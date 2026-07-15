<script setup lang="ts">
import { useSettingsStore } from '../../../stores/settings'

const settingsStore = useSettingsStore()
const toast = useToast()

const saving = ref(false)
const error = ref('')
const showKey = ref(false)
const testing = ref(false)

const form = ref({
  ai_provider: 'ollama',
  ollama_base_url: '',
  ollama_model: '',
  openai_api_key: '',
  openai_model: '',
})

const providerOptions = [
  { label: 'Ollama (Local)', value: 'ollama' },
  { label: 'OpenAI (Cloud)', value: 'openai' },
]

const settings = computed(() => settingsStore.settings)

onMounted(async () => {
  await settingsStore.fetchSettings()
  const s = settingsStore.settings
  form.value.ai_provider = s.ai_provider
  form.value.ollama_base_url = s.ollama_base_url
  form.value.ollama_model = s.ollama_model
  form.value.openai_model = s.openai_model
  await testConnection()
})

async function testConnection() {
  testing.value = true
  try {
    const result = await settingsStore.testConnection()
    toast.add({
      title: result.ok ? 'Connected' : 'Connection failed',
      description: result.message,
      color: result.ok ? 'success' : 'error',
      icon: result.ok ? 'i-lucide-check-circle' : 'i-lucide-x-circle',
      timeout: result.ok ? 5000 : 0,
    })
  } finally {
    testing.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload: Record<string, string> = {
      ai_provider: form.value.ai_provider,
      ollama_base_url: form.value.ollama_base_url,
      ollama_model: form.value.ollama_model,
      openai_model: form.value.openai_model,
    }
    if (form.value.ai_provider === 'openai' && form.value.openai_api_key) {
      payload.openai_api_key = form.value.openai_api_key
    }
    await settingsStore.updateSettings(payload)
    toast.add({
      title: 'Saved',
      description: 'Settings saved successfully',
      color: 'success',
      icon: 'i-lucide-check',
      timeout: 3000,
    })
    await testConnection()
  } catch (err: any) {
    error.value = settingsStore.error || err.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <UCard>
      <template #header>
        <span class="font-semibold">AI Provider</span>
      </template>

      <UFormField label="Provider">
        <USelect v-model="form.ai_provider" :items="providerOptions" :disabled="saving" class="w-full" />
      </UFormField>
    </UCard>

    <UCard v-if="form.ai_provider === 'ollama'" class="mt-4">
      <template #header>
        <span class="font-semibold">Ollama Configuration</span>
      </template>

      <div class="flex flex-col gap-4">
        <UFormField label="Base URL" required>
          <UInput v-model="form.ollama_base_url" placeholder="http://localhost:11434" :disabled="saving" class="w-full" />
        </UFormField>
        <UFormField label="Model Name" required>
          <UInput v-model="form.ollama_model" placeholder="llama3.2" :disabled="saving" class="w-full" />
        </UFormField>
      </div>
    </UCard>

    <UCard v-if="form.ai_provider === 'openai'" class="mt-4">
      <template #header>
        <span class="font-semibold">OpenAI Configuration</span>
      </template>

      <div class="flex flex-col gap-4">
        <UFormField label="API Key" :hint="settings.has_openai_key ? 'Configured' : ''" required>
          <UInput
            v-model="form.openai_api_key"
            placeholder="sk-..."
            :type="showKey ? 'text' : 'password'"
            :disabled="saving"
            class="w-full"
          >
            <template #trailing>
              <UButton :icon="showKey ? 'i-lucide-eye-off' : 'i-lucide-eye'" variant="ghost" size="sm" @click="showKey = !showKey" />
            </template>
          </UInput>
        </UFormField>
        <UFormField label="Model Name" required>
          <UInput v-model="form.openai_model" placeholder="gpt-4o" :disabled="saving" class="w-full" />
        </UFormField>
      </div>
    </UCard>

    <UAlert v-if="error" type="error" :description="error" class="mt-4" closable @close="error = ''" />

    <div class="flex gap-2 mt-4">
      <UButton :loading="testing" variant="outline" @click="testConnection">
        Test Connection
      </UButton>
      <UButton :loading="saving" @click="save">
        Save
      </UButton>
    </div>
  </div>
</template>
