<script lang="ts" setup>
import AuthCard from "../../components/auth/AuthCard.vue";
import PasswordInput from "../../components/auth/PasswordInput.vue";
import { useAuthStore } from "../../stores/auth";
import { adminAuthError, isAdminUser } from "../../utils/auth";

const authStore = useAuthStore();
const router = useRouter();

onMounted(() => {
	if (!authStore.isAuthenticated) return;
	router.replace(isAdminUser(authStore.user) ? "/admin/" : "/login");
});

const email = ref("admin@example.com");
const password = ref("");
const error = ref("");
const isSubmitting = ref(false);
const busy = computed(() => authStore.loading || isSubmitting.value);

async function handleLogin() {
	if (isSubmitting.value) return;
	error.value = "";
	isSubmitting.value = true;
	try {
		await authStore.login(email.value.trim(), password.value);
		if (!isAdminUser(authStore.user)) {
			// Mask non-admin logins as bad credentials (decided: admin page never
			// distinguishes wrong-password from not-an-admin).
			error.value = "Incorrect email or password.";
			await authStore.logout();
			return;
		}
		await router.push("/admin/");
	} catch (err: unknown) {
		error.value = adminAuthError(err, authStore.error);
	} finally {
		isSubmitting.value = false;
	}
}
</script>

<template>
  <AuthCard icon="i-lucide-lock" title="Admin Login" subtitle="Sign in to manage your chatbot">
    <form class="flex flex-col gap-4" @submit.prevent="handleLogin">
      <UFormField label="Email" name="email" required>
        <UInput v-model="email" class="w-full" icon="i-lucide-mail" placeholder="you@example.com" type="email" autocomplete="username" autofocus />
      </UFormField>
      <UFormField label="Password" name="password" required>
        <PasswordInput v-model="password" autocomplete="current-password" />
      </UFormField>
      <UAlert v-if="error" aria-live="assertive" role="alert" color="error" icon="i-lucide-alert-circle" variant="subtle" :description="error" />
      <UButton block size="lg" type="submit" :disabled="busy" :loading="busy">
        {{ busy ? "Signing in…" : "Sign In" }}
      </UButton>
    </form>
  </AuthCard>
</template>
