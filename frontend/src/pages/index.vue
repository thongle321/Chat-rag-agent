<script setup lang="ts">
import { Comark } from "@comark/vue";
import { useClipboard } from "@vueuse/core";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { useAuthStore } from "../stores/auth";
import Indicator from "../components/chat/Indicator.vue";
import SourceLink from "../components/chat/SourceLink.vue";

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
      <header class="flex items-center px-3 md:px-7 py-3.5 border-b border-default bg-default/75">
        <UButton
          v-if="!sidebarOpen"
          variant="ghost"
          color="neutral"
          size="sm"
          :square="true"
          :icon="'i-lucide-menu'"
          @click="sidebarOpen = true"
        />
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
              <div v-if="msg.role === 'user'" class="flex justify-end mb-7">
                <div class="max-w-[85%] md:max-w-[78%] px-4 py-3 rounded-2xl rounded-br-sm text-inverted text-sm leading-relaxed break-words bg-primary">
                  {{ msg.text }}
                </div>
              </div>

              <div v-else class="flex gap-3.5 mb-3.5">
                <UAvatar icon="i-lucide-bot" size="md" class="bg-primary/10 text-primary shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-2 text-xs text-muted">
                    <span class="font-semibold text-default">VeilAi</span>
                    <span v-if="msg.sources?.length && !msg.streaming">· {{ msg.sources.length }} sources</span>
                  </div>

                  <template v-if="msg.streaming && !msg.text">
                    <Indicator label="Thinking…" />
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
  </UDashboardGroup>
</template>

