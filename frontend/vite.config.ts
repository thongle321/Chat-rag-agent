import ui from "@nuxt/ui/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vueRouter from "vue-router/vite";

export default defineConfig({
	plugins: [
		vueRouter({
			dts: "src/route-map.d.ts",
		}),
		vue(),
		ui({
			autoImport: {
				imports: ["vue", "vue-router", "@vueuse/core"],
			},
			prose: true,
			ui: {
				colors: {
					neutral: "slate",
					primary: "blue",
				},
			},
		}),
	],
	server: {
		port: 3000,
		proxy: {
			"/api": {
				changeOrigin: true,
				target: "http://localhost:8000",
			},
		},
	},
});
