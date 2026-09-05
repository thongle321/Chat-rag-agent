<script setup lang="ts">
import type { ChatMessage } from "../../stores/chat";

defineProps<{ msg: ChatMessage }>();
const emit = defineEmits<{ save: [text: string] }>();

const editing = ref(false);
const editingText = ref("");

function startEdit(msg: ChatMessage) {
	editing.value = true;
	editingText.value = msg.text;
}
function cancelEdit() {
	editing.value = false;
	editingText.value = "";
}
function saveEdit(msg: ChatMessage) {
	const newText = editingText.value.trim();
	if (!newText || newText === msg.text) {
		cancelEdit();
		return;
	}
	cancelEdit();
	emit("save", newText);
}
</script>

<template>
  <div class="group flex flex-col items-end mb-7 gap-1">
    <div v-if="!editing" class="max-w-[85%] md:max-w-[78%] px-4 py-3 rounded-2xl rounded-br-sm text-inverted text-sm leading-relaxed break-words bg-primary">
      {{ msg.text }}
    </div>
    <div v-else class="max-w-[85%] md:max-w-[78%] flex flex-col gap-2 w-full">
      <UTextarea v-model="editingText" autoresize :maxrows="6" class="w-full" @keydown.enter.exact.prevent="saveEdit(msg)" @keydown.escape="cancelEdit" />
      <div class="flex gap-1.5 justify-end">
        <UButton size="xs" color="neutral" variant="ghost" label="Cancel" @click="cancelEdit" />
        <UButton size="xs" color="primary" label="Save" :disabled="!editingText.trim()" @click="saveEdit(msg)" />
      </div>
    </div>
    <div v-if="!editing" class="flex justify-end w-full max-w-[85%] md:max-w-[78%] opacity-0 group-hover:opacity-100 transition">
      <UButton icon="i-lucide-pencil" color="neutral" variant="ghost" size="xs" aria-label="Edit" @click="startEdit(msg)" />
    </div>
  </div>
</template>
