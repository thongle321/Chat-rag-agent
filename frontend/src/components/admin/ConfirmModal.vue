<script setup lang="ts">
const open = defineModel<boolean>("open", { default: false });
withDefaults(
	defineProps<{
		title: string;
		description?: string;
		confirmLabel?: string;
		danger?: boolean;
		loading?: boolean;
	}>(),
	{ confirmLabel: "Delete", danger: true, description: "", loading: false },
);
const emit = defineEmits<{ confirm: [] }>();
</script>

<template>
  <UModal v-model:open="open" :title="title" :description="description" :ui="{ footer: 'justify-end' }">
    <template #footer="{ close }">
      <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
      <UButton :color="danger ? 'error' : 'primary'" :label="confirmLabel" :loading="loading" @click="emit('confirm')" />
    </template>
  </UModal>
</template>
