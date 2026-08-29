<script lang="ts" setup>
defineProps<{
	collapsed?: boolean;
}>();
</script>

<template>
  <RouterLink class="flex items-center gap-2.5 shrink-0" to="/">
    <div
      class="flex items-center justify-center size-8 rounded-lg bg-primary/10"
    >
      <UIcon class="size-4.5 text-primary" name="i-lucide-bot" />
    </div>
    <span
      class="font-[var(--font-display)] font-bold text-sm text-highlighted truncate"
      v-if="!collapsed"
    >
      VeilAi Rag
    </span>
  </RouterLink>
</template>
