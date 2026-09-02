<script setup lang="ts">
import { Comark } from "@comark/vue";
import { useClipboard } from "@vueuse/core";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { useAuthStore } from "../stores/auth";
import Indicator from "../components/chat/Indicator.vue";
import SourceLink from "../components/chat/SourceLink.vue";
import { useChatActions } from "../composables/useChatActions";

const chatStore = useChatStore();
const authStore = useAuthStore();
const { copy, copied } = useClipboard();

// Keep good morning only — like chat-vue (no quick prompts, no extra center text)
const greeting = computed(() => {
  const h = new Date().getHours();
  let t = "Good evening";
  if (h < 12) t = "Good morning";
  else if (h < 18) t = "Good afternoon";
  const name = authStore.user?.email?.split("@")[0] || "";
  return name ? `${t}, ${name}` : t;
});

const chatInput = ref("");
const chatWindow = ref<HTMLElement>();
const sidebarOpen = ref(false);
const accOpen = reactive<Record<string, string | undefined>>({});
const activeCite = reactive(new Map<string, number>());
// ChatTitle at top left like chat-vue — same modal as sidebar
const headerRenameOpen = ref(false);
const titleDraft = ref("");
const currentTitle = computed(() => chatStore.activeConversation?.title || chatStore.messages.find((m) => m.role === "user")?.text?.slice(0, 40) || "New chat");
const { deleteChat: deleteHeaderChat } = useChatActions();
const headerMenuItems = computed(() => [
  [{ label: "Rename", icon: "i-lucide-pencil", onSelect: () => { titleDraft.value = currentTitle.value; headerRenameOpen.value = true; } }],
  [{ label: "Delete", icon: "i-lucide-trash", color: "error" as const, onSelect: async () => { if (chatStore.activeId) await deleteHeaderChat(chatStore.activeId); } }],
]);
function saveHeaderTitle() {
  const t = titleDraft.value.trim();
  if (t && chatStore.activeId) chatStore.renameConversation(chatStore.activeId, t);
  headerRenameOpen.value = false;
}
// AI thought timing like chat-vue
const thinkingStart = ref<number | null>(null);
const thinkingElapsed = ref(0);
let thinkingTimer: ReturnType<typeof setInterval> | null = null;
watch(
  () => chatStore.loading,
  (loading) => {
    if (loading) {
      thinkingStart.value = Date.now();
      thinkingElapsed.value = 0;
      if (thinkingTimer) clearInterval(thinkingTimer);
      thinkingTimer = setInterval(() => {
        if (thinkingStart.value) thinkingElapsed.value = (Date.now() - thinkingStart.value) / 1000;
      }, 100);
    } else {
      if (thinkingTimer) clearInterval(thinkingTimer);
      thinkingTimer = null;
      if (thinkingStart.value) thinkingElapsed.value = (Date.now() - thinkingStart.value) / 1000;
    }
  },
);
// Hover edit for my messages like chat-vue
const editingId = ref<string | null>(null);
const editingText = ref("");
function startEdit(msg: any) {
  editingId.value = msg.id;
  editingText.value = msg.text;
}
function cancelEdit() {
  editingId.value = null;
  editingText.value = "";
}
async function saveEdit(msg: any) {
  const newText = editingText.value.trim();
  if (!newText || newText === msg.text) {
    cancelEdit();
    return;
  }
  const conv = chatStore.activeConversation;
  if (!conv) return;
  const idx = conv.messages.findIndex((m) => m.id === msg.id);
  if (idx !== -1) conv.messages.splice(idx);
  cancelEdit();
  await handleSend(newText);
}

onMounted(async () => {
	await chatStore.fetchSessions();
	if (
		typeof window !== "undefined" &&
		window.matchMedia("(min-width: 768px)").matches
	) {
		sidebarOpen.value = true;
	}
});

watch(
	() => chatStore.streamingText,
	() => {
		nextTick(() => {
			if (chatWindow.value) {
				chatWindow.value.scrollTop = chatWindow.value.scrollHeight;
			}
		});
	},
);

function closeSidebarOnMobile() {
	if (
		typeof window !== "undefined" &&
		window.matchMedia("(max-width: 767px)").matches
	) {
		sidebarOpen.value = false;
	}
}

