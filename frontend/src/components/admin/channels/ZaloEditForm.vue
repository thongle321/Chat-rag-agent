<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";

const props = defineProps<{
	open: boolean;
	error?: string;
	initial: { bot_username?: string; verify_token?: string; webhook_url?: string };
}>();
const emit = defineEmits<{ submit: [data: ZaloEditSchema] }>();

const zaloEditSchema = z.object({
	bot_username: z.string().optional(),
	bot_token: z.string().optional(),
	verify_token: z.string().min(8).max(256).optional().or(z.literal("")),
	webhook_url: z.string().optional(),
});
type ZaloEditSchema = z.output<typeof zaloEditSchema>;
const state = reactive<Partial<ZaloEditSchema>>({
	bot_username: "",
	bot_token: "",
	verify_token: "",
	webhook_url: "",
});

watch(
	() => props.open,
	(open) => {
		if (open) {
			state.bot_username = props.initial?.bot_username || "";
			state.bot_token = "";
			state.verify_token = props.initial?.verify_token || "";
			state.webhook_url = props.initial?.webhook_url || "";
		}
	},
);
</script>

<template>
  <UForm class="space-y-4" id="zalo-edit-form" :schema="zaloEditSchema" :state="state" @submit="(e: FormSubmitEvent<ZaloEditSchema>) => emit('submit', e.data)">
    <UFormField label="Bot Token" name="bot_token" hint="Leave blank to keep">
      <UInput class="w-full" size="sm" type="password" v-model="state.bot_token" placeholder="Leave blank" />
    </UFormField>
    <UFormField label="Verify Token" name="verify_token">
      <UInput class="w-full" size="sm" v-model="state.verify_token" />
    </UFormField>
    <UAlert color="neutral" variant="soft" icon="i-lucide-settings" title="Webhook URL is global" description="Managed in Settings → Integration, not per-bot." class="mb-1" />
    <p class="text-xs text-muted">Bot name is always synced from Zalo account_name.</p>
    <UAlert v-if="error" color="error" variant="subtle" :description="error" />
  </UForm>
</template>
