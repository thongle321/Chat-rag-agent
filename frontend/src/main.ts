import "./assets/css/main.css";

import ui from "@nuxt/ui/vue-plugin";
import { createHead } from "@unhead/vue/client";
import { createPinia } from "pinia";
import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { routes as autoRoutes, handleHotUpdate } from "vue-router/auto-routes";
import App from "./App.vue";
import { useAuthStore } from "./stores/auth.ts";

const app = createApp(App);
const head = createHead();
const router = createRouter({
	history: createWebHistory(),
	routes: autoRoutes,
});

app.use(createPinia());
app.use(head);
app.use(router);
app.use(ui);

app.config.errorHandler = (err, _instance, info) => {
	console.error("[vue]", info, err);
};

function isAdminUser(u: any) { return !!u && (u.role === "admin" || u.is_superuser); }

router.beforeEach(async (to) => {
	const auth = useAuthStore();
	if (auth.token && !auth.user) {
		await auth.fetchUser();
	}
	const isAuthed = auth.isAuthenticated;
	const isAdmin = isAdminUser(auth.user);

	// Admin area — only admin role
	if (to.path.startsWith("/admin")) {
		if (to.path === "/admin/login") {
			if (isAuthed) return isAdmin ? "/admin/" : "/login";
			return;
		}
		if (!isAuthed) return "/admin/login";
		if (!isAdmin) return "/login"; // user cannot access admin
		return;
	}

	// User area — only non-admin role (strict separation, cannot be logged as both)
	if (to.path === "/login") {
		if (isAuthed) return isAdmin ? "/admin/" : "/";
		return;
	}
	if (to.path === "/") {
		// Chat like ChatGPT: public, no login required — only redirect logged-in admin to dashboard
		if (isAdmin) return "/admin/"; // admin must use /admin, not user chat
		return;
	}
});

app.mount("#app");

if (import.meta.hot) {
	handleHotUpdate(router);
}
