<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import { syncIntervalOptions } from "../../../composables/useChannelCrud";

const props = defineProps<{ open: boolean; error?: string }>();
const emit = defineEmits<{ submit: [data: ConnectSchema] }>();

const connectSchema = z.object({
	page_id: z.string().min(1, "Page ID is required"),
	page_name: z.string().min(1, "Page name is required"),
	page_token: z.string().min(1, "Page access token is required"),
	sync_interval: z.number().int().min(1).default(15),
	verify_token: z.string().min(1, "Verify token is required"),
});
type ConnectSchema = z.output<typeof connectSchema>;
const state = reactive<Partial<ConnectSchema>>({
	page_id: "",
	page_name: "",
	page_token: "",
	sync_interval: 15,
	verify_token: "",
});

watch(
	() => props.open,
	(open) => {
		if (open) {
			state.page_name = "";
			state.page_id = "";
			state.page_token = "";
			state.verify_token = "";
			state.sync_interval = 15;
		}
	},
);
</script>

<template>
  <UForm class="space-y-4" id="connect-form" :schema="connectSchema" :state="state" @submit="(e: FormSubmitEvent<ConnectSchema>) => emit('submit', e.data)">
    <UFormField label="Page Name" name="page_name" variant="none" required>
      <UInput class="w-full" placeholder="e.g. My Business Page" size="sm" v-model="state.page_name" />
    </UFormField>
    <UFormField label="Page ID" name="page_id" required>
      <UInput class="w-full" placeholder="e.g. 1234567890" size="sm" v-model="state.page_id" />
    </UFormField>
    <UFormField hint="Use a long-lived token for production" label="Page Access Token" name="page_token" required>
      <UInput class="w-full" placeholder="Paste your Page Access Token" size="sm" type="password" v-model="state.page_token" />
    </UFormField>
    <UFormField hint="Must match the verification code in Facebook Developer" label="Verify Token" name="verify_token" required>
      <UInput class="w-full" placeholder="e.g. my_verify_token" size="sm" v-model="state.verify_token" />
    </UFormField>
    <UFormField label="Sync interval" name="sync_interval">
      <USelect class="w-full" size="sm" v-model="state.sync_interval" :items="syncIntervalOptions" />
    </UFormField>
    <UAlert color="error" icon="i-lucide-alert-circle" variant="subtle" v-if="error" :description="error" />
  </UForm>
</template>
