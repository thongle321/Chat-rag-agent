import { defineStore } from "pinia";
import { computed, ref } from "vue";
import api, {
	getErrorMessage,
	type StreamSource,
	streamChat,
} from "../api/index.ts";

const STORAGE_PREFIX = "chat_sessions";
const ACTIVE_PREFIX = "chat_active_id";
// Identity bucket: "anon" or "user:<id>". Guests only ever see the anon
// bucket — account sessions are invisible after logout and restored on login.

export interface ChatMessage {
	id: string;
	model?: string;
	role: "user" | "assistant";
	sources?: StreamSource[];
	products?: import("../api/index.ts").StreamProduct[];
	followups?: string[];
	streaming?: boolean;
	text: string;
}

export interface Conversation {
	createdAt: number;
	id: string;
	messages: ChatMessage[];
	pinned: boolean;
	sessionId: string;
	title: string;
}

export function groupByDate(
	conversations: Conversation[],
): [string, Conversation[]][] {
	const now = Date.now();
	const day = 86_400_000;
	const groups = new Map<string, Conversation[]>();
	const label = (d: number) => {
		const diff = now - d;
		if (diff < day) {
			return "Today";
		}
		if (diff < 2 * day) {
			return "Yesterday";
		}
		if (diff < 7 * day) {
			return "7 days ago";
		}
		if (diff < 30 * day) {
			return "30 days ago";
		}
		return "Older";
	};
	for (const c of conversations) {
		const l = label(c.createdAt);
		const arr = groups.get(l) ?? [];
		arr.push(c);
		groups.set(l, arr);
	}
	return [...groups.entries()];
}

