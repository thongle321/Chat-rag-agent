<script lang="ts" setup>
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

function isAdmin(u: any) { return !!u && (u.role === "admin" || u.is_superuser); }
onMounted(() => {
  if (!authStore.isAuthenticated) return;
  router.replace(isAdmin(authStore.user) ? "/admin/" : "/");
});

const isRegister = ref(false);
// ?mode=signup opens the register form (header Sign up button)
if (route.query.mode === "signup") isRegister.value = true;
const error = ref("");
const isSubmitting = ref(false);
const showPassword = ref(false);
const showConfirm = ref(false);

// Login schema: 2 inputs
const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

// Register schema: 3 inputs inside SAME file
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

type LoginSchema = z.output<typeof loginSchema>;
type RegisterSchema = z.output<typeof registerSchema>;

const loginState = reactive<Partial<LoginSchema>>({
  email: "",
  password: "",
});
const registerState = reactive<Partial<RegisterSchema>>({
  email: "",
  password: "",
  confirmPassword: "",
});

function resolveErrorMessage(err: unknown): string {
  const storeMessage = authStore.error;
  const status =
    (err as any)?.response?.status ??
    (err as any)?.statusCode ??
    (err as any)?.status;
  if (status === 400) return "Invalid data. Check email/password.";
  if (status === 401) return "Incorrect email or password.";
  if (status === 422) return (err as any)?.response?.data?.detail?.[0]?.msg ?? "Invalid input.";
  if (status === 400 && isRegister.value) return "Email already registered.";
  if (status === 429) return "Too many attempts. Wait a moment.";
  if (status && status >= 500) return "Server error. Try again shortly.";
  if (storeMessage) return storeMessage;
  return "Something went wrong. Try again.";
}

function toggleMode() {
  isRegister.value = !isRegister.value;
  error.value = "";
}

async function handleLogin(event: FormSubmitEvent<LoginSchema>) {
  if (isSubmitting.value) return;
  error.value = "";
  isSubmitting.value = true;
  try {
    await authStore.login(event.data.email.trim(), event.data.password);
    if (isAdmin(authStore.user)) {
      error.value = "Admin accounts must use Admin Login (/admin/login).";
      await authStore.logout();
      return;
    }
    await router.push("/");
  } catch (err: unknown) {
    error.value = resolveErrorMessage(err);
  } finally {
    isSubmitting.value = false;
  }
}

async function handleRegister(event: FormSubmitEvent<RegisterSchema>) {
  if (isSubmitting.value) return;
  error.value = "";
  isSubmitting.value = true;
  try {
    await authStore.register(event.data.email.trim(), event.data.password);
    // New accounts are always role=user, but double-check
    if (isAdmin(authStore.user)) {
      error.value = "Admin accounts must use Admin Login.";
      await authStore.logout();
      return;
    }
    await router.push("/");
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
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <UIcon class="h-6 w-6 text-primary" :name="isRegister ? 'i-lucide-user-plus' : 'i-lucide-log-in'" />
          </div>
          <h1 class="text-xl font-bold">{{ isRegister ? "Create account" : "Sign in" }}</h1>
          <p class="text-sm text-muted mt-1">
            {{ isRegister ? "Register to start chatting" : "Sign in to continue chatting" }}
          </p>
        </div>
      </template>

      <!-- LOGIN: 2 inputs -->
      <UForm
        v-if="!isRegister"
        class="flex flex-col gap-4"
        :schema="loginSchema"
        :state="loginState"
        @submit="handleLogin"
      >
        <UFormField label="Email" name="email" required>
          <UInput v-model="loginState.email" class="w-full" icon="i-lucide-mail" placeholder="you@example.com" type="email" autocomplete="username" autofocus />
        </UFormField>
        <UFormField label="Password" name="password" required>
          <UInput
            v-model="loginState.password"
            class="w-full"
            icon="i-lucide-key-round"
            placeholder="Enter your password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
          >
            <template #trailing>
              <UButton
                color="neutral"
                variant="link"
                size="sm"
                :icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
                @click="showPassword = !showPassword"
              />
            </template>
          </UInput>
        </UFormField>
        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />
        <UButton block size="lg" type="submit" :loading="authStore.loading || isSubmitting" :disabled="authStore.loading || isSubmitting">
          {{ authStore.loading || isSubmitting ? "Signing in…" : "Sign In" }}
        </UButton>
        <p class="text-center text-sm text-muted">
          Don't have an account?
          <button type="button" class="text-primary font-medium hover:underline" @click="toggleMode">Register</button>
        </p>
      </UForm>

      <!-- REGISTER: 3 inputs — same file, not separate -->
      <UForm
        v-else
        class="flex flex-col gap-4"
        :schema="registerSchema"
        :state="registerState"
        @submit="handleRegister"
      >
        <UFormField label="Email" name="email" required>
          <UInput v-model="registerState.email" class="w-full" icon="i-lucide-mail" placeholder="you@example.com" type="email" autocomplete="email" autofocus />
        </UFormField>
        <UFormField label="Password" name="password" required>
          <UInput
            v-model="registerState.password"
            class="w-full"
            icon="i-lucide-key-round"
            placeholder="At least 6 characters"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
          >
            <template #trailing>
              <UButton
                color="neutral"
                variant="link"
                size="sm"
                :icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                @click="showPassword = !showPassword"
              />
            </template>
          </UInput>
        </UFormField>
        <UFormField label="Confirm password" name="confirmPassword" required>
          <UInput
            v-model="registerState.confirmPassword"
            class="w-full"
            icon="i-lucide-key-round"
            placeholder="Confirm your password"
            :type="showConfirm ? 'text' : 'password'"
            autocomplete="new-password"
          >
            <template #trailing>
              <UButton
                color="neutral"
                variant="link"
                size="sm"
                :icon="showConfirm ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                @click="showConfirm = !showConfirm"
              />
            </template>
          </UInput>
        </UFormField>
        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />
        <UButton block size="lg" type="submit" :loading="authStore.loading || isSubmitting" :disabled="authStore.loading || isSubmitting">
          {{ authStore.loading || isSubmitting ? "Creating account…" : "Create account" }}
        </UButton>
        <p class="text-center text-sm text-muted">
          Already have an account?
          <button type="button" class="text-primary font-medium hover:underline" @click="toggleMode">Sign in</button>
        </p>
      </UForm>
    </UCard>
  </div>
</template>
