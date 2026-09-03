import axios from "axios";

const api = axios.create({
	baseURL: import.meta.env.VITE_API_URL || "/api",
	timeout: 180_000,
});

// Always attach JWT from localStorage — survives hard refresh / HMR where
// api.defaults.headers.common may have been reset even though token is stored
api.interceptors.request.use((config) => {
	const t = localStorage.getItem("auth_token");
	if (t && !config.headers.Authorization) {
		config.headers.Authorization = `Bearer ${t}`;
	}
	return config;
});

api.interceptors.response.use(
	(res) => res,
	(err) => {
		const status = err?.response?.status;
		const detail: string = err?.response?.data?.detail || "";
		// "/" and "/c/:id" are public like ChatGPT — never auto-redirect from
		// background 401s (e.g. /documents docCount)
		const path = window.location.pathname;
		const isPublic = path === "/" || path.startsWith("/c/") || path === "/login" || path.startsWith("/admin/login");
		if (status === 401) {
			if (!isPublic) {
				localStorage.removeItem("auth_token");
				window.location.href = path.startsWith("/admin") ? "/admin/login" : "/login";
			}
		} else if (status === 403) {
			// Strict role separation: admin→user or user→admin via direct API/URL
			if (detail.includes("Admin cannot access user chat")) {
				// Admin tried to use user chat — send to admin dashboard, keep token (still admin)
				if (!window.location.pathname.startsWith("/admin")) window.location.href = "/admin/";
			} else if (detail.includes("Admin only")) {
				// User tried to hit admin API — send to user login
				if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
			}
		}
		return Promise.reject(err);
	},
);

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

export interface StreamProduct {
	id: string;
	name: string;
	description?: string | null;
	price?: number | null;
	currency?: string;
	image_url?: string | null;
	product_url?: string | null;
	category?: string | null;
	stock?: number;
}

export interface StreamHandlers {
	onDelta: (content: string) => void;
	onDone: (data: { session_id: string; model: string }) => void;
	onError: (detail: string) => void;
	onSources?: (sources: StreamSource[]) => void;
	onProducts?: (products: StreamProduct[]) => void;
	onFollowups?: (followups: string[]) => void;
}

export async function streamChat(
	question: string,
	sessionId: string | undefined,
	handlers: StreamHandlers,
	signal: AbortSignal,
): Promise<void> {
	const headers: Record<string, string> = { "Content-Type": "application/json" };
	// Forward JWT so backend can fill user_id/user_email like CQA activity_logs (axios does this automatically, fetch does not)
	const token = localStorage.getItem("auth_token");
	if (token) headers.Authorization = `Bearer ${token}`;
	const response = await fetch(`${api.defaults.baseURL}/chat/query/stream`, {
		body: JSON.stringify({ question, session_id: sessionId }),
		headers,
		method: "POST",
		signal,
	});
	if (!(response.ok && response.body)) {
		if (response.status === 401) {
			localStorage.removeItem("auth_token");
			window.location.href = "/login";
			handlers.onError("Please log in to chat");
			return;
		}
		if (response.status === 403) {
			let detail403 = "Forbidden";
			try {
				const b = await response.clone().json();
				if (b?.detail) detail403 = typeof b.detail === "string" ? b.detail : detail403;
			} catch {}
			if (detail403.includes("Admin cannot access")) window.location.href = "/admin/";
			handlers.onError(detail403);
			return;
		}
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
			} else if (currentEvent === "products") {
				handlers.onProducts?.(data.products ?? []);
			} else if (currentEvent === "followups") {
				handlers.onFollowups?.(data.followups ?? []);
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
