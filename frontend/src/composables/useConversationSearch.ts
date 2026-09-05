import { computed, ref } from "vue";
import { useChatStore } from "../stores/chat";
import { useChats } from "./useChats";

// Search palette over real conversation links + hover-prefetch: warming the
// session under the cursor before the click lands. prefetchSession is a
// guarded no-op when cached or already in flight.
export function useConversationSearch() {
	const chatStore = useChatStore();
	const { groups } = useChats();
	const searchOpen = ref(false);

	// Search palette needs real links too (groups carry raw conversations without `to`)
	const searchGroups = computed(() => [
		{
			id: "links",
			items: [{ label: "New chat", to: "/", icon: "i-lucide-message-circle-plus" }],
		},
		...groups.value.map((g) => ({
			id: g.id,
			label: g.label,
			items: g.items.map((c) => ({
				id: c.id ?? c.sessionId,
				label: c.title ?? c.label,
				to: `/c/${c.id ?? c.sessionId}`,
				icon: "i-lucide-message-circle",
			})),
		})),
	]);

	// mouseover / focusin delegate on the menu (covers label, padding, trailing area).
	function prefetchFromEvent(e: Event) {
		const anchor = (e.target as HTMLElement | null)?.closest?.('a[href^="/c/"]');
		const id = anchor?.getAttribute("href")?.slice(3);
		if (id) void chatStore.prefetchSession(id);
	}

	return { prefetchFromEvent, searchGroups, searchOpen };
}
