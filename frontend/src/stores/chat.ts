import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getErrorMessage, streamChat, type StreamSource } from '../api'

const STORAGE_KEY = 'chat_sessions'
const ACTIVE_KEY = 'chat_active_id'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  model?: string
  streaming?: boolean
  sources?: StreamSource[]
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  pinned: boolean
  createdAt: number
  sessionId: string
}

export function groupByDate(conversations: Conversation[]): [string, Conversation[]][] {
  const now = Date.now()
  const day = 86400000
  const groups = new Map<string, Conversation[]>()
  const label = (d: number) => {
    const diff = now - d
    if (diff < day) return 'Today'
    if (diff < 2 * day) return 'Yesterday'
    if (diff < 7 * day) return '7 days ago'
    if (diff < 30 * day) return '30 days ago'
    return 'Older'
  }
  for (const c of conversations) {
    const l = label(c.createdAt)
    const arr = groups.get(l) ?? []
    arr.push(c)
    groups.set(l, arr)
  }
  return [...groups.entries()]
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeId = ref('')
  const loading = ref(false)
  const error = ref('')
  // One AbortController per in-flight send, keyed by conversation id, so switching
  // chats never aborts a running stream — it keeps streaming in the background.
  const activeControllers = new Map<string, AbortController>()

  const activeConversation = computed(() =>
    conversations.value.find(c => c.id === activeId.value) ?? null
  )

  const messages = computed(() => activeConversation.value?.messages ?? [])

  const streamingText = computed(() =>
    activeConversation.value?.messages.find(m => m.streaming)?.text ?? ''
  )

  function saveToStorage() {
    const data = conversations.value.map(c => ({
      id: c.id,
      title: c.title,
      pinned: c.pinned,
      createdAt: c.createdAt,
      sessionId: c.sessionId,
    }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    localStorage.setItem(ACTIVE_KEY, activeId.value)
  }

  function loadFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      conversations.value = JSON.parse(raw).map((s: any) => ({
        id: s.id,
        title: s.title,
        messages: [],
        pinned: s.pinned,
        createdAt: s.createdAt,
        sessionId: s.sessionId || s.id,
      }))
    } catch {
      // corrupted storage
    }
    // Restore the chat you were viewing; fall back to the first session.
    const stored = localStorage.getItem(ACTIVE_KEY) || ''
    if (stored && conversations.value.some(c => c.id === stored)) {
      activeId.value = stored
    }
  }

  async function fetchSessions() {
    loadFromStorage()
    if (!activeId.value && conversations.value.length) {
      activeId.value = conversations.value[0].id
    }
    // Restore the chat you were in before refresh — messages (and hydrated sources).
    const conv = conversations.value.find(c => c.id === activeId.value)
    if (conv && !conv.messages.length) {
      await fetchSessionMessages(activeId.value)
    }
  }

  async function fetchSessionMessages(id: string) {
    try {
      const { data } = await api.get(`/chat/sessions/${id}`)
      const conv = conversations.value.find(c => c.id === id)
      if (!conv) return
      conv.messages = (data.messages || []).map((m: any, i: number) => ({
        id: String(i),
        role: m.role === 'user' ? 'user' : 'assistant',
        text: m.content,
        sources: m.sources ?? undefined,
      }))
    } catch {
      // ignore
    }
  }

  function newConversation() {
    const id = String(Date.now())
    conversations.value.unshift({
      id,
      title: 'New chat',
      messages: [],
      pinned: false,
      createdAt: Date.now(),
      sessionId: '',
    })
    activeId.value = id
    saveToStorage()
  }

  async function setActive(id: string) {
    activeId.value = id
    saveToStorage()
    const conv = conversations.value.find(c => c.id === id)
    if (conv && !conv.messages.length) {
      await fetchSessionMessages(id)
    }
  }

  async function deleteConversation(id: string) {
    activeControllers.get(id)?.abort()
    activeControllers.delete(id)
    try {
      await api.delete(`/chat/sessions/${id}`)
    } catch (err)
    {
      console.error('Failed to delete session on backend:', err)
    }
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeId.value === id) {
      activeId.value = conversations.value[0]?.id ?? ''
    }
    saveToStorage()
  }

  function togglePin(id: string) {
    const c = conversations.value.find(c => c.id === id)
    if (!c) return
    c.pinned = !c.pinned
    saveToStorage()
  }

  function renameConversation(id: string, title: string) {
    const c = conversations.value.find(c => c.id === id)
    if (!c) return
    c.title = title
    saveToStorage()
  }

  async function sendMessage(question: string) {
    if (!question.trim()) return

    if (!activeId.value) newConversation()

    const conv = conversations.value.find(c => c.id === activeId.value)
    if (!conv) return

    conv.messages.push({
      id: String(Date.now()),
      role: 'user',
      text: question,
    })

    if (conv.messages.length === 1) {
      conv.title = question.slice(0, 60)
    }

    conv.messages.push({ id: 'streaming', role: 'assistant', text: '', streaming: true })
    const streamMsg = conv.messages[conv.messages.length - 1] as ChatMessage

    error.value = ''
    loading.value = true

    const ctrl = new AbortController()
    const key = conv.id
    activeControllers.set(key, ctrl)
    try {
      await streamChat(
        question,
        conv.sessionId || undefined,
        {
          onDelta: (content) => { streamMsg.text += content },
          onSources: (sources) => { streamMsg.sources = sources },
          onDone: (data) => {
            // If first message, session_id is now set — update the id to match server
            if (!conv.sessionId) {
              conv.sessionId = data.session_id
              const oldId = conv.id
              conv.id = data.session_id
              if (activeId.value === oldId) activeId.value = data.session_id
              const c = activeControllers.get(oldId)
              if (c) {
                activeControllers.delete(oldId)
                activeControllers.set(data.session_id, c)
              }
            }
            streamMsg.id = String(Date.now())
            streamMsg.model = data.model
            streamMsg.streaming = false
          },
          onError: (detail) => { error.value = detail },
        },
        ctrl.signal,
      )
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        error.value = getErrorMessage(err)
      }
    } finally {
      loading.value = false
      activeControllers.delete(key)
      streamMsg.streaming = false
      if (!streamMsg.text) {
        conv.messages = conv.messages.filter(m => m !== streamMsg)
      }
      saveToStorage()
    }
  }

  function stop() {
    activeControllers.get(activeId.value)?.abort()
  }

  return {
    conversations, activeId, loading, error,
    activeConversation, messages, streamingText,
    fetchSessions, fetchSessionMessages,
    newConversation, setActive, deleteConversation, togglePin,
    renameConversation,
    sendMessage, stop,
  }
})
