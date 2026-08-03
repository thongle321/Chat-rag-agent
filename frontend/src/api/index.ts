import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 120000,
})

export function getErrorMessage(err: unknown): string {
  if (!axios.isAxiosError(err)) return err instanceof Error ? err.message : 'An error occurred'
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('; ')
  return err.message || 'An error occurred'
}

export default api
