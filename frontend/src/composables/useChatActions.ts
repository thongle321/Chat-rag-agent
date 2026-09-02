import { useChats } from "./useChats";

/**
 * Mirrors nuxt-ui-templates/chat-vue/src/composables/useChatActions.ts
 * Provides rename/delete with overlay modals (template uses useOverlay + ModalRename/ModalConfirm).
 * For RAG we keep same UI (UModal in ChatSidebar) but expose composable actions for reuse.
 */
export function useChatActions() {
  const toast = useToast();
  const { updateChat, removeChat } = useChats();

  async function renameChat(id: string, currentTitle: string | null, newTitle: string): Promise<string | null> {
    const title = newTitle.trim();
    if (!title || title === currentTitle) return null;
    try {
      updateChat(id, { label: title });
      toast.add({ title: "Renamed", description: "Conversation renamed", icon: "i-lucide-pencil", color: "success" });
      return title;
    } catch {
      toast.add({ description: "Failed to rename chat", icon: "i-lucide-alert-circle", color: "error" });
      return null;
    }
  }

  async function deleteChat(id: string): Promise<boolean> {
    try {
      removeChat(id);
      toast.add({ title: "Chat deleted", description: "Your chat has been deleted", icon: "i-lucide-trash", color: "success" });
      return true;
    } catch {
      toast.add({ description: "Failed to delete chat", icon: "i-lucide-alert-circle", color: "error" });
      return false;
    }
  }

  return { renameChat, deleteChat };
}
