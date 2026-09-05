import type { DropdownMenuItem } from "@nuxt/ui";
import { useChatStore } from "../stores/chat";

/**
 * Rename/delete with overlay toasts (template uses useOverlay + ModalRename/ModalConfirm;
 * for RAG we keep the same UI via UModal in the chat shell) plus the per-chat
 * dropdown menu items (pin / rename / delete) behind the trailing ellipsis.
 */
export function useChatActions() {
	const toast = useToast();
	const chatStore = useChatStore();

	async function renameChat(id: string, currentTitle: string | null, newTitle: string): Promise<string | null> {
		const title = newTitle.trim();
		if (!title || title === currentTitle) return null;
		try {
			chatStore.renameConversation(id, title);
			toast.add({ title: "Renamed", description: "Conversation renamed", icon: "i-lucide-pencil", color: "success" });
			return title;
		} catch {
			toast.add({ description: "Failed to rename chat", icon: "i-lucide-alert-circle", color: "error" });
			return null;
		}
	}

	async function deleteChat(id: string): Promise<boolean> {
		try {
			void chatStore.deleteConversation(id);
			toast.add({
				title: "Chat deleted",
				description: "Your chat has been deleted",
				icon: "i-lucide-trash",
				color: "success",
			});
			return true;
		} catch {
			toast.add({ description: "Failed to delete chat", icon: "i-lucide-alert-circle", color: "error" });
			return false;
		}
	}

	function conversationMenuItems(
		id: string,
		handlers: { onRename: (id: string) => void; onDelete: (id: string) => void },
	): DropdownMenuItem[][] {
		const pinned = !!chatStore.conversations.find((c) => c.id === id)?.pinned;
		return [
			[
				{
					label: pinned ? "Unpin" : "Pin",
					icon: pinned ? "i-lucide-pin-off" : "i-lucide-pin",
					onSelect: () => chatStore.togglePin(id),
				},
			],
			[
				{
					label: "Rename",
					icon: "i-lucide-pencil",
					onSelect: () => handlers.onRename(id),
				},
			],
			[
				{
					label: "Delete",
					icon: "i-lucide-trash",
					color: "error" as const,
					onSelect: () => handlers.onDelete(id),
				},
			],
		];
	}

	return { conversationMenuItems, deleteChat, renameChat };
}
