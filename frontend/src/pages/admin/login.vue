<script lang="ts" setup>
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import { useAuthStore } from "../../stores/auth";

const authStore = useAuthStore();
const router = useRouter();

function isAdmin(u: any) { return !!u && (u.role === "admin" || u.is_superuser); }
onMounted(() => {
	if (!authStore.isAuthenticated) return;
	router.replace(isAdmin(authStore.user) ? "/admin/" : "/login");
});

const schema = z.object({
	email: z
		.string()
		.min(1, "Email is required")
		.email("Enter a valid email address"),
	password: z.string().min(1, "Password is required"),
});

type Schema = z.output<typeof schema>;
const error = ref("");
const isSubmitting = ref(false);

/**
 * Turns whatever the auth store / network throws into a clear,
 * user-facing message instead of a generic "Login failed".
 */
function resolveErrorMessage(err: unknown): string {
	// Prefer a message the auth store already parsed from the API response
	const storeMessage = authStore.error;

	// Try to detect common HTTP status codes surfaced via $fetch/ofetch errors
	const status =
		(err as any)?.response?.status ??
		(err as any)?.statusCode ??
		(err as any)?.status;

	if (status === 401 || status === 400) {
		return "Incorrect email or password. Please try again.";
	}
	if (status === 403) {
		return "Your account does not have access. Contact an administrator.";
	}
	if (status === 429) {
		return "Too many attempts. Please wait a moment before trying again.";
	}
	if (status && status >= 500) {
		return "Something went wrong on our end. Please try again shortly.";
	}

	// Offline / network failure (no response at all)
	if (
		((err as any)?.name === "FetchError" && !status) ||
		(typeof navigator !== "undefined" && !navigator.onLine)
	) {
		return "Unable to reach the server. Check your internet connection and try again.";
	}

	if (storeMessage) {
		return storeMessage;
	}

	return "We couldn't sign you in. Please check your details and try again.";
}

const state = reactive<Partial<Schema>>({
	email: "admin@example.com",
	password: "",
});
const showPassword = ref(false);

async function handleLogin(event: FormSubmitEvent<Schema>) {
	if (isSubmitting.value) {
		return;
	}
	error.value = "";
	isSubmitting.value = true;
	try {
		await authStore.login(event.data.email.trim(), event.data.password);
		if (!isAdmin(authStore.user)) {
			error.value = "This account is not an admin. Use User Login (/login) to chat.";
			await authStore.logout();
			return;
		}
		await router.push("/admin/");
	} catch (err: unknown) {
		error.value = resolveErrorMessage(err);
	} finally {
		isSubmitting.value = false;
	}
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30 px-4">
    <UCard class="w-full max-w-md shadow-lg">
      <template #header>
        <div class="text-center py-2">
          <div
            class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10"
          >
            <UIcon class="h-6 w-6 text-primary" name="i-lucide-lock" />
          </div>
          <h1 class="text-xl font-bold">Admin Login</h1>
          <p class="text-sm text-muted mt-1">Sign in to manage your chatbot</p>
        </div>
      </template>

      <UForm
        class="flex flex-col gap-4"
        :schema="schema"
        :state="state"
        @submit="handleLogin"
      >
        <UFormField label="Email" name="email" required>
          <UInput
            autocomplete="username"
            autofocus
            class="w-full"
            icon="i-lucide-mail"
            placeholder="you@example.com"
            type="email"
            v-model="state.email"
          />
        </UFormField>

        <UFormField label="Password" name="password" required>
          <UInput
            autocomplete="current-password"
            class="w-full"
            icon="i-lucide-key-round"
            placeholder="Enter your password"
            v-model="state.password"
            :type="showPassword ? 'text' : 'password'"
          >
            <template #trailing>
              <UButton
                color="neutral"
                size="sm"
                variant="link"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
                :icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                @click="showPassword = !showPassword"
              />
            </template>
          </UInput>
        </UFormField>

        <UAlert
          aria-live="assertive"
          color="error"
          icon="i-lucide-alert-circle"
          role="alert"
          variant="subtle"
          v-if="error"
          :description="error"
        />

        <UButton
          block
          size="lg"
          type="submit"
          :disabled="authStore.loading || isSubmitting"
          :loading="authStore.loading || isSubmitting"
        >
          {{ (authStore.loading || isSubmitting) ? 'Signing in…' : 'Sign In' }}
        </UButton>
      </UForm>
    </UCard>
  </div>
</template>
