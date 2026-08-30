<script setup lang="ts">
import api from "../../api";
import { useDocumentStore } from "../../stores/documents";

let pollTimer: number | undefined;

const documentStore = useDocumentStore();

const selectedFiles = ref<File[]>([]);
const uploading = ref(false);
const uploadResults = ref<
    {
        name: string;
        status: string;
        message: string;
        size: number;
        chunks: number;
        error_message?: string;
    }[]
>([]);
const deleting = ref(false);
const deleteTarget = ref("");
const showDeleteModal = ref(false);

const STORAGE_KEY = "upload-results";

function saveUploadResults() {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(uploadResults.value));
}

function loadUploadResults() {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
        try {
            uploadResults.value = JSON.parse(stored);
        } catch {
            uploadResults.value = [];
        }
    }
}

const ACTIVELY_PROCESSING = ["pending", "processing"];

function isProcessingStatus(status: string): boolean {
    return ACTIVELY_PROCESSING.includes(status);
}

const documentList = computed(() => {
    const storeDocs = documentStore.documents;
    const storeNames = new Set(storeDocs.map((d) => d.title));
    const processing = uploadResults.value.filter(
        (r) => !storeNames.has(r.name) && r.status !== "completed",
    );
    return [
        ...processing.map((r) => ({
            chunks: r.chunks,
            error_message: r.error_message,
            id: r.name,
            isProcessing: true as const,
            size: r.size,
            status: r.status,
            title: r.name,
        })),
        ...storeDocs.map((d) => {
            const uploadResult = uploadResults.value.find(
                (r) => r.name === d.title,
            );
            return {
                chunks: d.chunks,
                error_message: uploadResult?.error_message,
                id: d.document_id,
                isProcessing: false,
                size: d.size,
                // present in the vector store => indexing finished
                status: uploadResult?.status || "completed",
                title: d.title,
            };
        }),
    ];
});

onMounted(() => {
    documentStore.fetchDocuments();
    loadUploadResults();
    const indexed = uploadResults.value.filter((r) =>
        isProcessingStatus(r.status),
    );
    if (indexed.length) {
        pollTimer = setTimeout(
            () => pollStatus(indexed.map((r) => r.name)),
            2000,
        );
    }
});

onUnmounted(() => {
    if (pollTimer) {
        clearTimeout(pollTimer);
    }
});

function statusBadge(status: string): {
    label: string;
    color: "warning" | "info" | "success" | "error";
} {
    switch (status) {
        case "pending":
            return { color: "warning", label: "Pending" };
        case "processing":
            return { color: "info", label: "Processing" };
        case "completed":
            return { color: "success", label: "Completed" };
        case "failed":
            return { color: "error", label: "Failed" };
        default:
            return { color: "warning", label: status };
    }
}

