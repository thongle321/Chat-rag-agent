<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";

const props = defineProps<{ open: boolean; error?: string }>();
const emit = defineEmits<{ submit: [data: ZaloConnectSchema] }>();

const zaloConnectSchema = z.object({
	bot_token: z.string().min(1, "Bot token is required"),
	bot_username: z.string().optional(),
	verify_token: z.string().min(8, "Verify token 8..256 chars").max(256),
	// webhook_url moved to global Settings → Integration (auto-managed, no manual input)
	webhook_url: z.string().optional().or(z.literal("")),
});
type ZaloConnectSchema = z.output<typeof zaloConnectSchema>;
const state = reactive<Partial<ZaloConnectSchema>>({
	bot_token: "",
	bot_username: "",
	verify_token: "",
	webhook_url: "",
});

watch(
	() => props.open,
	(open) => {
		if (open) {
			state.bot_token = "";
			state.bot_username = "";
			state.webhook_url = "";
			state.verify_token = "";
		}
	},
);
</script>

<template>
    <UForm
        class="space-y-4"
        id="zalo-connect-form"
        :schema="zaloConnectSchema"
        :state="state"
        @submit="
            (e: FormSubmitEvent<ZaloConnectSchema>) => emit('submit', e.data)
        "
    >
        <UFormField label="Bot Token" name="bot_token" required>
            <UInput
                class="w-full"
                size="sm"
                type="password"
                v-model="state.bot_token"
                placeholder="123456:abc-xyz"
            />
        </UFormField>
        <UFormField label="Verify Token" name="verify_token" required>
            <UInput
                class="w-full"
                size="sm"
                v-model="state.verify_token"
                placeholder="my_verify_token"
            />
        </UFormField>
        <p class="text-xs text-muted">Bot name will be auto-filled from Zalo</p>
        <UAlert
            v-if="error"
            color="error"
            variant="subtle"
            :description="error"
        />
    </UForm>
</template>
