<script setup lang="ts">
import ConfirmModal from "../../components/admin/ConfirmModal.vue";
import EmptyState from "../../components/admin/EmptyState.vue";
import { useDocumentUploads } from "../../composables/useDocumentUploads";
import { statusBadge } from "../../utils/documents";
import { formatSize } from "../../utils/format";

const uploads = useDocumentUploads();
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
              <UIcon class="text-primary" name="i-lucide-upload" />
              <span class="font-semibold">Documents</span>
            </div>
          </template>

          <UFileUpload
            accept=".txt,.md,.csv,.json,.pdf,.png,.jpg,.jpeg,.tiff,.tif,.bmp,.webp"
            class="w-full"
            description="Supports TXT, MD, CSV, JSON, PDF, PNG, JPG, TIFF, BMP, WebP"
            label="Drop files here"
            layout="list"
            multiple
            v-model="uploads.selectedFiles.value"
          />

          <div v-if="uploads.selectedFiles.value.length" class="mt-4">
            <UButton block :disabled="!uploads.selectedFiles.value.length" :loading="uploads.uploading.value" @click="uploads.handleUpload">
              Upload {{ uploads.selectedFiles.value.length }} file{{ uploads.selectedFiles.value.length > 1 ? "s" : "" }}
            </UButton>
          </div>

          <div v-if="uploads.documentList.value.length" class="mt-6 divide-y divide-default">
            <div v-for="item in uploads.documentList.value" :key="item.id" class="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <UIcon class="text-primary shrink-0" name="i-lucide-file-text" />
              <div class="flex-1 min-w-0">
                <p class="font-medium truncate flex items-center gap-1.5">
                  {{ item.title }}
                  <UBadge v-if="item.status" size="sm" variant="soft" :color="statusBadge(item.status).color">
                    {{ statusBadge(item.status).label }}
                  </UBadge>
                </p>
                <p class="text-sm text-muted">
                  {{ formatSize(item.size) }}
                  <template v-if="item.chunks">· {{ item.chunks }} chunk{{ item.chunks === 1 ? "" : "s" }}</template>
                </p>
                <p v-if="item.status === 'failed' && item.error_message" class="text-xs text-(--ui-color-error) mt-1">
                  {{ item.error_message }}
                </p>
              </div>
              <UButton
                color="error"
                icon="i-lucide-trash-2"
                size="sm"
                variant="ghost"
                :loading="!item.isProcessing && uploads.deleting.value && uploads.deleteTarget.value === item.title"
                @click="uploads.handleTrashClick(item)"
              />
            </div>
          </div>
          <EmptyState v-else icon="i-lucide-file-text" title="No documents uploaded yet" />
        </UCard>
      </div>
    </template>
  </UDashboardPanel>

  <ConfirmModal
    v-model:open="uploads.deleteOpen.value"
    title="Delete Document"
    description="This action cannot be undone."
    :loading="uploads.deleting.value"
    @confirm="uploads.deleteDocument"
  />
</template>
