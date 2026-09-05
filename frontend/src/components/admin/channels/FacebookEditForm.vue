<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import { syncIntervalOptions } from "../../../composables/useChannelCrud";

const props = defineProps<{
	open: boolean;
	error?: string;
	initial: { page_id?: string; page_name?: string; verify_token?: string; sync_interval?: number };
}>();
const emit = defineEmits<{ submit: [data: EditSchema] }>();

const editSchema = z.object({
	page_name: z.string().min(1, "Page name is required"),
	page_token: z.string().min(1, "Page access token is required"),
	sync_interval: z.number().int().min(1).default(15),
	verify_token: z.string().min(1, "Verify token is required"),
});
type EditSchema = z.output<typeof editSchema>;
const state = reactive<Partial<EditSchema>>({
	page_name: "",
	page_token: "",
	sync_interval: 15,
	verify_token: "",
});

watch(
	() => props.open,
	(open) => {
		if (open) {
			state.page_name = props.initial?.page_name || "";
			state.page_token = "";
			state.verify_token = props.initial?.verify_token || "";
			state.sync_interval = props.initial?.sync_interval ?? 15;
		}
	},
);
</script>

<template>
  <UForm class="space-y-4" id="edit-form" :schema="editSchema" :state="state" @submit="(e: FormSubmitEvent<EditSchema>) => emit('submit', e.data)">
    <div class="flex items-center gap-3 mb-2">
      <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
        <UIcon class="text-primary size-5" name="i-lucide-facebook" />
      </div>
      <div>
        <h3 class="font-semibold">Facebook Messenger</h3>
        <p class="text-xs text-muted">Page ID: {{ initial?.page_id }}</p>
      </div>
    </div>
    <UFormField label="Page Name" name="page_name" required>
      <UInput class="w-full" placeholder="e.g. My Business Page" size="sm" v-model="state.page_name" />
    </UFormField>
    <UFormField hint="Leave blank to keep existing" label="Page Access Token" name="page_token">
      <UInput class="w-full" placeholder="Paste new token or leave blank" size="sm" type="password" v-model="state.page_token" />
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
