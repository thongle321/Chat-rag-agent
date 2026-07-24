<script setup lang="ts">
const hour = new Date().getHours()
const greeting = hour < 11 ? 'Chào buổi sáng' : hour < 18 ? 'Chào buổi chiều' : 'Chào buổi tối'
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
  </div>
</template>
