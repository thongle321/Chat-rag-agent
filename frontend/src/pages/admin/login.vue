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
  email: z.string().min(1, 'Email is required').email('Invalid email'),
  password: z.string().min(1, 'Password is required'),
})

type Schema = z.output<typeof schema>
const state = reactive<Partial<Schema>>({
  email: 'admin@example.com',
  password: '',
})

const error = ref('')

async function handleLogin(event: FormSubmitEvent<Schema>) {
  error.value = ''
  try {
    await authStore.login(event.data.email, event.data.password)
    router.push('/admin/')
  } catch (err: unknown) {
    error.value = authStore.error || 'Login failed'
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30">
    <UCard class="w-full max-w-md">
      <template #header>
        <div class="text-center">
          <h1 class="text-xl font-bold">Admin Login</h1>
          <p class="text-sm text-muted mt-1">Sign in to manage your chatbot</p>
        </div>
      </template>

      <UForm :schema="schema" :state="state" class="flex flex-col gap-4" @submit="handleLogin">
        <UFormField name="email" label="Email" required>
          <UInput v-model="state.email" placeholder="admin@example.com" type="email" class="w-full" />
        </UFormField>

        <UFormField name="password" label="Password" required>
          <UInput v-model="state.password" placeholder="Password" type="password" class="w-full" />
        </UFormField>

        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />

        <UButton type="submit" :loading="authStore.loading" block size="lg">
          Sign In
        </UButton>
      </UForm>
    </UCard>
  </div>
</template>
