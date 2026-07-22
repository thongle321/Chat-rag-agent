<script setup lang="ts">
import api from '../../api'
import { useDocumentStore } from '../../stores/documents'

const documentStore = useDocumentStore()

const selectedFiles = ref<File[]>([])
const uploading = ref(false)
const uploadResults = ref<{ name: string; status: string; message: string; size: number; chunks: number }[]>([])
const deleting = ref(false)
const deleteTarget = ref('')
const showDeleteModal = ref(false)

let pollTimer: ReturnType<typeof setTimeout> | null = null

const documentList = computed(() => {
  const storeDocs = documentStore.documents
  const storeNames = new Set(storeDocs.map(d => d.title))
  const processing = uploadResults.value.filter(r => !storeNames.has(r.name))
  return [
    ...processing.map(r => ({
      id: r.name,
      title: r.name,
      size: r.size,
      chunks: r.chunks,
      status: r.status,
      isProcessing: true as const,
    })),
    ...storeDocs.map(d => ({
      id: d.document_id,
      title: d.title,
      size: d.size,
      chunks: d.chunks,
      status: null as string | null,
      isProcessing: false as const,
    })),
  ]
})

onMounted(() => {
  documentStore.fetchDocuments()
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function pollStatus(titles: string[]) {
  if (!titles.length) return

  try {
    const { data } = await api.get('/documents/upload/status', {
      params: { titles: titles.join(',') },
    })
    for (const res of uploadResults.value) {
      const status = data.results[res.name]
      if (status) {
        res.status = status.status
        res.chunks = status.chunks || 0
        res.size = status.size || res.size
      }
    }
  } catch {
    // ponytail: poll failed, retry
  }

  const pending = uploadResults.value.filter(r => r.status === 'indexed')
  if (pending.length) {
    pollTimer = setTimeout(() => pollStatus(pending.map(r => r.name)), 2000)
  } else {
    documentStore.fetchDocuments(true)
  }
}

async function handleUpload() {
  if (!selectedFiles.value.length) return

  uploading.value = true
  uploadResults.value = []

  try {
    const results = await documentStore.uploadDocuments(selectedFiles.value)
    uploadResults.value = results.map((r, i) => ({
      name: selectedFiles.value[i]?.name || 'Unknown',
      status: r.status === 'ok' ? 'indexed' : 'failed',
      message: r.message,
      size: selectedFiles.value[i]?.size || 0,
      chunks: 0,
    }))
    selectedFiles.value = []

    const indexed = uploadResults.value.filter(r => r.status === 'indexed')
    if (indexed.length) {
      pollTimer = setTimeout(() => pollStatus(indexed.map(r => r.name)), 2000)
    }
  } catch {
    uploadResults.value = [{
      name: 'Upload',
      status: 'failed',
      message: documentStore.error || 'Upload failed',
      size: 0,
      chunks: 0,
    }]
  } finally {
    uploading.value = false
  }
}

function handleTrashClick(item: ReturnType<typeof documentList.value>[number]) {
  if (item.isProcessing) {
    uploadResults.value = uploadResults.value.filter(r => r.name !== item.id)
  } else {
    confirmDelete(item.title)
  }
}

function confirmDelete(title: string) {
  deleteTarget.value = title
  showDeleteModal.value = true
}

async function deleteDocument() {
  const title = deleteTarget.value
  showDeleteModal.value = false
  deleting.value = true
  try {
    await documentStore.deleteDocument(title)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <UDashboardPanel id="documents">
    <template #header>
      <UDashboardNavbar title="Documents">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col gap-6">
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-upload" class="text-primary" />
              <span class="font-semibold">Documents</span>
            </div>
          </template>

          <UFileUpload
            v-model="selectedFiles"
            multiple
            accept=".txt,.md,.csv,.json,.pdf"
            label="Drop files here"
            description="Supports TXT, MD, CSV, JSON, PDF"
            layout="list"
            class="w-full"
          />

          <div v-if="selectedFiles.length" class="mt-4">
            <UButton
              block
              :loading="uploading"
              :disabled="!selectedFiles.length"
              @click="handleUpload"
            >
              Upload {{ selectedFiles.length }} file{{ selectedFiles.length > 1 ? 's' : '' }}
            </UButton>
          </div>

          <div v-if="documentList.length" class="mt-6 divide-y divide-default">
            <div
              v-for="item in documentList"
              :key="item.id"
              class="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
            >
              <UIcon name="i-lucide-file-text" class="text-primary shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="font-medium truncate flex items-center gap-1.5">
                  {{ item.title }}
                  <UBadge
                    v-if="item.isProcessing"
                    size="xs"
                    variant="soft"
                    :color="item.status === 'indexed' ? 'warning' : 'error'"
                  >
                    {{ item.status === 'indexed' ? 'Indexed' : 'Failed' }}
                  </UBadge>
                </p>
                <p class="text-sm text-muted">
                  {{ formatSize(item.size) }}<template v-if="item.chunks"> · {{ item.chunks }} chunk{{ item.chunks === 1 ? '' : 's' }}</template>
                </p>
              </div>
              <UButton
                icon="i-lucide-trash-2"
                variant="ghost"
                color="error"
                size="sm"
                :loading="!item.isProcessing && deleting && deleteTarget === item.title"
                @click="handleTrashClick(item)"
              />
            </div>
          </div>
          <div v-else class="flex flex-col items-center justify-center py-8">
            <UIcon name="i-lucide-file-text" class="text-4xl text-muted mb-2" />
            <p class="text-muted">No documents uploaded yet</p>
          </div>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>

  <UModal v-model:open="showDeleteModal" title="Delete Document" description="This action cannot be undone." :ui="{ footer: 'justify-end' }">
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton label="Delete" color="error" :loading="deleting" @click="deleteDocument" />
    </template>
  </UModal>
</template>