export const useChatStore = defineStore("chat", () => {
	const conversations = ref<Conversation[]>([]);
	const activeId = ref("");
	const identity = ref("anon");
	const storageKey = () => `${STORAGE_PREFIX}:${identity.value}`;
	const activeStorageKey = () => `${ACTIVE_PREFIX}:${identity.value}`;
	const loading = ref(false);
	const error = ref("");
	// Sessions currently hydrating over network (drives the skeleton + dedupes
	// hover-prefetch vs click so one session is never fetched twice).
	const hydrating = ref<Record<string, boolean>>({});
	// One AbortController per in-flight send, keyed by conversation id, so switching
	// chats never aborts a running stream — it keeps streaming in the background.
	const activeControllers = new Map<string, AbortController>();

	const activeConversation = computed(
		() => conversations.value.find((c) => c.id === activeId.value) ?? null,
	);

	const messages = computed(() => activeConversation.value?.messages ?? []);

	const streamingText = computed(
		() =>
			activeConversation.value?.messages.find((m) => m.streaming)?.text ?? "",
	);

	function saveToStorage() {
		// Logged-out = temporary chat: in-memory only, never persisted.
		if (identity.value === "anon") {
			return;
		}
		const data = conversations.value.map((c) => ({
			createdAt: c.createdAt,
			id: c.id,
			pinned: c.pinned,
			sessionId: c.sessionId,
			title: c.title,
		}));
		localStorage.setItem(storageKey(), JSON.stringify(data));
		localStorage.setItem(activeStorageKey(), activeId.value);
	}

	// Guests keep nothing: drop pre-bucket keys and any anon-bucket keys
	// (the old migration copied account sessions into anon). Idempotent —
	// self-heals browsers carrying leaked data.
	function cleanupGuestKeys() {
		try {
			for (const k of [STORAGE_PREFIX, ACTIVE_PREFIX, `${STORAGE_PREFIX}:anon`, `${ACTIVE_PREFIX}:anon`]) {
				localStorage.removeItem(k);
			}
		} catch {
			// storage unavailable
		}
	}

	function loadFromStorage() {
		cleanupGuestKeys();
		try {
			const raw = localStorage.getItem(storageKey());
			if (!raw) {
				return;
			}
			conversations.value = JSON.parse(raw).map((s: any) => ({
				createdAt: s.createdAt,
				id: s.id,
				messages: [],
				pinned: s.pinned,
				sessionId: s.sessionId || s.id,
				title: s.title,
			}));
		} catch {
			// corrupted storage
		}
		// Restore the chat you were viewing; fall back to the first session.
		const stored = localStorage.getItem(activeStorageKey()) || "";
		if (stored && conversations.value.some((c) => c.id === stored)) {
			activeId.value = stored;
		}
	}

	// Switch identity bucket (login/logout). Persists the outgoing bucket,
	// drops in-memory messages (guest must never see account content),
	// loads the incoming bucket.
	function switchIdentity(next: string) {
		if (next === identity.value) {
			return;
		}
		saveToStorage();
		identity.value = next;
		conversations.value = [];
		activeId.value = "";
		loadFromStorage();
	}

	// Sidebar source after login: the account's server-side sessions.
	// Server wins (titles/pins synced via PATCH); blank local drafts dropped.
	async function loadServerSessions() {
		const { data } = await api.get("/chat/sessions");
		conversations.value = (data || []).map((s: any) => ({
			createdAt: s.created_at ? Date.parse(s.created_at) : Date.now(),
			id: s.id,
			messages: [],
			pinned: !!s.pinned,
			sessionId: s.id,
			title: s.title || "Chat",
		}));
		if (activeId.value && !conversations.value.some((c) => c.id === activeId.value)) {
			activeId.value = "";
		}
		saveToStorage();
	}

	// Best-effort meta sync (rename/pin) — local save already happened.
	function syncSessionMeta(conv: Conversation) {
		if (identity.value === "anon") {
			return;
		}
		const sid = conv.sessionId || conv.id;
		if (!sid) {
			return;
		}
		void api.patch(`/chat/sessions/${sid}`, { title: conv.title, pinned: conv.pinned }).catch(() => {});
	}

	// Cache in-memory conversations across route changes (/ ↔ /c/:id remounts
	// pages) so an in-flight stream is never wiped by a reload from storage.
	async function fetchSessions() {
		if (!conversations.value.length) {
			loadFromStorage();
		}
		if (!activeId.value && conversations.value.length) {
			activeId.value = conversations.value[0].id;
		}
		// Restore the chat you were in before refresh — messages (and hydrated sources).
		await prefetchSession(activeId.value);
	}

	// Warm an uncached session (hover/focus prefetch). No-op when cached or
	// already in flight — safe to call from mouseover/focusin repeatedly.
	async function prefetchSession(id: string) {
		const conv = conversations.value.find((c) => c.id === id);
		if (!conv || conv.messages.length || hydrating.value[id]) {
			return;
		}
		hydrating.value[id] = true;
		try {
			await fetchSessionMessages(id);
		} finally {
			hydrating.value[id] = false;
		}
	}

	async function fetchSessionMessages(id: string) {
		try {
			const { data } = await api.get(`/chat/sessions/${id}`);
			const conv = conversations.value.find((c) => c.id === id);
			if (!conv) {
				return;
			}
			conv.messages = (data.messages || []).map((m: any, i: number) => ({
				id: String(i),
				role: m.role === "user" ? "user" : "assistant",
				sources: m.sources ?? undefined,
				text: m.content,
			}));
		} catch {
			// ignore
		}
	}

	function newConversation() {
		const id = String(Date.now());
		conversations.value.unshift({
			createdAt: Date.now(),
			id,
			messages: [],
			pinned: false,
			sessionId: "",
			title: "New chat",
		});
		activeId.value = id;
		saveToStorage();
	}

	// Blank composer for / — clears the selection without creating an entry
	// (a conversation is created on first send, like ChatGPT).
	function clearActive() {
		activeId.value = "";
		saveToStorage();
	}

	// Validate a /c/:id against local list, then the server (fresh device /
	// cleared storage). Hydrates a local entry so direct loads work.
	async function resolveSession(id: string): Promise<boolean> {
		let conv = conversations.value.find((c) => c.id === id);
		if (!conv) {
			try {
				await api.get(`/chat/sessions/${id}`);
			} catch {
				return false;
			}
			conversations.value.unshift({
				createdAt: Date.now(),
				id,
				messages: [],
				pinned: false,
				sessionId: id,
				title: "Chat",
			});
			saveToStorage();
		}
		await setActive(id);
		conv = conversations.value.find((c) => c.id === id);
		if (conv && conv.title === "Chat") {
			const first = conv.messages.find((m) => m.role === "user");
			if (first?.text) {
				conv.title = first.text.slice(0, 60);
				saveToStorage();
			}
		}
		return true;
	}

	async function setActive(id: string) {
		activeId.value = id;
		saveToStorage();
		// Same guarded path as hover-prefetch: instant when warm, skeleton
		// while cold (covers touch devices and clicks that beat the hover).
		await prefetchSession(id);
	}

	async function deleteConversation(id: string) {
		activeControllers.get(id)?.abort();
		activeControllers.delete(id);
		const conv = conversations.value.find((c) => c.id === id);
		const serverId = conv?.sessionId;
		if (serverId) {
			try {
				await api.delete(`/chat/sessions/${serverId}`);
			} catch {
				// idempotent delete — ignore 404/race
			}
		}
		conversations.value = conversations.value.filter((c) => c.id !== id);
		if (activeId.value === id) {
			activeId.value = conversations.value[0]?.id ?? "";
		}
		saveToStorage();
	}

	function togglePin(id: string) {
		const c = conversations.value.find((c) => c.id === id);
		if (!c) {
			return;
		}
		c.pinned = !c.pinned;
		saveToStorage();
		syncSessionMeta(c);
	}

	function renameConversation(id: string, title: string) {
		const c = conversations.value.find((c) => c.id === id);
		if (!c) {
			return;
		}
		c.title = title;
		saveToStorage();
		syncSessionMeta(c);
	}

	async function sendMessage(question: string) {
		if (!question.trim()) {
			return;
		}

		if (!activeId.value) {
			newConversation();
		}

		const conv = conversations.value.find((c) => c.id === activeId.value);
		if (!conv) {
			return;
		}

		conv.messages.push({
			id: String(Date.now()),
			role: "user",
			text: question,
		});

		if (conv.messages.length === 1) {
			conv.title = question.slice(0, 60);
		}

		conv.messages.push({
			id: "streaming",
			role: "assistant",
			streaming: true,
			text: "",
		});
		const streamMsg = conv.messages.at(-1) as ChatMessage;

		error.value = "";
		loading.value = true;

		const ctrl = new AbortController();
		const key = conv.id;
		activeControllers.set(key, ctrl);
		try {
			await streamChat(
				question,
				conv.sessionId || undefined,
				{
					onDelta: (content) => {
						streamMsg.text += content;
					},
					onDone: (data) => {
						// If first message, session_id is now set — update the id to match server
						if (!conv.sessionId) {
							conv.sessionId = data.session_id;
							const oldId = conv.id;
							conv.id = data.session_id;
							if (activeId.value === oldId) {
								activeId.value = data.session_id;
							}
							const c = activeControllers.get(oldId);
							if (c) {
								activeControllers.delete(oldId);
								activeControllers.set(data.session_id, c);
							}
						}
						streamMsg.id = String(Date.now());
						streamMsg.model = data.model;
						streamMsg.streaming = false;
					},
					onError: (detail) => {
						error.value = detail;
					},
					onSources: (sources) => {
						streamMsg.sources = sources;
					},
					onProducts: (products) => {
						streamMsg.products = products;
					},
					onFollowups: (followups) => {
						streamMsg.followups = followups;
					},
				},
				ctrl.signal,
			);
		} catch (err: any) {
			if (err?.name !== "AbortError") {
				error.value = getErrorMessage(err);
			}
		} finally {
			loading.value = false;
			activeControllers.delete(key);
			streamMsg.streaming = false;
			if (!streamMsg.text) {
				conv.messages = conv.messages.filter((m) => m !== streamMsg);
			}
			saveToStorage();
		}
	}

	function stop() {
		activeControllers.get(activeId.value)?.abort();
	}

	return {
		activeConversation,
		activeId,
		clearActive,
		conversations,
		deleteConversation,
		error,
		fetchSessionMessages,
		fetchSessions,
		hydrating,
		identity,
		loading,
		loadServerSessions,
		messages,
		newConversation,
		prefetchSession,
		renameConversation,
		resolveSession,
		sendMessage,
		setActive,
		stop,
		streamingText,
		switchIdentity,
		togglePin,
	};
});
