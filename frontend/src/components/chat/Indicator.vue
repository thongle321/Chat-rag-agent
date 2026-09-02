<script setup lang="ts">
defineProps<{ label?: string }>();
</script>

<template>
  <div class="flex items-center gap-2 py-1 text-xs text-muted">
    <span class="inline-flex gap-1">
      <span class="size-1.5 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]" />
      <span class="size-1.5 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]" />
      <span class="size-1.5 rounded-full bg-primary animate-bounce" />
    </span>
    <span>{{ label || "Thinking…" }}</span>
  </div>
</template>
