<script setup lang="ts">
const props = defineProps<{
  disabled?: boolean
  big?: boolean
}>()

const modelValue = defineModel<string>({ default: '' })

const emit = defineEmits<{
  send: [text: string]
}>()

const taRef = ref<HTMLTextAreaElement>()

function autosize() {
  const el = taRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

watch(modelValue, autosize)

function submit() {
  const t = modelValue.value.trim()
  if (!t || props.disabled) return
  emit('send', t)
  modelValue.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="w-full">
    <div
      class="flex items-end gap-2 bg-elevated border border-default rounded-2xl shadow-sm transition focus-within:border-primary/40"
      :class="big ? 'px-4 py-3' : 'pl-3.5 pr-2.5 py-2.5'"
    >
      <textarea
        ref="taRef"
        v-model="modelValue"
        :rows="1"
        :disabled="disabled"
        :placeholder="big ? 'Nhập câu hỏi của bạn...' : 'Nhập câu hỏi...'"
        class="flex-1 resize-none bg-transparent outline-none text-sm text-default font-sans placeholder:text-muted leading-relaxed py-1"
        @keydown="onKeydown"
      />

      <UButton
        icon="i-lucide-send"
        color="primary"
        size="sm"
        :square="true"
        :disabled="disabled || !modelValue.trim()"
        @click="submit"
      />
    </div>
    <!-- <p class="text-[11px] text-muted text-center mt-2">
      Câu trả lời chỉ mang tính tham khảo. Vui lòng đối chiếu với tài liệu gốc.
    </p> -->
  </div>
</template>
