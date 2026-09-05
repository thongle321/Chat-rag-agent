<script setup lang="ts">
withDefaults(
	defineProps<{
		autocomplete?: string;
		placeholder?: string;
	}>(),
	{ autocomplete: "current-password", placeholder: "Enter your password" },
);
const model = defineModel<string>({ default: "" });
const visible = ref(false);
</script>

<template>
  <UInput
    v-model="model"
    class="w-full"
    icon="i-lucide-key-round"
    :placeholder="placeholder"
    :type="visible ? 'text' : 'password'"
    :autocomplete="autocomplete"
  >
    <template #trailing>
      <UButton
        color="neutral"
        variant="link"
        size="sm"
        :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'"
        :aria-label="visible ? 'Hide password' : 'Show password'"
        @click="visible = !visible"
      />
    </template>
  </UInput>
</template>
