<script setup lang="ts">
import { useDocumentStore } from '../../stores/documents'

const documentStore = useDocumentStore()

const selectedFiles = ref<File[]>([])
const uploading = ref(false)
const uploadResults = ref<{ name: string; status: string; message: string }[]>([])
const deleting = ref(false)
const deleteTarget = ref('')
const showDeleteModal = ref(false)

onMounted(() => {
  documentStore.fetchDocuments()
})

async function handleUpload() {
  if (!selectedFiles.value.length) return

  uploading.value = true
  uploadResults.value = []

  try {
    const results = await documentStore.uploadDocuments(selectedFiles.value)
    uploadResults.value = results.map((r, i) => ({
      name: selectedFiles.value[i]?.name || 'Unknown',
      status: r.status,
      message: r.message,
    }))
    selectedFiles.value = []
  } catch {
    uploadResults.value = [{
      name: 'Upload',
      status: 'error',
      message: documentStore.error || 'Upload failed',
    }]
  } finally {
    uploading.value = false
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
        <!-- Upload Section -->
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-upload" class="text-primary" />
              <span class="font-semibold">Upload Documents</span>
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

          <!-- Indexing indicator -->
          <div v-if="documentStore.indexing" class="mt-4 flex items-center gap-2 text-sm text-muted">
            <UIcon name="i-lucide-loader-2" class="animate-spin text-primary" />
            <span>Indexing in background — documents will appear below when ready</span>
          </div>

          <!-- Upload Results -->
          <div v-if="uploadResults.length" class="mt-4 space-y-2">
            <div
              v-for="result in uploadResults"
              :key="result.name"
              class="flex items-center gap-3 p-3 rounded-lg border border-default"
            >
              <UIcon
                :name="result.status === 'ok' ? 'i-lucide-check-circle' : 'i-lucide-x-circle'"
                :class="result.status === 'ok' ? 'text-success' : 'text-error'"
                class="shrink-0"
              />
              <div class="flex-1 min-w-0">
                <p class="font-medium truncate text-sm">{{ result.name }}</p>
                <p class="text-xs text-muted">{{ result.message }}</p>
              </div>
              <UBadge
                :color="result.status === 'ok' ? 'success' : 'error'"
                variant="soft"
                size="xs"
              >
                {{ result.status === 'ok' ? 'Indexed' : 'Failed' }}
              </UBadge>
            </div>
          </div>
        </UCard>

        <!-- Documents List -->
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-file-text" class="text-primary" />
              <span class="font-semibold">Indexed Documents</span>
            </div>
          </template>

          <div v-if="documentStore.documents.length">
            <div
              v-for="(doc, i) in documentStore.documents"
              :key="doc.document_id"
              class="flex items-center gap-3 p-3 border-b border-default last:border-b-0"
            >
              <span class="text-xs text-muted w-6 text-right">{{ i + 1 }}</span>
              <UIcon name="i-lucide-file-text" class="text-primary shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="font-medium truncate">{{ doc.title }}</p>
                <p class="text-sm text-muted">{{ doc.chunks }} chunk{{ doc.chunks === 1 ? '' : 's' }} indexed</p>
              </div>
              <UButton
                icon="i-lucide-trash-2"
                variant="ghost"
                color="error"
                size="sm"
                :loading="deleting"
                @click="confirmDelete(doc.title)"
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
