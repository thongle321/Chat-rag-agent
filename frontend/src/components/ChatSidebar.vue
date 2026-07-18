<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore, groupByDate } from '../stores/chat'

defineProps<{
  onCollapse?: () => void
  onNavigate?: () => void
}>()

const chatStore = useChatStore()
const search = ref('')
const filtered = computed(() => {
  const s = search.value.trim().toLowerCase()
  if (!s) return chatStore.conversations
  return chatStore.conversations.filter(c => c.title.toLowerCase().includes(s))
})

const groups = computed(() => groupByDate(filtered.value))

function handleNew() {
  chatStore.newConversation()
}

function handleDelete(id: string) {
  chatStore.deleteConversation(id)
}

const renameModalOpen = ref(false)
const renameId = ref<string | null>(null)
const renameTitle = ref('')

function handleRename(id: string) {
  const conv = chatStore.conversations.find(c => c.id === id)
  renameId.value = id
  renameTitle.value = conv?.title ?? ''
  renameModalOpen.value = true
}

function confirmRename() {
  if (renameId.value && renameTitle.value.trim()) {
    chatStore.renameConversation(renameId.value, renameTitle.value.trim())
  }
  renameModalOpen.value = false
}

function getItems(c: any) {
  return [
    [
      { label: c.pinned ? 'Bỏ ghim' : 'Ghim', icon: c.pinned ? 'i-lucide-pin-off' : 'i-lucide-pin', onSelect: () => chatStore.togglePin(c.id) },
      { label: 'Đổi tên', icon: 'i-lucide-pencil', onSelect: () => handleRename(c.id) }
    ],
    [
      { label: 'Xoá', icon: 'i-lucide-trash-2', color: 'error' as const, onSelect: () => handleDelete(c.id) }
    ]
  ]
}

const colorMode = useColorMode()

function toggleColorMode() {
  colorMode.value = colorMode.value === 'dark' ? 'light' : 'dark'
}
</script>

<template>
  <aside class="w-[85vw] max-w-[300px] md:w-[280px] h-full shrink-0 bg-elevated border-r border-default flex flex-col">
    <div class="px-[18px] pt-[18px] pb-3 flex items-center gap-3">
      <div class="flex items-center justify-center size-9 rounded-xl bg-primary/10">
        <UIcon name="i-lucide-bot" class="size-5 text-primary" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="font-semibold text-sm tracking-tight text-default">Chat RAG</div>
        <div class="text-[11px] text-muted">Tra cứu thông minh</div>
      </div>
    </div>

    <div class="px-3.5 pb-2.5">
      <UButton
        block
        color="primary"
        variant="solid"
        size="sm"
        :icon="'i-lucide-plus'"
        @click="handleNew"
      >
        Cuộc hội thoại mới
      </UButton>
    </div>

    <div class="px-3.5 pb-3">
      <UInput v-model="search" icon="i-lucide-search" placeholder="Tìm trong lịch sử..." size="xs" />
    </div>

    <div class="flex-1 overflow-y-auto px-2 pb-4">
      <div v-if="!groups.length" class="px-3 py-6 text-xs text-muted text-center">
        Chưa có hội thoại nào.
      </div>

      <template v-for="[label, items] in groups" :key="label">
        <div class="mb-3.5">
          <div class="text-[10px] font-semibold text-muted uppercase tracking-wider px-2 py-1.5">
            {{ label }}
          </div>

          <div
            v-for="c in items"
            :key="c.id"
            @click="chatStore.setActive(c.id); onNavigate?.()"
            class="group relative flex items-center gap-2 px-2 py-1.5 rounded-md mb-px cursor-pointer transition"
            :class="c.id === chatStore.activeId ? 'bg-primary/10 text-primary font-medium' : 'text-muted hover:bg-muted'"
          >
            <span class="text-xs truncate flex-1">{{ c.title }}</span>

            <UDropdownMenu :items="getItems(c)">
              <UButton
                variant="ghost"
                color="neutral"
                size="2xs"
                :square="true"
                :icon="'i-lucide-ellipsis'"
                class="!w-6 !h-6 opacity-0 group-hover:opacity-100 transition"
                @click.stop
              />
            </UDropdownMenu>
          </div>
        </div>
      </template>
    </div>

    <div class="px-3.5 py-3 border-t border-default/50 flex items-center gap-2.5">
      <UAvatar icon="i-lucide-user" size="xs" class="bg-muted text-muted" />
      <div class="flex-1 text-[11px] text-default font-medium">Người dùng</div>
      <UButton
        variant="ghost"
        color="neutral"
        size="2xs"
        :square="true"
        :icon="colorMode.value === 'dark' ? 'i-lucide-sun' : 'i-lucide-moon'"
        @click="toggleColorMode"
      />
      <UButton
        variant="ghost"
        color="neutral"
        size="2xs"
        :square="true"
        :icon="'i-lucide-panel-left-close'"
        @click="onCollapse?.()"
      />
    </div>
  </aside>

  <UModal v-model:open="renameModalOpen" title="Đổi tên" description="Nhập tên mới cho cuộc hội thoại." @close="renameModalOpen = false">
    <template #body>
      <form id="rename-form" @submit.prevent="confirmRename">
        <UInput
          v-model="renameTitle"
          placeholder="Nhập tên mới..."
          size="sm"
          class="w-full"
        />
      </form>
    </template>

    <template #footer="{ close }">
      <UButton label="Huỷ" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="rename-form" label="Đổi tên" :disabled="!renameTitle.trim()" />
    </template>
  </UModal>
</template>
