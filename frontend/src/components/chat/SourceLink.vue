<script setup lang="ts">
defineProps<{
  n: number;
  title: string;
  reference?: string | null;
  active?: boolean;
}>();
defineEmits<{ (e: "click"): void }>();
</script>

<template>
  <div
    class="flex gap-2.5 p-2 rounded-lg border cursor-pointer transition"
    :class="active ? 'border-primary bg-primary/10' : 'border-default hover:bg-elevated'"
    @click="$emit('click')"
  >
    <div class="w-7 h-7 shrink-0 grid place-items-center rounded-md bg-elevated text-xs font-bold tabular-nums">{{ n }}</div>
    <div class="min-w-0">
      <div class="font-semibold text-default truncate">{{ title }}</div>
      <div v-if="reference" class="text-muted mt-0.5 truncate">{{ reference }}</div>
    </div>
  </div>
</template>
