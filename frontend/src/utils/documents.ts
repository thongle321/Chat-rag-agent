// Document indexing status presentation (pure — no Vue reactivity).

export type DocStatusColor = "warning" | "info" | "success" | "error";

export function statusBadge(status: string): { label: string; color: DocStatusColor } {
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

export function isProcessingStatus(status: string): boolean {
	return status === "pending" || status === "processing";
}
