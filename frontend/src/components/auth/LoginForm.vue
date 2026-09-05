<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import PasswordInput from "./PasswordInput.vue";

const emit = defineEmits<{ submit: [data: { email: string; password: string }] }>();
defineProps<{ error?: string; submitting?: boolean }>();

const loginSchema = z.object({
	email: z.string().min(1, "Email is required").email("Enter a valid email"),
	password: z.string().min(1, "Password is required"),
});
type LoginSchema = z.output<typeof loginSchema>;
const state = reactive<Partial<LoginSchema>>({ email: "", password: "" });
</script>

<template>
  <UForm class="flex flex-col gap-4" :schema="loginSchema" :state="state" @submit="(e: FormSubmitEvent<LoginSchema>) => emit('submit', { email: e.data.email, password: e.data.password })">
    <UFormField label="Email" name="email" required>
      <UInput v-model="state.email" class="w-full" icon="i-lucide-mail" placeholder="you@example.com" type="email" autocomplete="username" autofocus />
    </UFormField>
    <UFormField label="Password" name="password" required>
      <PasswordInput v-model="state.password" />
    </UFormField>
    <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />
    <UButton block size="lg" type="submit" :loading="submitting" :disabled="submitting">
      {{ submitting ? "Signing in…" : "Sign In" }}
    </UButton>
  </UForm>
</template>
