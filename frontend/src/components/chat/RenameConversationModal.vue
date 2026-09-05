<script setup lang="ts">
const open = defineModel<boolean>("open", { default: false });
const props = defineProps<{ initialTitle: string }>();
const emit = defineEmits<{ submit: [title: string] }>();

const titleDraft = ref("");

watch(open, (v) => {
	if (v) titleDraft.value = props.initialTitle;
});

function save() {
	const t = titleDraft.value.trim();
	if (!t) return;
	emit("submit", t);
	open.value = false;
}
</script>

<template>
  <UModal v-model:open="open" title="Rename" description="Enter a new name for this conversation.">
    <template #body>
      <form id="rename-conversation-form" @submit.prevent="save">
        <UInput v-model="titleDraft" placeholder="Enter a new name..." size="sm" class="w-full" />
      </form>
    </template>
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="rename-conversation-form" label="Rename" :disabled="!titleDraft.trim()" />
    </template>
  </UModal>
</template>
