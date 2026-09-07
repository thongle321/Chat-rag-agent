<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useChatActions } from "../composables/useChatActions";
import { useChatSession } from "../composables/useChatSession";
import { useGreeting } from "../composables/useGreeting";
import { useThinkingTimer } from "../composables/useThinkingTimer";
import { type ChatMessage, useChatStore } from "../stores/chat";
import AssistantMessage from "./chat/AssistantMessage.vue";
import ChatHeader from "./chat/ChatHeader.vue";
import ChatSkeleton from "./chat/ChatSkeleton.vue";
import RenameConversationModal from "./chat/RenameConversationModal.vue";
import UserMessage from "./chat/UserMessage.vue";

// Shared chat UI for / (blank composer, sessionId=null), /c/:id (account sessions)
// and /uc/:id (guest temporary sessions, in-memory only — never restored).
// Like ChatGPT: / is always fresh; first send routes to /c/:id authed, /uc/:id guest.
const props = defineProps<{ sessionId: string | null; temporary?: boolean }>();
const emit = defineEmits<{ "not-found": [] }>();

const chatStore = useChatStore();
const router = useRouter();
const { loading } = storeToRefs(chatStore);
const { bootstrap, chatInput, handleSend, ready } = useChatSession(
	() => props.sessionId,
	props.temporary ?? false,
	() => emit("not-found"),
);

// Keep good morning only — like chat-vue (no quick prompts, no extra center text)
const greeting = useGreeting();

// AI thought timing — per message: each assistant reply owns its counter,
// frozen when its stream completes so older replies keep their own time.
function lastStreamingId(): string | null {
	const msgs = chatStore.messages;
	for (let i = msgs.length - 1; i >= 0; i--) {
		if (msgs[i].role !== "user" && msgs[i].streaming) return msgs[i].id;
	}
	return null;
}
const { thinkSecs, thinkingTimes } = useThinkingTimer(loading, lastStreamingId);
function thoughtSecs(msg: ChatMessage): number | null {
	if (msg.streaming) return thinkSecs(msg);
	return thinkingTimes.value[msg.id] ?? null;
}

// ChatTitle at top left like chat-vue — same modal as sidebar
const currentTitle = computed(
	() =>
		chatStore.activeConversation?.title ||
		chatStore.messages.find((m) => m.role === "user")?.text?.slice(0, 40) ||
		"New chat",
);
const renameOpen = ref(false);
const { deleteChat } = useChatActions();
function saveHeaderTitle(title: string) {
	if (chatStore.activeId) chatStore.renameConversation(chatStore.activeId, title);
}
async function deleteHeaderChat() {
	if (!chatStore.activeId) return;
	await deleteChat(chatStore.activeId);
	// replace: don't leave the deleted /c/:id in history
	if (props.sessionId) router.replace("/");
}

// Hover edit for my messages like chat-vue: truncate everything after the
// edited message, then resend the new text as a fresh turn.
async function saveEdit(msg: ChatMessage, newText: string) {
	const conv = chatStore.activeConversation;
	if (!conv) return;
	const idx = conv.messages.findIndex((m) => m.id === msg.id);
	if (idx !== -1) conv.messages.splice(idx);
	await handleSend(newText);
}

const chatWindow = ref<HTMLElement>();
const sidebarOpen = ref(false);

function scrollToBottom() {
	nextTick(() => {
		if (chatWindow.value) chatWindow.value.scrollTop = chatWindow.value.scrollHeight;
	});
}

onMounted(async () => {
	await bootstrap();
});

watch(
	() => chatStore.streamingText,
	() => scrollToBottom(),
);

function closeSidebarOnMobile() {
	if (typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches) {
		sidebarOpen.value = false;
	}
}

async function sendAndScroll(question: string) {
	await handleSend(question);
	scrollToBottom();
}
</script>

<template>
  <UDashboardGroup v-if="ready" unit="rem" class="h-screen bg-bg text-default overflow-hidden">    <ChatSidebar v-model:open="sidebarOpen" :on-navigate="closeSidebarOnMobile" />

    <!-- Main area like chat-vue: rounded panel -->
    <div class="flex-1 flex flex-col min-w-0 m-4 lg:ml-0 rounded-lg ring ring-default bg-default/75 shadow-sm overflow-hidden">
      <ChatHeader :title="chatStore.messages.length ? currentTitle : ''" @rename="renameOpen = true" @delete="deleteHeaderChat">
        <template #leading>
          <!-- Mobile only: open the sidebar drawer (UDashboardSidebar `open` drives the slideover overlay) -->
          <UButton icon="i-lucide-menu" color="neutral" variant="ghost" size="sm" square aria-label="Open sidebar" class="md:hidden" @click="sidebarOpen = true" />
        </template>
      </ChatHeader>

      <div ref="chatWindow" class="flex-1 overflow-y-auto">
        <template v-if="!chatStore.messages.length">
          <ChatSkeleton v-if="chatStore.activeId && chatStore.hydrating[chatStore.activeId]" />
          <div v-else class="min-h-full flex items-center">
            <div class="w-full">
              <!-- center like chat-vue home: greeting + prompt centered, then goes below on chat -->
              <div class="max-w-[820px] mx-auto px-3 md:px-7 py-8 flex flex-col gap-6">
                <h1 class="text-3xl sm:text-4xl text-highlighted font-bold">{{ greeting }}</h1>
                <div class="[view-transition-name:chat-prompt]">
                  <ChatComposer v-model="chatInput" :disabled="chatStore.loading" :big="true" @send="sendAndScroll" />
                  <UAlert v-if="chatStore.error" type="error" color="error" variant="soft" :description="chatStore.error" icon="i-lucide-circle-x" class="mt-4" />
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="max-w-[820px] mx-auto px-3 md:px-7 py-6 pb-32">
            <template v-for="msg in chatStore.messages" :key="msg.id">
              <UserMessage v-if="msg.role === 'user'" :msg="msg" @save="(text) => saveEdit(msg, text)" />
              <AssistantMessage v-else :msg="msg" :thought-secs="thoughtSecs(msg)" @followup="sendAndScroll" />
            </template>

            <UAlert v-if="chatStore.error" type="error" color="error" variant="soft" :description="chatStore.error" icon="i-lucide-circle-x" class="mb-4" />
          </div>
        </template>
      </div>

      <div
        v-if="chatStore.messages.length"
        class="px-3 md:px-7 pb-5 pt-3 sticky bottom-0 z-10 [view-transition-name:chat-prompt]"
        :style="{ background: 'linear-gradient(180deg, transparent 0%, var(--color-bg) 30%)' }"
      >
        <div class="max-w-[820px] mx-auto">
          <div v-if="chatStore.loading" class="flex justify-center mb-3">
            <UButton variant="soft" color="neutral" size="sm" icon="i-lucide-square" @click="chatStore.stop()">Stop</UButton>
          </div>
          <ChatComposer v-model="chatInput" :disabled="chatStore.loading" :big="false" @send="sendAndScroll" />
        </div>
      </div>
    </div>
    <!-- Same modal as sidebar: Rename shares identical UI -->
    <RenameConversationModal v-model:open="renameOpen" :initial-title="currentTitle" @submit="saveHeaderTitle" />
  </UDashboardGroup>
  <div v-else class="h-screen flex items-center justify-center bg-bg">
    <ULoader />
  </div>
</template>
