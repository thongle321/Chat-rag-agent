import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { getErrorMessage } from '../api'

export const useFeedbackStore = defineStore('feedback', () => {
  const loading = ref(false)
  const error = ref('')
  const lastFeedbackStatus = ref('')

  async function submitFeedback(answerId: string, rating: number, comments?: string, sessionId?: string) {
    loading.value = true
    error.value = ''
    lastFeedbackStatus.value = ''

    try {
      const { data } = await api.post('/feedback/rating', {
        session_id: sessionId,
        answer_id: answerId,
        rating,
        comments: comments || undefined,
      })
      lastFeedbackStatus.value = data.saved ? 'success' : 'not_saved'
      return data
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return { loading, error, lastFeedbackStatus, submitFeedback }
})
