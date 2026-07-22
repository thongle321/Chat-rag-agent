import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { getErrorMessage } from '../api'

export interface DocumentInfo {
  document_id: string
  title: string
  chunks: number
  size: number
}

export interface UploadResult {
  status: string
  document_id: string
  message: string
}

export const useDocumentStore = defineStore('documents', () => {
  const documents = ref<DocumentInfo[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchDocuments(force = false) {
    if (documents.value.length > 0 && !force) return
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get('/documents')
      documents.value = data.documents
    } catch (err: any) {
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function uploadDocuments(files: File[]): Promise<UploadResult[]> {
    loading.value = true
    error.value = ''
    try {
      const fd = new FormData()
      for (const file of files) {
        fd.append('files', file)
      }

      const { data } = await api.post('/documents/upload', fd)
      const results: UploadResult[] = data.results

      const queued = results
        .filter(r => r.status === 'ok')
        .map(r => {
          const parts = r.message.split("'")
          return parts[1] || ''
        })
        .filter(Boolean)

      if (queued.length) {
        setTimeout(() => fetchDocuments(true), 5000)
      }

      return results
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteDocument(title: string) {
    try {
      await api.delete(`/documents/${encodeURIComponent(title)}`)
      await fetchDocuments(true)
    } catch (err: any) {
      error.value = getErrorMessage(err)
    }
  }

  return { documents, loading, error, fetchDocuments, uploadDocuments, deleteDocument }
})
