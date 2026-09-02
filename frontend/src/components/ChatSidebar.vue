<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import type { DropdownMenuItem } from "@nuxt/ui";
import { useChatStore, type Conversation } from "../stores/chat";
import { useAuthStore } from "../stores/auth";
import { useChats } from "../composables/useChats";
import { useChatActions } from "../composables/useChatActions";
import api from "../api/index.ts";

const props = defineProps<{
  onCollapse?: () => void;
  onNavigate?: () => void;
}>();

const chatStore = useChatStore();
const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();
const { groups, fetchChats } = useChats();
const { renameChat, deleteChat } = useChatActions();

const sidebarOpen = defineModel<boolean>("open", { default: true });
const searchOpen = ref(false);

const search = ref("");
// Keep filtered search for UDashboardSearch (template uses UDashboardSearch with groups)
const filteredGroups = computed(() => {
  const s = search.value.trim().toLowerCase();
  if (!s) return groups.value;
  const filtered = chatStore.conversations.filter((c) => c.title.toLowerCase().includes(s)).map((c) => ({
    id: c.id,
    label: c.title,
    to: "#",
    icon: "i-lucide-message-circle",
    createdAt: String(c.createdAt),
  }));
  return filtered.length ? [{ id: "search", label: `Results (${filtered.length})`, items: filtered as any }] : [];
});

// Backend feature-aware: doc count
const docCount = ref<number | null>(null);
onMounted(async () => {
  try {
    const { data } = await api.get("/documents");
    docCount.value = data?.documents?.length ?? 0;
  } catch {
    docCount.value = null;
  }
});

watch(() => chatStore.conversations.length, () => {
  // keep groups in sync if needed
});

function handleNew() {
  chatStore.newConversation();
  // template does router.push('/') for new chat — we stay on /
}

function handleDelete(id: string) {
  deleteChat(id);
  if ((route.params as any)?.id === id) router.push("/");
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
function confirmRename() {
  if (renameId.value && renameTitle.value.trim()) {
    renameChat(renameId.value, chatStore.conversations.find((c) => c.id === renameId.value)?.title ?? null, renameTitle.value.trim());
  }
  renameModalOpen.value = false;
}

function getChatActions(item: { id: string; label: string }): DropdownMenuItem[][] {
  const conv = chatStore.conversations.find((c) => c.id === item.id);
  const pinned = !!conv?.pinned;
  return [
    [{ label: pinned ? "Unpin" : "Pin", icon: pinned ? "i-lucide-pin-off" : "i-lucide-pin", onSelect: () => chatStore.togglePin(item.id) }],
    [{ label: "Rename", icon: "i-lucide-pencil", onSelect: () => handleRename(item.id) }],
    [{ label: "Delete", icon: "i-lucide-trash", color: "error" as const, onSelect: () => handleDelete(item.id) }],
  ];
}

// Keep color and user menu like before (our backend feature)
const colorMode = useColorMode();
async function handleLogout() {
  await authStore.logout();
  router.push("/login");
}
const userMenuItems = computed(() => [
  [{ label: authStore.user?.email ?? "Guest", type: "label" as const, icon: "i-lucide-user" }],
  [
    {
      label: "Appearance",
      icon: "i-lucide-sun-moon",
      children: [
        {
          label: "Light",
          icon: "i-lucide-sun",
          type: "checkbox" as const,
          checked: colorMode.value === "light",
          onSelect(e: Event) {
            e.preventDefault();
            colorMode.value = "light";
          },
        },
        {
          label: "Dark",
          icon: "i-lucide-moon",
          type: "checkbox" as const,
          checked: colorMode.value === "dark",
          onUpdateChecked(checked: boolean) {
            if (checked) colorMode.value = "dark";
          },
          onSelect(e: Event) {
            e.preventDefault();
          },
        },
      ],
    },
  ],
  [{ label: authStore.user ? "Logout" : "Login", icon: authStore.user ? "i-lucide-log-out" : "i-lucide-log-in", onSelect: () => (authStore.user ? handleLogout() : router.push("/login")) }],
]);

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
        to: undefined,
        slot: "chat" as const,
        icon: pinned ? "i-lucide-pin" : undefined,
        class: pinned ? "font-medium text-primary" : (item.title ?? item.label) === "Untitled" ? "text-muted" : "",
        onSelect: () => {
          chatStore.setActive(item.id);
          props.onNavigate?.();
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
  <UDashboardSidebar
    id="chat-sidebar"
    v-model:open="sidebarOpen"
    :min-size="12"
    collapsible
    resizable
    class="border-r-0 py-4 bg-elevated"
  >
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
      <UNavigationMenu
        :items="navItems"
        :collapsed="collapsed"
        orientation="vertical"
      >
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
          <span>{{ docCount > 0 ? `${docCount} docs indexed` : 'No docs — upload in admin' }}</span>
        </div>
      </div>

      <UNavigationMenu
        v-if="!collapsed"
        :items="chatItems"
        :collapsed="collapsed"
        orientation="vertical"
        :ui="{ link: 'overflow-hidden pr-7.5', linkTrailing: 'translate-x-full group-hover:translate-x-0 group-has-data-[state=open]:translate-x-0 transition-transform ms-0 absolute inset-e-px' }"
      >
        <template #chat-trailing="{ item }">
          <UDropdownMenu :items="getChatActions(item as { id: string; label: string })" :content="{ align: 'end' }">
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

      <div v-if="!collapsed && !groups.length" class="px-3 py-6 text-xs text-muted text-center">No conversations yet.</div>
    </template>

    <template #footer="{ collapsed }">
      <!-- Keep user menu and color like before -->
      <UDropdownMenu :items="userMenuItems" :content="{ align: 'center', collisionPadding: 12 }" :ui="{ content: collapsed ? 'w-48' : 'w-(--reka-dropdown-menu-trigger-width)' }">
        <UButton
          v-bind="{ label: collapsed ? undefined : (authStore.user?.email ?? 'Guest'), trailingIcon: collapsed ? undefined : 'i-lucide-chevrons-up-down' }"
          :avatar="{ icon: 'i-lucide-user', alt: authStore.user?.email ?? 'Guest' }"
          color="neutral"
          variant="ghost"
          block
          :square="collapsed"
          class="data-[state=open]:bg-elevated"
          :ui="{ trailingIcon: 'text-dimmed' }"
        />
      </UDropdownMenu>
    </template>
  </UDashboardSidebar>

  <UDashboardSearch
    v-model:open="searchOpen"
    placeholder="Search chats..."
    :groups="[{ id: 'links', items: [{ label: 'New chat', to: '/', icon: 'i-lucide-circle-plus' }] }, ...groups]"
  />

  <UModal v-model:open="renameModalOpen" title="Rename" description="Enter a new name for this conversation.">
    <template #body>
      <form id="rename-form-sidebar" @submit.prevent="confirmRename">
        <UInput v-model="renameTitle" placeholder="Enter a new name..." size="sm" class="w-full" />
      </form>
    </template>
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="rename-form-sidebar" label="Rename" :disabled="!renameTitle.trim()" />
    </template>
  </UModal>
</template>
