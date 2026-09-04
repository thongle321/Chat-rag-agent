import { defineStore } from "pinia";
import { computed, ref } from "vue";
import api, { getErrorMessage } from "../api/index.ts";
import { useChatStore } from "./chat.ts";

interface User {
	email: string;
	id: string;
	is_active: boolean;
	is_superuser: boolean;
	role: string;
}

export const useAuthStore = defineStore("auth", () => {
	const user = ref<User | null>(null);
	const token = ref<string>(localStorage.getItem("auth_token") || "");
	const loading = ref(false);
	const error = ref("");

	const isAuthenticated = computed(() => !!token.value && !!user.value);

	// Set auth token on axios instance
	function setToken(newToken: string) {
		token.value = newToken;
		if (newToken) {
			localStorage.setItem("auth_token", newToken);
			api.defaults.headers.common.Authorization = `Bearer ${newToken}`;
		} else {
			localStorage.removeItem("auth_token");
			api.defaults.headers.common.Authorization = undefined;
		}
	}

	// Initialize token from localStorage on load
	if (token.value) {
		api.defaults.headers.common.Authorization = `Bearer ${token.value}`;
	}

	// Sessions belong to the account: entering an account restores its bucket
	// (server list), leaving drops to the separate anon bucket.
	async function syncChatBucket() {
		try {
			const chat = useChatStore();
			if (user.value) {
				chat.switchIdentity(`user:${user.value.id}`);
				await chat.loadServerSessions();
			} else {
				chat.switchIdentity("anon");
			}
		} catch {
			// sidebar keeps whatever is cached
		}
	}

	async function login(email: string, password: string) {
		loading.value = true;
		error.value = "";
		try {
			// fastapi-users expects form-data for login
			const formData = new URLSearchParams();
			formData.append("username", email);
			formData.append("password", password);

			const { data } = await api.post("/auth/login", formData, {
				headers: { "Content-Type": "application/x-www-form-urlencoded" },
			});
			setToken(data.access_token);
			await fetchUser();
			if (user.value) {
				await syncChatBucket();
			}
		} catch (err: any) {
			error.value = getErrorMessage(err);
			throw err;
		} finally {
			loading.value = false;
		}
	}

	async function register(email: string, password: string) {
		loading.value = true;
		error.value = "";
		try {
			await api.post("/auth/register", { email, password });
			// Auto-login after successful registration
			await login(email, password);
		} catch (err: any) {
			error.value = getErrorMessage(err);
			throw err;
		} finally {
			loading.value = false;
		}
	}

	async function logout() {
		try {
			await api.post("/auth/logout", null, {
				headers: token.value ? { Authorization: `Bearer ${token.value}` } : {},
			});
		} catch {
			// Ignore — token may be expired, local cleanup is what matters
		}
		setToken("");
		user.value = null;
		await syncChatBucket();
	}

	async function fetchUser() {
		if (!token.value) {
			return;
		}
		const wasLoggedOut = !user.value;
		try {
			const { data } = await api.get("/auth/me");
			user.value = data;
			// Boot path (router guard): returning account restores its bucket.
			if (wasLoggedOut && user.value) {
				await syncChatBucket();
			}
		} catch {
			setToken("");
			user.value = null;
		}
	}

	return {
		error,
		fetchUser,
		isAuthenticated,
		loading,
		login,
		logout,
		register,
		token,
		user,
	};
});
