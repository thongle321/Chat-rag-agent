<script lang="ts" setup>
import AuthCard from "../components/auth/AuthCard.vue";
import LoginForm from "../components/auth/LoginForm.vue";
import RegisterForm from "../components/auth/RegisterForm.vue";
import { useAuthStore } from "../stores/auth";
import { isAdminUser, userAuthError } from "../utils/auth";

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

onMounted(() => {
	if (!authStore.isAuthenticated) return;
	router.replace(isAdminUser(authStore.user) ? "/admin/" : "/");
});

const isRegister = ref(false);
// ?mode=signup opens the register form (header Sign up button).
// Watched (not read once): in-SPA /login → /login?mode=signup reuses the
// component, so the form must follow query changes incl. back/forward.
watch(
	() => route.query.mode,
	(mode) => {
		isRegister.value = mode === "signup";
	},
	{ immediate: true },
);
const error = ref("");
const isSubmitting = ref(false);
const busy = computed(() => authStore.loading || isSubmitting.value);

function toggleMode() {
	isRegister.value = !isRegister.value;
	error.value = "";
	// Keep URL in sync so refresh/back matches the visible form (watcher is idempotent)
	router.replace({ query: isRegister.value ? { mode: "signup" } : {} });
}

async function guardAdmin(): Promise<boolean> {
	// New accounts are always role=user, but double-check
	if (isAdminUser(authStore.user)) {
		error.value = "Admin accounts must use Admin Login (/admin/login).";
		await authStore.logout();
		return false;
	}
	return true;
}

async function handleLogin(data: { email: string; password: string }) {
	if (isSubmitting.value) return;
	error.value = "";
	isSubmitting.value = true;
	try {
		await authStore.login(data.email.trim(), data.password);
		if (!(await guardAdmin())) return;
		await router.push("/");
	} catch (err: unknown) {
		error.value = userAuthError(err, authStore.error, false);
	} finally {
		isSubmitting.value = false;
	}
}

async function handleRegister(data: { email: string; password: string }) {
	if (isSubmitting.value) return;
	error.value = "";
	isSubmitting.value = true;
	try {
		await authStore.register(data.email.trim(), data.password);
		if (!(await guardAdmin())) return;
		await router.push("/");
	} catch (err: unknown) {
		error.value = userAuthError(err, authStore.error, true);
	} finally {
		isSubmitting.value = false;
	}
}
</script>

<template>
  <AuthCard :icon="isRegister ? 'i-lucide-user-plus' : 'i-lucide-log-in'" :title="isRegister ? 'Create account' : 'Sign in'" :subtitle="isRegister ? 'Register to start chatting' : 'Sign in to continue chatting'">
    <LoginForm v-if="!isRegister" :error="error" :submitting="busy" @submit="handleLogin" />
    <RegisterForm v-else :error="error" :submitting="busy" @submit="handleRegister" />
    <p class="text-center text-sm text-muted mt-4">
      <template v-if="!isRegister">
        Don't have an account?
        <button type="button" class="text-primary font-medium hover:underline" @click="toggleMode">Register</button>
      </template>
      <template v-else>
        Already have an account?
        <button type="button" class="text-primary font-medium hover:underline" @click="toggleMode">Sign in</button>
      </template>
    </p>
  </AuthCard>
</template>
