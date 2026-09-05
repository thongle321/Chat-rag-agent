<script setup lang="ts">
withDefaults(
	defineProps<{
		icon?: string;
		title: string;
		hint?: string;
		actionLabel?: string;
	}>(),
	{ actionLabel: "", hint: "", icon: "i-lucide-plug" },
);
const emit = defineEmits<{ action: [] }>();
</script>

<template>
  <div class="flex flex-col items-center justify-center py-24 text-center">
    <UIcon :name="icon" class="text-muted size-16 mb-4" />
    <h3 class="text-lg font-semibold mb-2">{{ title }}</h3>
    <p v-if="hint" class="text-muted text-sm mb-6">{{ hint }}</p>
    <UButton v-if="actionLabel" icon="i-lucide-plus" @click="emit('action')">{{ actionLabel }}</UButton>
  </div>
</template>