function stripInlineCitations(text: string): string {
	return text.replace(/\s*\[Source:[^\]]*\]/g, "").replace(/\s*\[(\d+)\]/g, "");
}

async function handleSend(question: string) {
	try {
		await chatStore.sendMessage(question);
	} catch {
		// error is already displayed via chatStore.error
	}
	await nextTick();
	if (chatWindow.value) {
		chatWindow.value.scrollTop = chatWindow.value.scrollHeight;
	}
}
</script>

<template>
  <UDashboardGroup unit="rem" class="h-screen bg-bg text-default overflow-hidden">
    <ChatSidebar v-model:open="sidebarOpen" :on-navigate="closeSidebarOnMobile" />

    <!-- Main area like chat-vue: rounded panel -->
    <div class="flex-1 flex flex-col min-w-0 m-4 lg:ml-0 rounded-lg ring ring-default bg-default/75 shadow-sm overflow-hidden">
      <header class="flex items-center justify-between px-3 md:px-7 py-2.5 bg-default/75 min-h-[44px]">
        <div class="flex items-center gap-2 min-w-0">
          <div v-if="chatStore.messages.length" class="min-w-0">
          <UDropdownMenu :items="headerMenuItems" :content="{ align: 'start' }" :ui="{ content: 'min-w-44' }">
            <UButton color="neutral" variant="ghost" :label="currentTitle" trailing-icon="i-lucide-chevron-down" class="group min-w-0 max-w-[280px] data-[state=open]:bg-elevated" :ui="{ trailingIcon: 'text-dimmed group-data-[state=open]:rotate-180 transition-transform duration-200' }" />
          </UDropdownMenu>
        </div>

        </div>
        <div v-if="chatStore.loading && thinkingElapsed" class="text-xs text-muted hidden sm:block">{{ thinkingElapsed.toFixed(1) }}s thinking</div>
      </header>

      <div ref="chatWindow" class="flex-1 overflow-y-auto">
        <template v-if="!chatStore.messages.length">
          <div class="min-h-full flex items-center">
            <div class="w-full">
              <!-- center like chat-vue home: greeting + prompt centered, then goes below on chat -->
              <div class="max-w-[820px] mx-auto px-3 md:px-7 py-8 flex flex-col gap-6">
                <h1 class="text-3xl sm:text-4xl text-highlighted font-bold">{{ greeting }}</h1>
                <div class="[view-transition-name:chat-prompt]">
                  <ChatComposer
                    v-model="chatInput"
                    :disabled="chatStore.loading"
                    :big="true"
                    @send="handleSend"
                  />
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="max-w-[820px] mx-auto px-3 md:px-7 py-6 pb-32">
            <div v-for="(msg, i) in chatStore.messages" :key="msg.id">
              <div v-if="msg.role === 'user'" class="group/user flex justify-end mb-7 relative">
                <div v-if="editingId !== msg.id" class="max-w-[85%] md:max-w-[78%] px-4 py-3 rounded-2xl rounded-br-sm text-inverted text-sm leading-relaxed break-words bg-primary">
                  {{ msg.text }}
                </div>
                <div v-else class="max-w-[85%] md:max-w-[78%] flex flex-col gap-2">
                  <UTextarea v-model="editingText" autoresize :maxrows="6" class="w-full" @keydown.enter.exact.prevent="saveEdit(msg)" @keydown.escape="cancelEdit" />
                  <div class="flex gap-1.5 justify-end">
                    <UButton size="xs" color="neutral" variant="ghost" label="Cancel" @click="cancelEdit" />
                    <UButton size="xs" color="primary" label="Save" :disabled="!editingText.trim()" @click="saveEdit(msg)" />
                  </div>
                </div>
                <UButton v-if="editingId !== msg.id" icon="i-lucide-pencil" color="neutral" variant="ghost" size="xs" class="absolute -left-8 top-1/2 -translate-y-1/2 opacity-0 group-hover/user:opacity-100 transition hidden sm:flex" @click="startEdit(msg)" />
              </div>

              <div v-else class="flex gap-3.5 mb-3.5">
                <UAvatar icon="i-lucide-bot" size="md" class="bg-primary/10 text-primary shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-2 text-xs text-muted">
                    <span class="font-semibold text-default">VeilAi</span>
                    <span v-if="msg.sources?.length && !msg.streaming">· {{ msg.sources.length }} sources</span>
                  </div>

                  <template v-if="msg.streaming && !msg.text">
                    <Indicator :label="`Thinking… ${thinkingElapsed.toFixed(1)}s`" />
                  </template>
                  <template v-else-if="msg.streaming && msg.text">
                    <div class="text-xs text-muted mb-1">Thinking {{ thinkingElapsed.toFixed(1) }}s…</div>
                    <Suspense>
                      <Comark :markdown="stripInlineCitations(msg.text)" :streaming="!!msg.streaming" caret class="text-sm text-default leading-relaxed prose prose-sm dark:prose-invert max-w-none" />
                    </Suspense>
                  </template>
                  <template v-else-if="!msg.streaming && msg.text && thinkingElapsed">
                    <div class="text-xs text-muted mb-1">Thought for {{ thinkingElapsed.toFixed(1) }}s</div>
                    <Suspense>
                      <Comark :markdown="stripInlineCitations(msg.text)" :streaming="!!msg.streaming" caret class="text-sm text-default leading-relaxed prose prose-sm dark:prose-invert max-w-none" />
                    </Suspense>
                  </template>
                  <template v-else>
                    <Suspense>
                      <Comark :markdown="stripInlineCitations(msg.text)" :streaming="!!msg.streaming" caret class="text-sm text-default leading-relaxed prose prose-sm dark:prose-invert max-w-none" />
                    </Suspense>

                    <UAccordion
                      v-if="msg.sources?.length && !msg.streaming"
                      v-model="accOpen[msg.id]"
                      :items="[{ label: `Sources (${msg.sources.length})`, icon: 'i-lucide-book-open', value: 'sources' }]"
                      class="mt-3"
                      :ui="{ trigger: 'text-xs font-medium', body: 'text-xs' }"
                    >
                      <template #body>
                        <div class="grid md:grid-cols-2 gap-2">
                          <SourceLink
                            v-for="s in msg.sources"
                            :id="`citation-${msg.id}-${s.n}`"
                            :key="s.n"
                            :n="s.n"
                            :title="s.title"
                            :reference="s.reference"
                            :active="(activeCite.get(msg.id) ?? null) === s.n"
                            @click="activeCite.set(msg.id, s.n)"
                          />
                        </div>
                      </template>
                    </UAccordion>

                    <div v-if="!msg.streaming" class="flex items-center gap-1 mt-3">
                      <UButton
                        variant="ghost"
                        color="neutral"
                        size="xs"
                        :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
                        @click="copy(msg.text)"
                      >
                        {{ copied ? 'Copied' : 'Copy' }}
                      </UButton>
                    </div>
                  </template>
                </div>
              </div>
            </div>

            <UAlert
              v-if="chatStore.error"
              type="error"
              color="error"
              variant="soft"
              :description="chatStore.error"
              icon="i-lucide-circle-x"
              class="mb-4"
            />
          </div>
        </template>
      </div>

      <div
        v-if="chatStore.messages.length"
        class="px-3 md:px-7 pb-5 pt-3 sticky bottom-0 z-10 [view-transition-name:chat-prompt]"
        :style="{
          background: 'linear-gradient(180deg, transparent 0%, var(--color-bg) 30%)',
        }"
      >
        <div class="max-w-[820px] mx-auto">
          <div v-if="chatStore.loading" class="flex justify-center mb-3">
            <UButton
              variant="soft"
              color="neutral"
              size="sm"
              icon="i-lucide-square"
              @click="chatStore.stop()"
            >
              Stop
            </UButton>
          </div>
          <ChatComposer
            v-model="chatInput"
            :disabled="chatStore.loading"
            :big="false"
            @send="handleSend"
          />
        </div>
      </div>
    </div>
    <!-- Same modal as sidebar: Rename/Delete share identical UI -->
    <UModal v-model:open="headerRenameOpen" title="Rename" description="Enter a new name for this conversation.">
      <template #body>
        <form id="header-rename-form" @submit.prevent="saveHeaderTitle">
          <UInput v-model="titleDraft" placeholder="Enter a new name..." size="sm" class="w-full" />
        </form>
      </template>
      <template #footer="{ close }">
        <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
        <UButton type="submit" form="header-rename-form" label="Rename" :disabled="!titleDraft.trim()" />
      </template>
    </UModal>
  </UDashboardGroup>
</template>

