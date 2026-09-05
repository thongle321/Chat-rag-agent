import { computed, onMounted, onUnmounted, ref } from "vue";
import api from "../api/index.ts";
import { useDocumentStore } from "../stores/documents";
import { isProcessingStatus } from "../utils/documents";

export interface ProcessingDoc {
	name: string;
	status: string;
	message: string;
	size: number;
	chunks: number;
	error_message?: string;
}

const STORAGE_KEY = "upload-results";

// Upload queue + background indexing poll + delete flow. The store owns the
// persisted document list; this owns the transient upload session state.
export function useDocumentUploads() {
	const documentStore = useDocumentStore();
	const selectedFiles = ref<File[]>([]);
	const uploading = ref(false);
	const uploadResults = ref<ProcessingDoc[]>([]);
	const deleting = ref(false);
	const deleteTarget = ref("");
	const deleteOpen = ref(false);
	let pollTimer: number | undefined;

	function saveUploadResults() {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(uploadResults.value));
	}

	function loadUploadResults() {
		const stored = sessionStorage.getItem(STORAGE_KEY);
		if (!stored) return;
		try {
			uploadResults.value = JSON.parse(stored);
		} catch {
			uploadResults.value = [];
		}
	}

	const documentList = computed(() => {
		const storeDocs = documentStore.documents;
		const storeNames = new Set(storeDocs.map((d) => d.title));
		const processing = uploadResults.value.filter((r) => !storeNames.has(r.name) && r.status !== "completed");
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
				const uploadResult = uploadResults.value.find((r) => r.name === d.title);
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

	async function pollStatus(titles: string[]) {
		if (!titles.length) return;
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
		const pending = uploadResults.value.filter((r) => isProcessingStatus(r.status));
		saveUploadResults();
		if (pending.length) {
			pollTimer = setTimeout(() => pollStatus(pending.map((r) => r.name)), 2000);
		} else {
			uploadResults.value = uploadResults.value.filter((r) => {
				const stillInStore = documentStore.documents.some((d) => d.title === r.name);
				return !stillInStore;
			});
			saveUploadResults();
		}
	}

	async function handleUpload() {
		if (!selectedFiles.value.length) return;
		uploading.value = true;
		uploadResults.value = [];
		try {
			const results = await documentStore.uploadDocuments(selectedFiles.value);
			uploadResults.value = results.map((r, i) => ({
				chunks: 0,
				message: r.message,
				name: selectedFiles.value[i]?.name || "Unknown",
				size: selectedFiles.value[i]?.size || 0,
				status: r.status === "ok" ? "pending" : "failed",
			}));
			selectedFiles.value = [];
			const indexed = uploadResults.value.filter((r) => isProcessingStatus(r.status));
			saveUploadResults();
			if (indexed.length) {
				pollTimer = setTimeout(() => pollStatus(indexed.map((r) => r.name)), 2000);
			}
		} catch {
			uploadResults.value = [
				{ chunks: 0, message: documentStore.error || "Upload failed", name: "Upload", size: 0, status: "failed" },
			];
		} finally {
			uploading.value = false;
		}
	}

	function handleTrashClick(item: { isProcessing: boolean; id: string; title: string }) {
		if (item.isProcessing) {
			uploadResults.value = uploadResults.value.filter((r) => r.name !== item.id);
			saveUploadResults();
		} else {
			deleteTarget.value = item.title;
			deleteOpen.value = true;
		}
	}

	async function deleteDocument() {
		const title = deleteTarget.value;
		deleteOpen.value = false;
		deleting.value = true;
		try {
			await documentStore.deleteDocument(title);
		} finally {
			deleting.value = false;
		}
	}

	onMounted(() => {
		documentStore.fetchDocuments();
		loadUploadResults();
		const indexed = uploadResults.value.filter((r) => isProcessingStatus(r.status));
		if (indexed.length) {
			pollTimer = setTimeout(() => pollStatus(indexed.map((r) => r.name)), 2000);
		}
	});

	onUnmounted(() => {
		if (pollTimer) clearTimeout(pollTimer);
	});

	return {
		deleteDocument,
		deleteOpen,
		deleteTarget,
		deleting,
		documentList,
		handleTrashClick,
		handleUpload,
		selectedFiles,
		uploading,
	};
}
