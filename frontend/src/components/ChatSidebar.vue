<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useChatActions } from "../composables/useChatActions";
import { useChats } from "../composables/useChats";
import { useConversationSearch } from "../composables/useConversationSearch";
import { useDocCount } from "../composables/useDocCount";
import { useAuthStore } from "../stores/auth";
import { useChatStore } from "../stores/chat";
import RenameConversationModal from "./chat/RenameConversationModal.vue";
import SidebarUserMenu from "./chat/SidebarUserMenu.vue";

const props = defineProps<{
	onNavigate?: () => void;
}>();

const chatStore = useChatStore();
const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();
const { groups } = useChats();
const { conversationMenuItems, deleteChat, renameChat } = useChatActions();
const { prefetchFromEvent, searchGroups, searchOpen } = useConversationSearch();
const { docCount } = useDocCount();

const sidebarOpen = defineModel<boolean>("open", { default: true });

function handleNew() {
	// / is always a blank composer (ChatView clears the selection) — no entry
	// is created until the first message is sent, like ChatGPT.
	router.push("/");
}

function handleDelete(id: string) {
	deleteChat(id);
	// replace: don't leave the deleted /c/:id in history
	if ((route.params as any)?.id === id) router.replace("/");
}

const renameModalOpen = ref(false);
const renameId = ref<string | null>(null);
const renameTitle = ref("");

function handleRename(id: string) {
	const conv = chatStore.conversations.find((c) => c.id === id);
	renameId.value = id;
	renameTitle.value = conv?.title ?? "";
	renameModalOpen.value = true;
}
function confirmRename(newTitle: string) {
	if (renameId.value) {
		renameChat(renameId.value, chatStore.conversations.find((c) => c.id === renameId.value)?.title ?? null, newTitle);
	}
	renameId.value = null;
}

async function handleLogout() {
	await authStore.logout();
	// Chat is public — land on a blank composer, never the login page.
	// (ChatView clears the selection on / mount.)
	if (route.path !== "/") await router.push("/");
}

// Same items as chat-vue default.vue but using our icon library (i-lucide-*)
const navItems = computed(() => [
	{
		label: "New chat",
		to: "/",
		kbds: ["meta", "o"],
		icon: "i-lucide-circle-plus",
		onSelect: () => handleNew(),
	},
	{
		label: "Search",
		icon: "i-lucide-search",
		kbds: ["meta", "k"],
		onSelect: () => (searchOpen.value = true),
	},
]);

const chatItems = computed(() =>
	groups.value.flatMap((group) => [
		{ label: group.label, type: "label" as const },
		...group.items.map((item: any) => {
			const conv = chatStore.conversations.find((c) => c.id === item.id);
			const pinned = !!conv?.pinned;
			return {
				id: item.id,
				label: item.title ?? item.label,
				// Real link (not onSelect-push): single click, middle-click/tab support,
				// free active highlight. /c/:id page sets the active session.
				to: `/c/${item.id}`,
				slot: "chat" as const,
				icon: pinned ? "i-lucide-pin" : undefined,
				class: pinned ? "font-medium text-primary" : (item.title ?? item.label) === "Untitled" ? "text-muted" : "",
				onSelect: () => {
					props.onNavigate?.(); // close sidebar on mobile
				},
			};
		}),
	]),
);

defineShortcuts({
	meta_o: () => handleNew(),
	meta_k: () => (searchOpen.value = true),
});
</script>

<template>
  <!-- Replicate chat-vue/src/layouts/default.vue sidebar UI/UX, keep user menu + color + backend feature -->
  <UDashboardSidebar id="chat-sidebar" v-model:open="sidebarOpen" :min-size="12" collapsible resizable class="border-r-0 py-4 bg-elevated">
    <template #header="{ collapsed }">
      <ULink v-if="!collapsed" to="/" class="flex items-center gap-0.5 outline-primary/25 focus-visible:outline-3 rounded-md">
        <div class="flex items-center justify-center size-7 rounded-lg bg-primary/10">
          <UIcon name="i-lucide-bot" class="size-4 text-primary" />
        </div>
        <span class="text-lg font-bold text-highlighted ml-1">VeilAi Rag</span>
      </ULink>
      <UDashboardSidebarCollapse class="ms-auto" />
    </template>

    <template #default="{ collapsed }">
      <UNavigationMenu :items="navItems" :collapsed="collapsed" orientation="vertical">
        <template #item-trailing="{ item }">
          <div v-if="(item as any).kbds?.length" class="flex items-center gap-px opacity-0 group-hover:opacity-100 transition-opacity">
            <UKbd v-for="kbd in (item as any).kbds" :key="kbd" :value="kbd" size="sm" variant="soft" class="bg-accented/50" />
          </div>
        </template>
      </UNavigationMenu>

      <!-- Backend feature: doc count -->
      <div v-if="!collapsed && docCount !== null" class="px-2 py-2">
        <div class="flex items-center gap-1.5 px-2 text-[11px]" :class="docCount > 0 ? 'text-success' : 'text-warning'">
          <UIcon :name="docCount > 0 ? 'i-lucide-database' : 'i-lucide-alert-circle'" class="size-3.5" />
          <span>{{ docCount > 0 ? `${docCount} docs indexed` : "No docs — upload in admin" }}</span>
        </div>
      </div>

      <UNavigationMenu
        v-if="!collapsed"
        :items="chatItems"
        :collapsed="collapsed"
        orientation="vertical"
        :ui="{
          link: 'overflow-hidden pr-7.5',
          linkTrailing: 'translate-x-full group-hover:translate-x-0 group-has-data-[state=open]:translate-x-0 transition-transform ms-0 absolute inset-e-px',
        }"
        @mouseover="prefetchFromEvent"
        @focusin="prefetchFromEvent"
      >
        <template #chat-trailing="{ item }">
          <UDropdownMenu :items="conversationMenuItems((item as { id: string }).id, { onRename: handleRename, onDelete: handleDelete })" :content="{ align: 'end' }">
            <UButton
              as="div"
              icon="i-lucide-ellipsis"
              color="neutral"
              variant="link"
              size="sm"
              class="rounded-[5px] hover:bg-accented/50 focus-visible:bg-accented/50 data-[state=open]:bg-accented/50"
              aria-label="Chat actions"
              tabindex="-1"
              @click.stop.prevent
            />
          </UDropdownMenu>
        </template>
      </UNavigationMenu>
    </template>

    <template #footer="{ collapsed }">
      <!-- Keep user menu and color like before -->
      <SidebarUserMenu :collapsed="collapsed" @logout="handleLogout" />
    </template>
  </UDashboardSidebar>

  <UDashboardSearch v-model:open="searchOpen" placeholder="Search chats..." :groups="searchGroups" />

  <RenameConversationModal v-model:open="renameModalOpen" :initial-title="renameTitle" @submit="confirmRename" />
</template>
