import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getErrorMessage } from '../api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  model?: string
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
    if (diff < day) return 'Hôm nay'
    if (diff < 2 * day) return 'Hôm qua'
    if (diff < 7 * day) return '7 ngày trước'
    if (diff < 30 * day) return '30 ngày trước'
    return 'Cũ hơn'
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

  const activeConversation = computed(() =>
    conversations.value.find(c => c.id === activeId.value) ?? null
  )

  const messages = computed(() => activeConversation.value?.messages ?? [])

  async function fetchSessions() {
    try {
      const { data } = await api.get('/chat/sessions')
      conversations.value = data.map((s: any) => ({
        id: s.id,
        title: s.title,
        messages: [],
        pinned: s.pinned,
        createdAt: new Date(s.created_at).getTime(),
        sessionId: s.id,
      }))
      if (!activeId.value && conversations.value.length) {
        activeId.value = conversations.value[0].id
      }
    } catch {
      // offline fallback — keep current state
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
      }))
    } catch {
      // ignore
    }
  }

  function newConversation() {
    const id = String(Date.now())
    conversations.value.unshift({
      id,
      title: 'Cuộc hội thoại mới',
      messages: [],
      pinned: false,
      createdAt: Date.now(),
      sessionId: '',
    })
    activeId.value = id
  }

  async function setActive(id: string) {
    activeId.value = id
    const conv = conversations.value.find(c => c.id === id)
    if (conv && !conv.messages.length) {
      await fetchSessionMessages(id)
    }
  }

  async function deleteConversation(id: string) {
    try {
      await api.delete(`/chat/sessions/${id}`)
    } catch { /* ignore */ }
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeId.value === id) {
      activeId.value = conversations.value[0]?.id ?? ''
    }
  }

  async function togglePin(id: string) {
    const c = conversations.value.find(c => c.id === id)
    if (!c) return
    try {
      await api.put(`/chat/sessions/${id}/pin`)
      c.pinned = !c.pinned
    } catch { /* ignore */ }
  }

  async function renameConversation(id: string, title: string) {
    try {
      await api.put(`/chat/sessions/${id}/title`, { title })
      const c = conversations.value.find(c => c.id === id)
      if (c) c.title = title
    } catch { /* ignore */ }
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

    error.value = ''
    loading.value = true

    try {
      const { data } = await api.post('/chat/query', {
        question,
        session_id: conv.sessionId || undefined,
      })

      // If first message, session_id is now set — update the id to match server
      if (!conv.sessionId) {
        conv.sessionId = data.session_id
        // Replace client-generated id with server id so sidebar matches
        const oldId = conv.id
        conv.id = data.session_id
        if (activeId.value === oldId) activeId.value = data.session_id
      }

      conv.messages.push({
        id: data.answer_id,
        role: 'assistant',
        text: data.answer,
        model: data.model,
      })

      return data
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    conversations, activeId, loading, error,
    activeConversation, messages,
    fetchSessions, fetchSessionMessages,
    newConversation, setActive, deleteConversation, togglePin,
    renameConversation,
    sendMessage,
  }
})
