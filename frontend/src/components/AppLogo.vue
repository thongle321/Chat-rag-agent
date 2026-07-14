<script setup lang="ts">
defineProps<{
  collapsed?: boolean
}>()
</script>

<template>
  <RouterLink to="/" class="flex items-center gap-2.5 shrink-0">
    <div class="flex items-center justify-center size-8 rounded-lg bg-primary/10">
      <UIcon name="i-lucide-bot" class="size-4.5 text-primary" />
    </div>
    <span v-if="!collapsed" class="font-[var(--font-display)] font-bold text-sm text-highlighted truncate">
      Chat RAG
    </span>
  </RouterLink>
</template>
