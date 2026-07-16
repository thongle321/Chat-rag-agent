<script setup lang="ts">
import { nextTick, ref, onMounted } from 'vue'
import { useChatStore } from '../stores/chat'

const chatStore = useChatStore()

const chatInput = ref('')
const chatWindow = ref<HTMLElement>()
const sidebarOpen = ref(false)

onMounted(() => {
  chatStore.fetchSessions()
  if (typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches) {
    sidebarOpen.value = true
  }
})

function closeSidebarOnMobile() {
  if (typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches) {
    sidebarOpen.value = false
  }
}

async function handleSend(question: string) {
  await chatStore.sendMessage(question)
  await nextTick()
  if (chatWindow.value) {
    chatWindow.value.scrollTop = chatWindow.value.scrollHeight
  }
}

function pickSuggestion(q: string) {
  chatInput.value = q
  nextTick(() => {
    const ta = document.querySelector<HTMLTextAreaElement>('textarea')
    ta?.focus()
  })
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
            <span class="hidden md:inline">Tra cứu thông tin từ tài liệu</span>
          </div>
        </div>
      </header>

      <div ref="chatWindow" class="flex-1 overflow-y-auto">
        <template v-if="!chatStore.messages.length">
          <div class="min-h-full flex items-center">
            <div class="w-full">
              <ChatEmpty @pick="pickSuggestion" />
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
                <div class="flex items-center justify-center size-8 rounded-lg bg-primary/10 shrink-0">
                  <UIcon name="i-lucide-bot" class="size-4.5 text-primary" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-2 text-xs text-muted">
                    <span class="font-semibold text-default">Chat RAG</span>
                    <span v-if="msg.sources?.length">• Dựa trên {{ msg.sources.length }} nguồn</span>
                  </div>

                  <div class="text-sm text-default leading-relaxed whitespace-pre-wrap">{{ msg.text }}</div>

                  <div v-if="msg.sources?.length" class="mt-3 border border-default rounded-xl bg-elevated overflow-hidden">
                    <UCollapsible>
                      <template #trigger="{ open }">
                        <UButton
                          variant="ghost"
                          color="neutral"
                          block
                          class="justify-between px-3.5 py-2.5 text-xs font-medium !text-default"
                          :trailing-icon="open ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                        >
                          <div class="flex items-center gap-2">
                            <UIcon name="i-lucide-book" class="size-3.5 text-primary" />
                            Nguồn tài liệu
                            <UBadge size="sm" variant="soft" color="neutral">{{ msg.sources.length }}</UBadge>
                          </div>
                        </UButton>
                      </template>

                      <div class="border-t border-default p-2.5 flex flex-col gap-2">
                        <div
                          v-for="(src, si) in msg.sources"
                          :key="si"
                          class="flex items-center gap-2.5 p-2 rounded-lg hover:bg-muted/50 transition"
                        >
                          <div class="size-7 rounded-md bg-muted grid place-items-center text-muted text-xs font-bold">
                            {{ si + 1 }}
                          </div>
                          <span class="text-xs text-default truncate">{{ src }}</span>
                        </div>
                      </div>
                    </UCollapsible>
                  </div>

                  <div class="flex items-center gap-1 mt-3">
                    <UButton
                      variant="ghost"
                      color="neutral"
                      size="xs"
                      icon="i-lucide-copy"
                      @click="navigator.clipboard.writeText(msg.text)"
                    >
                      Sao chép
                    </UButton>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="chatStore.loading" class="flex gap-3.5 mb-3.5">
              <div class="flex items-center justify-center size-8 rounded-lg bg-primary/10 shrink-0">
                <UIcon name="i-lucide-bot" class="size-4.5 text-primary" />
              </div>
              <div class="flex-1 flex flex-col gap-2 py-1">
                <div class="h-2.5 rounded bg-muted animate-pulse" style="width: 92%" />
                <div class="h-2.5 rounded bg-muted animate-pulse" style="width: 78%" />
                <div class="h-2.5 rounded bg-muted animate-pulse" style="width: 60%" />
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
