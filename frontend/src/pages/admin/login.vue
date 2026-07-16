<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (authStore.isAuthenticated) {
    router.replace('/admin/')
  }
})

const email = ref('admin@example.com')
const password = ref('')
const error = ref('')

async function handleLogin() {
  error.value = ''
  try {
    await authStore.login(email.value, password.value)
    router.push('/admin/')
  } catch (err: any) {
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

      <form @submit.prevent="handleLogin" class="flex flex-col gap-4">
        <UFormField label="Email" required>
          <UInput v-model="email" placeholder="admin@example.com" type="email" class="w-full" />
        </UFormField>

        <UFormField label="Password" required>
          <UInput v-model="password" placeholder="Password" type="password" class="w-full" />
        </UFormField>

        <UAlert v-if="error" type="error" :description="error" />

        <UButton type="submit" :loading="authStore.loading" block size="lg">
          Sign In
        </UButton>
      </form>
    </UCard>
  </div>
</template>
