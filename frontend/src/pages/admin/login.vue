<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
import { z } from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const authStore = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (authStore.isAuthenticated) {
    router.replace('/admin/')
  }
})

const schema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
})

type Schema = z.output<typeof schema>
const state = reactive<Partial<Schema>>({
  email: 'admin@example.com',
  password: '',
})

const error = ref('')
const isSubmitting = ref(false)
const showPassword = ref(false)

/**
 * Turns whatever the auth store / network throws into a clear,
 * user-facing message instead of a generic "Login failed".
 */
function resolveErrorMessage(err: unknown): string {
  // Prefer a message the auth store already parsed from the API response
  const storeMessage = authStore.error

  // Try to detect common HTTP status codes surfaced via $fetch/ofetch errors
  const status =
    (err as any)?.response?.status ??
    (err as any)?.statusCode ??
    (err as any)?.status

  if (status === 401 || status === 400) {
    return 'Incorrect email or password. Please try again.'
  }
  if (status === 403) {
    return 'Your account does not have access. Contact an administrator.'
  }
  if (status === 429) {
    return 'Too many attempts. Please wait a moment before trying again.'
  }
  if (status && status >= 500) {
    return 'Something went wrong on our end. Please try again shortly.'
  }

  // Offline / network failure (no response at all)
  if (
    (err as any)?.name === 'FetchError' && !status ||
    (typeof navigator !== 'undefined' && !navigator.onLine)
  ) {
    return 'Unable to reach the server. Check your internet connection and try again.'
  }

  if (storeMessage) return storeMessage

  return 'We couldn\'t sign you in. Please check your details and try again.'
}

async function handleLogin(event: FormSubmitEvent<Schema>) {
  if (isSubmitting.value) return
  error.value = ''
  isSubmitting.value = true
  try {
    await authStore.login(event.data.email.trim(), event.data.password)
    await router.push('/admin/')
  } catch (err: unknown) {
    error.value = resolveErrorMessage(err)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30 px-4">
    <UCard class="w-full max-w-md shadow-lg">
      <template #header>
        <div class="text-center py-2">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <UIcon name="i-lucide-lock" class="h-6 w-6 text-primary" />
          </div>
          <h1 class="text-xl font-bold">Admin Login</h1>
          <p class="text-sm text-muted mt-1">Sign in to manage your chatbot</p>
        </div>
      </template>

      <UForm :schema="schema" :state="state" class="flex flex-col gap-4" @submit="handleLogin">
        <UFormField name="email" label="Email" required>
          <UInput
            v-model="state.email"
            placeholder="you@example.com"
            type="email"
            autocomplete="username"
            autofocus
            icon="i-lucide-mail"
            class="w-full"
          />
        </UFormField>

        <UFormField name="password" label="Password" required>
          <UInput
            v-model="state.password"
            placeholder="Enter your password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            icon="i-lucide-key-round"
            class="w-full"
          >
            <template #trailing>
              <UButton
                :icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                color="neutral"
                variant="link"
                size="sm"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
                @click="showPassword = !showPassword"
              />
            </template>
          </UInput>
        </UFormField>

        <UAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-alert-circle"
          :description="error"
          role="alert"
          aria-live="assertive"
        />

        <UButton
          type="submit"
          :loading="authStore.loading || isSubmitting"
          :disabled="authStore.loading || isSubmitting"
          block
          size="lg"
        >
          {{ (authStore.loading || isSubmitting) ? 'Signing in…' : 'Sign In' }}
        </UButton>
      </UForm>
    </UCard>
  </div>
</template>
