import { computed } from "vue";
import { useAuthStore } from "../stores/auth";

// Time-of-day greeting for the blank composer (ChatGPT-style, no quick prompts).
export function useGreeting() {
	const authStore = useAuthStore();
	return computed(() => {
		const h = new Date().getHours();
		let t = "Good evening";
		if (h < 12) t = "Good morning";
		else if (h < 18) t = "Good afternoon";
		const name = authStore.user?.email?.split("@")[0] || "";
		return name ? `${t}, ${name}` : t;
	});
}
