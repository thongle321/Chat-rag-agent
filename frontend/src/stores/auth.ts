import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getErrorMessage } from '../api'

interface User {
  id: string
  email: string
  role: string
  is_active: boolean
  is_superuser: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string>(localStorage.getItem('auth_token') || '')
  const loading = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => !!token.value && !!user.value)

  // Set auth token on axios instance
  function setToken(newToken: string) {
    token.value = newToken
    if (newToken) {
      localStorage.setItem('auth_token', newToken)
      api.defaults.headers.common['Authorization'] = `Bearer ${newToken}`
    } else {
      localStorage.removeItem('auth_token')
      delete api.defaults.headers.common['Authorization']
    }
  }

  // Initialize token from localStorage on load
  if (token.value) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  async function login(email: string, password: string) {
    loading.value = true
    error.value = ''
    try {
      // fastapi-users expects form-data for login
      const formData = new URLSearchParams()
      formData.append('username', email)
      formData.append('password', password)

      const { data } = await api.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      setToken(data.access_token)
      await fetchUser()
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await api.post('/auth/logout', null, {
        headers: token.value ? { Authorization: `Bearer ${token.value}` } : {},
      })
    } catch {
      // Ignore — token may be expired, local cleanup is what matters
    }
    setToken('')
    user.value = null
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
    } catch {
      setToken('')
      user.value = null
    }
  }

  return { user, token, loading, error, isAuthenticated, login, logout, fetchUser }
})
