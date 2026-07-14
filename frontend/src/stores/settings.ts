import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export interface AISettings {
  ai_provider: string
  ollama_base_url: string
  ollama_model: string
  openai_model: string
  has_openai_key: boolean
}

export interface TestResult {
  ok: boolean
  message: string
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AISettings>({
    ai_provider: 'ollama',
    ollama_base_url: '',
    ollama_model: '',
    openai_model: '',
    has_openai_key: false,
  })
  const loading = ref(false)
  const error = ref('')

  async function fetchSettings() {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get('/settings/ai')
      settings.value = data
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to load settings'
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(payload: Partial<AISettings> & { openai_api_key?: string }) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.put('/settings/ai', payload)
      settings.value = data
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to save settings'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function testConnection(): Promise<TestResult> {
    try {
      const { data } = await api.post('/settings/test')
      return data
    } catch (err: any) {
      return { ok: false, message: err.response?.data?.detail || err.message || 'Test failed' }
    }
  }

  return { settings, loading, error, fetchSettings, updateSettings, testConnection }
})
