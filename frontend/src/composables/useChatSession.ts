import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useChatStore } from "../stores/chat";

// Session lifecycle for the shared chat surface: route bootstrap
// (fetch/resolve/clear → ready or not-found) plus send-and-route
// (first send from blank / jumps to the session URL like ChatGPT).
export function useChatSession(sessionId: () => string | null, temporary: boolean, onNotFound: () => void) {
	const chatStore = useChatStore();
	const authStore = useAuthStore();
	const router = useRouter();
	const ready = ref(false);
	const chatInput = ref("");

	async function bootstrap() {
		await chatStore.fetchSessions();
		const id = sessionId();
		if (id) {
			if (temporary) {
				// Guest temp route: local memory only, never the server (reload = gone).
				if (chatStore.conversations.some((c) => c.id === id)) {
					await chatStore.setActive(id);
				} else {
					onNotFound(); // reload/direct visit → parent redirects to /
					return;
				}
			} else if (!(await chatStore.resolveSession(id))) {
				// Local list first, then server (fresh device / cleared storage)
				onNotFound(); // unknown/deleted id → parent redirects to /
				return;
			}
		} else {
			// / is always a blank composer — never restore the last session here
			chatStore.clearActive();
		}
		ready.value = true;
	}

	async function handleSend(question: string) {
		try {
			await chatStore.sendMessage(question);
		} catch {
			// error is already displayed via chatStore.error
		}
		// First send from the blank / composer → jump to the session URL.
		// Failed before a server session existed → drop the phantom so / stays blank.
		if (!sessionId()) {
			const conv = chatStore.activeConversation;
			if (conv && !conv.sessionId) {
				if (chatStore.error) {
					await chatStore.deleteConversation(conv.id);
					chatStore.clearActive();
				}
			} else if (conv?.sessionId) {
				// Guests get temporary /uc/:id URLs (in-memory only); accounts get /c/:id.
				router.push(authStore.isAuthenticated ? `/c/${conv.sessionId}` : `/uc/${conv.sessionId}`);
			}
		}
	}

	return { bootstrap, chatInput, handleSend, ready };
}
