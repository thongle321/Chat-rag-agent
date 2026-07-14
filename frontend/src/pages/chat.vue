<script setup lang="ts">
import { useChatStore } from '../stores/chat'

const chatStore = useChatStore()

const chatInput = ref('')
const chatWindow = ref<HTMLElement>()

async function handleSend() {
  const question = chatInput.value.trim()
  if (!question) return
  chatInput.value = ''
  await chatStore.sendMessage(question)
  await nextTick()
  if (chatWindow.value) {
    chatWindow.value.scrollTop = chatWindow.value.scrollHeight
  }
}
</script>

<template>
  <UDashboardPanel id="chat">
    <template #header>
      <UDashboardNavbar title="Chat">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UButton variant="soft" icon="i-lucide-trash-2" @click="chatStore.clearMessages()">
            Clear
          </UButton>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col gap-4">

        <UCard ref="chatWindow" class="flex-1 overflow-hidden" :ui="{ body: 'h-[calc(100vh-320px)] min-h-[300px] overflow-y-auto' }">
          <div v-if="!chatStore.messages.length" class="flex flex-col items-center justify-center py-8">
            <UIcon name="i-lucide-message-square" class="text-5xl text-primary mb-2" />
            <p class="text-muted text-lg">Ask a question about your documents</p>
          </div>

          <div v-for="msg in chatStore.messages" :key="msg.id" class="mb-3" :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
            <div :class="msg.role === 'user' ? 'bg-primary text-white rounded-l-xl rounded-tr-xl' : 'bg-muted rounded-r-xl rounded-tl-xl'" class="max-w-[80%] p-3">
              <p class="text-sm">{{ msg.text }}</p>
              <div v-if="msg.role === 'assistant'" class="flex gap-1 mt-2">
                <UBadge color="info" variant="soft" size="sm">
                  <UIcon name="i-lucide-bot" class="mr-1" />
                  {{ msg.model }}
                </UBadge>
                <UBadge v-if="msg.sources?.length" color="warning" variant="soft" size="sm">
                  <UIcon name="i-lucide-git-branch" class="mr-1" />
                  {{ msg.sources.length }} sources
                </UBadge>
                <UBadge v-else color="neutral" variant="soft" size="sm">
                  <UIcon name="i-lucide-file-question" class="mr-1" />
                  No document sources
                </UBadge>
              </div>
            </div>
          </div>

          <div v-if="chatStore.loading" class="flex justify-start mb-3">
            <div class="bg-muted rounded-xl p-3">
              <UProgress animation="carousel" />
              <span class="text-sm text-muted ml-2">Loading...</span>
            </div>
          </div>
        </UCard>

        <UAlert v-if="chatStore.error" type="error" :description="chatStore.error" />

        <div class="flex gap-2">
          <UInput v-model="chatInput" placeholder="Type your question here..." @keyup.enter="handleSend" :disabled="chatStore.loading" class="flex-1" />
          <UButton icon="i-lucide-send" @click="handleSend" :loading="chatStore.loading" :disabled="!chatInput.trim()" />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