function formatSize(bytes: number): string {
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function pollStatus(titles: string[]) {
    if (!titles.length) {
        return;
    }

    try {
        const { data } = await api.get("/documents/upload/status", {
            params: { titles: titles.join(",") },
        });
        for (const res of uploadResults.value) {
            const status = data.results[res.name];
            if (status) {
                res.status = status.status ?? res.status;
                res.chunks = status.chunks || 0;
                res.size = status.size || res.size;
                if (status.error_message) {
                    res.error_message = status.error_message;
                    res.message = status.error_message;
                }
            }
        }
    } catch {
        // ponytail: poll failed, retry
    }

    await documentStore.fetchDocuments(true);
    const pending = uploadResults.value.filter((r) =>
        isProcessingStatus(r.status),
    );
    saveUploadResults();
    if (pending.length) {
        pollTimer = setTimeout(
            () => pollStatus(pending.map((r) => r.name)),
            2000,
        );
    } else {
        uploadResults.value = uploadResults.value.filter((r) => {
            const stillInStore = documentStore.documents.some(
                (d) => d.title === r.name,
            );
            return !stillInStore;
        });
        saveUploadResults();
    }
}

async function handleUpload() {
    if (!selectedFiles.value.length) {
        return;
    }

    uploading.value = true;
    uploadResults.value = [];

    try {
        const results = await documentStore.uploadDocuments(
            selectedFiles.value,
        );
        uploadResults.value = results.map((r, i) => ({
            chunks: 0,
            message: r.message,
            name: selectedFiles.value[i]?.name || "Unknown",
            size: selectedFiles.value[i]?.size || 0,
            status: r.status === "ok" ? "pending" : "failed",
        }));
        selectedFiles.value = [];

        const indexed = uploadResults.value.filter((r) =>
            isProcessingStatus(r.status),
        );
        saveUploadResults();
        if (indexed.length) {
            pollTimer = setTimeout(
                () => pollStatus(indexed.map((r) => r.name)),
                2000,
            );
        }
    } catch {
        uploadResults.value = [
            {
                chunks: 0,
                message: documentStore.error || "Upload failed",
                name: "Upload",
                size: 0,
                status: "failed",
            },
        ];
    } finally {
        uploading.value = false;
    }
}

function handleTrashClick(item: ReturnType<typeof documentList.value>[number]) {
    if (item.isProcessing) {
        uploadResults.value = uploadResults.value.filter(
            (r) => r.name !== item.id,
        );
        saveUploadResults();
    } else {
        confirmDelete(item.title);
    }
}

function confirmDelete(title: string) {
    deleteTarget.value = title;
    showDeleteModal.value = true;
}

async function deleteDocument() {
    const title = deleteTarget.value;
    showDeleteModal.value = false;
    deleting.value = true;
    try {
        await documentStore.deleteDocument(title);
    } finally {
        deleting.value = false;
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
                            <UIcon
                                class="text-primary"
                                name="i-lucide-upload"
                            />
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
                        v-model="selectedFiles"
                    />

                    <div class="mt-4" v-if="selectedFiles.length">
                        <UButton
                            block
                            :disabled="!selectedFiles.length"
                            :loading="uploading"
                            @click="handleUpload"
                        >
                            Upload
                            {{ selectedFiles.length }}
                            file{{ selectedFiles.length > 1 ? "s" : "" }}
                        </UButton>
                    </div>

                    <div
                        class="mt-6 divide-y divide-default"
                        v-if="documentList.length"
                    >
                        <div
                            class="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                            v-for="item in documentList"
                            :key="item.id"
                        >
                            <UIcon
                                class="text-primary shrink-0"
                                name="i-lucide-file-text"
                            />
                            <div class="flex-1 min-w-0">
                                <p
                                    class="font-medium truncate flex items-center gap-1.5"
                                >
                                    {{ item.title }}
                                    <UBadge
                                        size="sm"
                                        variant="soft"
                                        v-if="item.status"
                                        :color="statusBadge(item.status).color"
                                    >
                                        {{ statusBadge(item.status).label }}
                                    </UBadge>
                                </p>
                                <p class="text-sm text-muted">
                                    {{ formatSize(item.size) }}
                                    <template v-if="item.chunks">
                                        ·
                                        {{ item.chunks }}
                                        chunk{{
                                            item.chunks === 1 ? "" : "s"
                                        }}</template
                                    >
                                </p>
                                <p
                                    class="text-xs text-(--ui-color-error) mt-1"
                                    v-if="
                                        item.status === 'failed' &&
                                        item.error_message
                                    "
                                >
                                    {{ item.error_message }}
                                </p>
                            </div>
                            <UButton
                                color="error"
                                icon="i-lucide-trash-2"
                                size="sm"
                                variant="ghost"
                                :loading="
                                    !item.isProcessing &&
                                    deleting &&
                                    deleteTarget === item.title
                                "
                                @click="handleTrashClick(item)"
                            />
                        </div>
                    </div>
                    <div
                        class="flex flex-col items-center justify-center py-8"
                        v-else
                    >
                        <UIcon
                            class="text-4xl text-muted mb-2"
                            name="i-lucide-file-text"
                        />
                        <p class="text-muted">No documents uploaded yet</p>
                    </div>
                </UCard>
            </div>
        </template>
    </UDashboardPanel>

    <UModal
        description="This action cannot be undone."
        title="Delete Document"
        v-model:open="showDeleteModal"
        :ui="{ footer: 'justify-end' }"
    >
        <template #footer="{ close }">
            <UButton
                color="neutral"
                label="Cancel"
                variant="outline"
                @click="close"
            />
            <UButton
                color="error"
                label="Delete"
                :loading="deleting"
                @click="deleteDocument"
            />
        </template>
    </UModal>
</template>
