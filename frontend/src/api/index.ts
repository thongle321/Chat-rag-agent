import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export function getErrorMessage(err: any): string {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join('; ')
  return err.message || 'An error occurred'
}

export default api
