<script setup lang="ts">
import { Comark } from "@comark/vue";
import { useClipboard } from "@vueuse/core";
import { nextTick, onMounted, reactive, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";

const chatStore = useChatStore();
const { copy, copied } = useClipboard();

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
  <div class="h-screen flex bg-bg text-default overflow-hidden">
    <!-- Mobile backdrop -->
    <div
      v-if="sidebarOpen"
      class="md:hidden fixed inset-0 bg-black/40 z-40"
      @click="sidebarOpen = false"
    />

    <!-- Sidebar: drawer on mobile, in-flow on desktop -->
    <div v-if="sidebarOpen" class="fixed md:relative inset-y-0 left-0 z-50 md:z-auto">
      <ChatSidebar
        :on-collapse="() => sidebarOpen = false"
        :on-navigate="closeSidebarOnMobile"
      />
    </div>

    <!-- Main area -->
    <div class="flex-1 flex flex-col min-w-0">
      <header class="flex items-center justify-between px-3 md:px-7 py-3.5 border-b border-default bg-elevated">
        <div class="flex items-center gap-2.5 min-w-0">
          <UButton
            v-if="!sidebarOpen"
            variant="ghost"
            color="neutral"
            size="sm"
            :square="true"
            :icon="'i-lucide-menu'"
            @click="sidebarOpen = true"
          />
          <div class="flex items-center gap-2 text-muted text-xs min-w-0">
            <span class="hidden md:inline">Search information from documents</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- email/logout moved to ChatSidebar footer -->
        </div>
      </header>

      <div ref="chatWindow" class="flex-1 overflow-y-auto">
        <template v-if="!chatStore.messages.length">
          <div class="min-h-full flex items-center">
            <div class="w-full">
              <ChatEmpty />
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
                    <div class="flex flex-col gap-2 py-1">
                      <USkeleton class="h-2.5 rounded" style="width: 92%" />
                      <USkeleton class="h-2.5 rounded" style="width: 78%" />
                      <USkeleton class="h-2.5 rounded" style="width: 60%" />
                    </div>
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
                          <div
                            v-for="s in msg.sources"
                            :id="`citation-${msg.id}-${s.n}`"
                            :key="s.n"
                            class="flex gap-2.5 p-2 rounded-lg border cursor-pointer transition"
                            :class="(activeCite.get(msg.id) ?? null) === s.n ? 'border-primary bg-primary/10' : 'border-default hover:bg-elevated'"
                            @click="activeCite.set(msg.id, s.n)"
                          >
                            <div class="w-7 h-7 shrink-0 grid place-items-center rounded-md bg-elevated text-xs font-bold tabular-nums">{{ s.n }}</div>
                            <div class="min-w-0">
                              <div class="font-semibold text-default truncate">{{ s.title }}</div>
                              <div v-if="s.reference" class="text-muted mt-0.5 truncate">{{ s.reference }}</div>
                            </div>
                          </div>
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
        class="px-3 md:px-7 pb-5 pt-3"
        :style="{
          background: 'linear-gradient(180deg, transparent 0%, var(--color-bg) 30%)',
          marginTop: '-40px',
          position: 'relative'
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
            :big="!chatStore.messages.length"
            @send="handleSend"
          />
        </div>
      </div>
    </div>
  </div>
</template>

