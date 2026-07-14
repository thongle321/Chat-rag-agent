import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  model?: string
  sources?: string[]
  answerId?: string
}

export const useChatStore = defineStore('chat', () => {
  const sessionId = ref('')
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const error = ref('')

  async function sendMessage(question: string) {
    if (!question.trim()) return

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      text: question,
    }
    messages.value.push(userMsg)
    error.value = ''
    loading.value = true

    try {
      const { data } = await api.post('/chat/query', {
        question,
        session_id: sessionId.value || undefined,
      })

      sessionId.value = data.session_id

      const assistantMsg: ChatMessage = {
        id: data.answer_id,
        role: 'assistant',
        text: data.answer,
        model: data.model,
        sources: data.source_documents,
        answerId: data.answer_id,
      }
      messages.value.push(assistantMsg)
      return data
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to get response'
      throw err
    } finally {
      loading.value = false
    }
  }

  function clearMessages() {
    messages.value = []
    sessionId.value = ''
  }

  return { sessionId, messages, loading, error, sendMessage, clearMessages }
})
