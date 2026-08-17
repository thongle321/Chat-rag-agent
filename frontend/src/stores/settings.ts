import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { getErrorMessage } from '../api'

export interface AISettings {
  ai_provider: string
  ollama_base_url: string
  ollama_model: string
  ollama_api_key: string
  openai_model: string
  openai_api_key: string
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
    ollama_api_key: '',
    openai_model: '',
    openai_api_key: '',
  })
  const loading = ref(false)
  const error = ref('')
  const models = ref<string[]>([])
  const modelsCache = ref<Record<string, string[]>>({})
  const modelLoading = ref(false)

  function modelsKey(provider: string, baseUrl: string = '') {
    return `${provider}|${baseUrl}`
  }

  async function fetchSettings() {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get('/settings/ai')
      settings.value = data
    } catch (err: any) {
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(payload: Partial<AISettings>) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.put('/settings/ai', payload)
      settings.value = data
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function testConnection(opts?: { provider?: string; ollama_base_url?: string; ollama_api_key?: string; openai_api_key?: string }): Promise<TestResult> {
    try {
      const { data } = await api.post('/settings/test', opts ?? {})
      return data
    } catch (err: any) {
      return { ok: false, message: getErrorMessage(err) }
    }
  }

  async function fetchModels(opts?: { provider?: string; ollama_base_url?: string; ollama_api_key?: string; openai_api_key?: string }) {
    if (modelLoading.value) return
    modelLoading.value = true
    error.value = ''
    try {
      const { data } = await api.post('/settings/models', opts ?? {})
      models.value = data.models
      modelsCache.value[modelsKey(opts?.provider ?? '', opts?.ollama_base_url ?? '')] = data.models
    } catch (err: any) {
      models.value = []
    } finally {
      modelLoading.value = false
    }
  }

  async function useCachedModels(
    provider: string,
    baseUrl: string = '',
    opts?: { ollama_api_key?: string; openai_api_key?: string },
  ) {
    const key = modelsKey(provider, baseUrl)
    if (modelsCache.value[key] !== undefined) {
      models.value = modelsCache.value[key]
      return
    }
    await fetchModels({ provider, ollama_base_url: baseUrl, ...opts })
  }

  return { settings, loading, error, models, modelLoading, fetchSettings, updateSettings, testConnection, fetchModels, useCachedModels }
})
