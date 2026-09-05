<script setup lang="ts">
import { useSettingsStore } from "../../../stores/settings";

// Global Zalo webhook URL (per-bot tokens stay on the channel forms).
// Mirrors the store value; saving goes straight through updateSettings.
const settingsStore = useSettingsStore();
const toast = useToast();
const webhook = ref("");
const saving = ref(false);

watch(
	() => settingsStore.settings.zalo_webhook_url,
	(v) => {
		webhook.value = v || "";
	},
	{ immediate: true },
);

async function copy() {
	if (!webhook.value) return;
	await navigator.clipboard.writeText(webhook.value);
	toast.add({ title: "Copied", description: "Webhook URL copied", color: "success" });
}

async function save() {
	saving.value = true;
	try {
		await settingsStore.updateSettings({ zalo_webhook_url: webhook.value } as any);
		toast.add({ title: "Saved", description: "Webhook URL saved", color: "success" });
	} catch (e: any) {
		const status = e?.response?.status ?? e?.status;
		if (status === 401) {
			toast.add({
				title: "Session expired",
				description: "Please log in again at /admin/login then retry.",
				color: "error",
			});
		} else {
			toast.add({ title: "Failed", description: settingsStore.error || "Save failed", color: "error" });
		}
	} finally {
		saving.value = false;
	}
}
</script>

<template>
  <UCard>
    <template #header>
      <div class="flex items-center gap-2">
        <UIcon name="i-lucide-plug" class="size-4" />
        <span class="font-semibold">Zalo Integration</span>
      </div>
    </template>
    <div class="flex flex-col gap-4">
      <UFormField label="Zalo Webhook URL">
        <div class="flex gap-2">
          <UInput class="flex-1 font-mono text-sm" v-model="webhook" placeholder="https://example.com/api/zalo/webhook" />
          <UButton icon="i-lucide-copy" variant="outline" :disabled="!webhook" @click="copy">Copy</UButton>
        </div>
      </UFormField>
      <div class="flex gap-2">
        <UButton icon="i-lucide-check" :loading="saving" @click="save">Save Webhook</UButton>
      </div>
    </div>
  </UCard>
</template>
