<script setup lang="ts">
const emit = defineEmits<{
  pick: [q: string]
}>()

const hour = new Date().getHours()
const greeting = hour < 11 ? 'Chào buổi sáng' : hour < 18 ? 'Chào buổi chiều' : 'Chào buổi tối'

const suggestions = [
  { cat: 'Tìm kiếm', icon: 'i-lucide-search', q: 'Tìm kiếm thông tin trong tài liệu đã tải lên' },
  { cat: 'Phân tích', icon: 'i-lucide-file-text', q: 'Phân tích nội dung chính của tài liệu' },
  { cat: 'So sánh', icon: 'i-lucide-git-compare', q: 'So sánh các điểm khác nhau giữa các văn bản' },
  { cat: 'Tổng hợp', icon: 'i-lucide-list-tree', q: 'Tổng hợp thông tin từ nhiều tài liệu' },
]
</script>

<template>
  <div class="max-w-[760px] mx-auto px-8 py-10">
    <div class="text-center mb-9">
      <div class="flex items-center justify-center size-14 rounded-2xl bg-primary/10 mx-auto mb-4">
        <UIcon name="i-lucide-message-square" class="size-7 text-primary" />
      </div>
      <h1 class="text-2xl font-bold text-default">{{ greeting }}, bạn cần tra cứu gì?</h1>
      <p class="mt-2 text-muted text-sm">
        Đặt câu hỏi về nội dung tài liệu để nhận câu trả lời từ trợ lý AI.
      </p>
    </div>

    <!-- <div class="flex items-center gap-2 mb-3 text-[11px] text-muted font-semibold uppercase tracking-wider">
      <UIcon name="i-lucide-sparkles" class="size-3.5 text-primary" />
      Câu hỏi gợi ý
    </div> -->

    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
      <!-- <button
        v-for="s in suggestions"
        :key="s.q"
        @click="emit('pick', s.q)"
        class="text-left bg-elevated border border-default rounded-xl p-3.5 flex gap-3 transition hover:border-primary/30 hover:shadow-sm"
      >
        <div class="size-8 rounded-lg bg-primary/10 text-primary grid place-items-center shrink-0">
          <UIcon :name="s.icon" class="size-4" />
        </div>
        <div class="min-w-0">
          <div class="text-[10px] font-semibold text-muted uppercase tracking-wider mb-0.5">{{ s.cat }}</div>
          <div class="text-xs text-default leading-snug">{{ s.q }}</div>
        </div>
      </button> -->
    </div>
  </div>
</template>
