import axios from "axios";

const api = axios.create({
	baseURL: import.meta.env.VITE_API_URL || "/api",
	timeout: 180_000,
});

export function getErrorMessage(err: unknown): string {
	if (!axios.isAxiosError(err)) {
		return err instanceof Error ? err.message : "An error occurred";
	}
	const detail = err.response?.data?.detail;
	if (typeof detail === "string") {
		return detail;
	}
	if (Array.isArray(detail)) {
		return detail
			.map((d: { msg?: string }) => d.msg ?? "")
			.filter(Boolean)
			.join("; ");
	}
	return err.message || "An error occurred";
}

export interface StreamSource {
	n: number;
	pages?: number[];
	reference?: string | null;
	title: string;
}

export interface StreamHandlers {
	onDelta: (content: string) => void;
	onDone: (data: { session_id: string; model: string }) => void;
	onError: (detail: string) => void;
	onSources?: (sources: StreamSource[]) => void;
}

export async function streamChat(
	question: string,
	sessionId: string | undefined,
	handlers: StreamHandlers,
	signal: AbortSignal,
): Promise<void> {
	const response = await fetch(`${api.defaults.baseURL}/chat/query/stream`, {
		body: JSON.stringify({ question, session_id: sessionId }),
		headers: { "Content-Type": "application/json" },
		method: "POST",
		signal,
	});
	if (!(response.ok && response.body)) {
		let detail = `HTTP ${response.status}`;
		try {
			const body = await response.json();
			if (body?.detail) {
				detail =
					typeof body.detail === "string" ? body.detail : getErrorMessage(body);
			}
		} catch {
			/* non-JSON body */
		}
		handlers.onError(detail);
		return;
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = "";
	let currentEvent = "message";
	while (true) {
		const { done, value } = await reader.read();
		if (done) {
			break;
		}
		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split("\n");
		buffer = lines.pop() || "";
		for (const raw of lines) {
			const line = raw.trimEnd();
			if (!line) {
				currentEvent = "message";
				continue;
			}
			if (line.startsWith("event: ")) {
				currentEvent = line.slice(7).trim();
				continue;
			}
			if (!line.startsWith("data: ")) {
				continue;
			}
			let data: any;
			try {
				data = JSON.parse(line.slice(6));
			} catch {
				continue;
			}
			if (currentEvent === "sources") {
				handlers.onSources?.(data.sources ?? []);
			} else if (currentEvent === "error") {
				handlers.onError(data.detail ?? "Unknown error");
			} else if (currentEvent === "done") {
				handlers.onDone({ model: data.model, session_id: data.session_id });
			} else {
				handlers.onDelta(data.content ?? "");
			}
			if (
				currentEvent === "sources" ||
				currentEvent === "error" ||
				currentEvent === "done"
			) {
				currentEvent = "message";
			}
		}
	}
}

export default api;
