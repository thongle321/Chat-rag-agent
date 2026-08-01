<script setup lang="ts">
import { useSettingsStore } from '../../stores/settings'
import { z } from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const settingsStore = useSettingsStore()
const toast = useToast()

const saving = ref(false)
const error = ref('')
const showOpenaiKey = ref(false)
const showOllamaKey = ref(false)
const testing = ref(false)

const schema = z.object({
  ai_provider: z.string(),
  ollama_base_url: z.string().default(''),
  ollama_model: z.string().default(''),
  ollama_api_key: z.string().default(''),
  openai_api_key: z.string().default(''),
  openai_model: z.string().default(''),
}).refine(
  data => data.ai_provider !== 'ollama' || (data.ollama_base_url ?? '').trim().length > 0,
  { message: 'Base URL is required', path: ['ollama_base_url'] }
)

type Schema = z.output<typeof schema>
const state = reactive<Partial<Schema>>({
  ai_provider: 'ollama',
  ollama_base_url: '',
  ollama_model: '',
  ollama_api_key: '',
  openai_api_key: '',
  openai_model: '',
})

const providerOptions = [
  { label: 'Ollama', value: 'ollama' },
  { label: 'OpenAI', value: 'openai' },
]

const modelOptions = computed(() => settingsStore.models)

watch(
  () => state.ai_provider,
  () => {
    settingsStore.models = []
  },
)

onMounted(async () => {
  await settingsStore.fetchSettings()
  Object.assign(state, settingsStore.settings)
})

async function testConnection() {
  testing.value = true
  try {
    const result = await settingsStore.testConnection({
      provider: state.ai_provider,
      ollama_base_url: state.ollama_base_url || undefined,
      ollama_api_key: state.ollama_api_key || undefined,
      openai_api_key: state.openai_api_key || undefined,
    })
    toast.add({
      title: result.ok ? 'Connected' : 'Connection failed',
      description: result.message,
      color: result.ok ? 'success' : 'error',
      icon: result.ok ? 'i-lucide-check-circle' : 'i-lucide-x-circle',
      timeout: result.ok ? 5000 : 0,
    })
    if (result.ok) {
      await refreshModels()
    }
  } finally {
    testing.value = false
  }
}

async function refreshModels() {
  await settingsStore.fetchModels({
    provider: state.ai_provider,
    ollama_base_url: state.ollama_base_url || undefined,
    ollama_api_key: state.ollama_api_key || undefined,
    openai_api_key: state.openai_api_key || undefined,
  })
}

async function save(event: FormSubmitEvent<Schema>) {
  error.value = ''

  saving.value = true
  try {
    const payload: Record<string, string> = {
      ai_provider: event.data.ai_provider,
      ollama_base_url: event.data.ollama_base_url ?? '',
      ollama_model: event.data.ollama_model ?? '',
      openai_model: event.data.openai_model ?? '',
    }
    if (event.data.ai_provider === 'ollama' && event.data.ollama_api_key) {
      payload.ollama_api_key = event.data.ollama_api_key
    }
    if (event.data.ai_provider === 'openai' && event.data.openai_api_key) {
      payload.openai_api_key = event.data.openai_api_key
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
  <UDashboardPanel id="settings" :ui="{ body: 'lg:py-12' }">
    <template #header>
      <UDashboardNavbar title="Settings">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UForm :schema="schema" :state="state" class="flex flex-col gap-4 sm:gap-6 lg:gap-8 w-full lg:max-w-2xl mx-auto" @submit="save">
        <UCard>
          <template #header>
            <span class="font-semibold">AI Provider</span>
          </template>

          <UFormField name="ai_provider" label="Provider">
            <USelect v-model="state.ai_provider" :items="providerOptions" :disabled="saving" class="w-full" />
          </UFormField>
        </UCard>

        <UCard v-if="state.ai_provider === 'ollama'">
          <template #header>
            <span class="font-semibold">Ollama Configuration</span>
          </template>

          <div class="flex flex-col gap-4">
            <UFormField name="ollama_base_url" label="Base URL" required>
              <UInput v-model="state.ollama_base_url" placeholder="http://localhost:11434" :disabled="saving" class="w-full" />
            </UFormField>
            <UFormField name="ollama_api_key" label="API Key">
              <UInput
                v-model="state.ollama_api_key"
                placeholder="ollama-api-key"
                :type="showOllamaKey ? 'text' : 'password'"
                :disabled="saving"
                class="w-full"
              >
                <template #trailing>
                  <UButton :icon="showOllamaKey ? 'i-lucide-eye-off' : 'i-lucide-eye'" variant="ghost" size="sm" @click="showOllamaKey = !showOllamaKey" />
                </template>
              </UInput>
            </UFormField>
            <UFormField name="ollama_model" label="Model Name" required>
              <USelect v-model="state.ollama_model" :items="modelOptions" :loading="settingsStore.modelLoading" filterable placeholder="llama3.2" :disabled="saving" class="w-full">
                <template #trailing>
                  <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" :loading="settingsStore.modelLoading" @click.stop="refreshModels" />
                </template>
              </USelect>
            </UFormField>
          </div>
        </UCard>

        <UCard v-if="state.ai_provider === 'openai'">
          <template #header>
            <span class="font-semibold">OpenAI Configuration</span>
          </template>

          <div class="flex flex-col gap-4">
            <UFormField name="openai_api_key" label="API Key" required>
              <UInput
                v-model="state.openai_api_key"
                placeholder="sk-..."
                :type="showOpenaiKey ? 'text' : 'password'"
                :disabled="saving"
                class="w-full"
              >
                <template #trailing>
                  <UButton :icon="showOpenaiKey ? 'i-lucide-eye-off' : 'i-lucide-eye'" variant="ghost" size="sm" @click="showOpenaiKey = !showOpenaiKey" />
                </template>
              </UInput>
            </UFormField>
            <UFormField name="openai_model" label="Model Name" required>
              <USelect v-model="state.openai_model" :items="modelOptions" :loading="settingsStore.modelLoading" filterable placeholder="gpt-4o" :disabled="saving" class="w-full">
                <template #trailing>
                  <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" :loading="settingsStore.modelLoading" @click.stop="refreshModels" />
                </template>
              </USelect>
            </UFormField>
          </div>
        </UCard>

        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" closable @close="error = ''" />

        <div class="flex gap-2">
          <UButton :loading="testing" variant="outline" @click="testConnection">
            Test Connection
          </UButton>
          <UButton type="submit" :loading="saving">
            Save
          </UButton>
        </div>
      </UForm>
    </template>
  </UDashboardPanel>
</template>
