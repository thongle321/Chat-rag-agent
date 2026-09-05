<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import PasswordInput from "./PasswordInput.vue";

const emit = defineEmits<{ submit: [data: { email: string; password: string }] }>();
defineProps<{ error?: string; submitting?: boolean }>();

const registerSchema = z
	.object({
		email: z.string().min(1, "Email is required").email("Enter a valid email"),
		password: z.string().min(6, "Password must be at least 6 characters"),
		confirmPassword: z.string().min(1, "Confirm your password"),
	})
	.refine((d) => d.password === d.confirmPassword, {
		message: "Passwords do not match",
		path: ["confirmPassword"],
	});
type RegisterSchema = z.output<typeof registerSchema>;
const state = reactive<Partial<RegisterSchema>>({ email: "", password: "", confirmPassword: "" });
</script>

<template>
  <UForm
    class="flex flex-col gap-4"
    :schema="registerSchema"
    :state="state"
    @submit="(e: FormSubmitEvent<RegisterSchema>) => emit('submit', { email: e.data.email, password: e.data.password })"
  >
    <UFormField label="Email" name="email" required>
      <UInput v-model="state.email" class="w-full" icon="i-lucide-mail" placeholder="you@example.com" type="email" autocomplete="email" autofocus />
    </UFormField>
    <UFormField label="Password" name="password" required>
      <PasswordInput v-model="state.password" placeholder="At least 6 characters" autocomplete="new-password" />
    </UFormField>
    <UFormField label="Confirm password" name="confirmPassword" required>
      <PasswordInput v-model="state.confirmPassword" placeholder="Confirm your password" autocomplete="new-password" />
    </UFormField>
    <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />
    <UButton block size="lg" type="submit" :loading="submitting" :disabled="submitting">
      {{ submitting ? "Creating account…" : "Create account" }}
    </UButton>
  </UForm>
</template>
