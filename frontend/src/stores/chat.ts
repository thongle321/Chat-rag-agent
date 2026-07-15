import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getErrorMessage } from '../api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  model?: string
  sources?: string[]
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
  const sessionId = computed(() => activeConversation.value?.sessionId ?? '')

  function newConversation() {
    const id = String(Date.now())
    conversations.value.push({
      id,
      title: 'Cuộc hội thoại mới',
      messages: [],
      pinned: false,
      createdAt: Date.now(),
      sessionId: '',
    })
    activeId.value = id
  }

  function setActive(id: string) {
    activeId.value = id
  }

  function deleteConversation(id: string) {
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeId.value === id) {
      activeId.value = conversations.value[0]?.id ?? ''
    }
  }

  function togglePin(id: string) {
    const c = conversations.value.find(c => c.id === id)
    if (c) c.pinned = !c.pinned
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

      conv.sessionId = data.session_id

      conv.messages.push({
        id: data.answer_id,
        role: 'assistant',
        text: data.answer,
        model: data.model,
        sources: data.source_documents,
      })

      return data
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  function clearMessages() {
    const conv = conversations.value.find(c => c.id === activeId.value)
    if (conv) {
      conv.messages = []
      conv.sessionId = ''
    }
  }

  return {
    conversations, activeId, loading, error,
    activeConversation, sessionId, messages,
    newConversation, setActive, deleteConversation, togglePin,
    sendMessage, clearMessages,
  }
})
