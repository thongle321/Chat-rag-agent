<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore, groupByDate } from '../stores/chat'

defineProps<{
  onCollapse?: () => void
  onNavigate?: () => void
}>()

const chatStore = useChatStore()
const search = ref('')
const menuId = ref<string | null>(null)

const filtered = computed(() => {
  const s = search.value.trim().toLowerCase()
  if (!s) return chatStore.conversations
  return chatStore.conversations.filter(c => c.title.toLowerCase().includes(s))
})

const groups = computed(() => groupByDate(filtered.value))

function toggleMenu(id: string) {
  menuId.value = menuId.value === id ? null : id
}

function handleNew() {
  chatStore.newConversation()
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
      <div class="flex items-center gap-2 px-2.5 py-2 bg-muted rounded-lg">
        <UIcon name="i-lucide-search" class="size-3.5 text-muted shrink-0" />
        <input
          v-model="search"
          placeholder="Tìm trong lịch sử..."
          class="flex-1 bg-transparent outline-none text-xs text-default placeholder:text-muted"
        />
      </div>
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

            <UButton
              variant="ghost"
              color="neutral"
              size="2xs"
              :square="true"
              :icon="'i-lucide-ellipsis'"
              class="!w-6 !h-6 opacity-0 group-hover:opacity-100 transition"
              @click.stop="toggleMenu(c.id)"
            />

            <div
              v-if="menuId === c.id"
              class="absolute right-1 top-8 z-10 bg-elevated border border-default rounded-lg shadow-md py-1 min-w-[140px]"
              @mouseleave="menuId = null"
            >
              <UButton
                variant="ghost"
                color="neutral"
                size="xs"
                block
                :icon="c.pinned ? 'i-lucide-pin-off' : 'i-lucide-pin'"
                class="justify-start !rounded-none"
                @click="chatStore.togglePin(c.id); menuId = null"
              >
                {{ c.pinned ? 'Bỏ ghim' : 'Ghim' }}
              </UButton>
              <UButton
                variant="ghost"
                color="neutral"
                size="xs"
                block
                :icon="'i-lucide-trash-2'"
                class="justify-start !rounded-none !text-error"
                @click="chatStore.deleteConversation(c.id); menuId = null"
              >
                Xoá
              </UButton>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div class="px-3.5 py-3 border-t border-default/50 flex items-center gap-2.5">
      <div class="size-7 rounded-full bg-muted grid place-items-center text-muted text-[10px] font-semibold">
        NV
      </div>
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
</template>
