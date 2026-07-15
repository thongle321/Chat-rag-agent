import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { getErrorMessage } from '../api'

export interface DocumentInfo {
  document_id: string
  title: string
  chunks: number
}

export interface UploadResult {
  status: string
  document_id: string
  message: string
}

export const useDocumentStore = defineStore('documents', () => {
  const documents = ref<DocumentInfo[]>([])
  const loading = ref(false)
  const indexing = ref(false)
  const error = ref('')

  async function fetchDocuments() {
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
        indexing.value = true
        await pollForIndexing(queued)
        indexing.value = false
      }

      return results
    } catch (err: any) {
      error.value = getErrorMessage(err)
      throw err
    } finally {
      loading.value = false
      indexing.value = false
    }
  }

  async function pollForIndexing(filenames: string[]) {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000))
      try {
        const { data } = await api.get('/documents')
        documents.value = data.documents
        const titles = data.documents.map((d: DocumentInfo) => d.title)
        if (filenames.every(f => titles.includes(f))) return
      } catch {
        // non-fatal, keep polling
      }
    }
  }

  async function deleteDocument(title: string) {
    try {
      await api.delete(`/documents/${encodeURIComponent(title)}`)
      await fetchDocuments()
    } catch (err: any) {
      error.value = getErrorMessage(err)
    }
  }

  return { documents, loading, indexing, error, fetchDocuments, uploadDocuments, deleteDocument }
})
