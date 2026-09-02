<script setup lang="ts">
import { useSettingsStore } from "../stores/settings";

const settingsStore = useSettingsStore();
const model = defineModel<string>({ default: "" });

async function refresh() {
  await settingsStore.fetchSettings();
}
</script>

<template>
  <USelectMenu
    v-model="model"
    :items="settingsStore.models.length ? settingsStore.models : ['gemma4:31b-cloud', 'gpt-4o']"
    placeholder="Model"
    size="xs"
    variant="ghost"
    class="min-w-[140px]"
    :loading="settingsStore.modelLoading"
    @update:open="refresh"
  >
    <template #trailing>
      <UIcon name="i-lucide-chevron-down" class="size-3 text-muted" />
    </template>
  </USelectMenu>
</template>
