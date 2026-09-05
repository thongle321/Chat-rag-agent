import { onMounted, ref } from "vue";
import api from "../api/index.ts";
import { useAuthStore } from "../stores/auth";
import { isAdminUser } from "../utils/auth";

// Backend feature-aware: doc count (admin-only endpoint — a non-admin GET
// returns 403 "Admin only", which the axios interceptor turns into a /login
// hard-redirect, i.e. an infinite reload loop right after register/login).
export function useDocCount() {
	const authStore = useAuthStore();
	const docCount = ref<number | null>(null);

	onMounted(async () => {
		if (!isAdminUser(authStore.user)) return;
		try {
			const { data } = await api.get("/documents");
			docCount.value = data?.documents?.length ?? 0;
		} catch {
			docCount.value = null;
		}
	});

	return { docCount };
}
