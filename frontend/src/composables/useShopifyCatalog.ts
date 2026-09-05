import { ref } from "vue";
import api from "../api/index.ts";

// Shopify Global Catalog connect (Products page modal): live recommendations
// from all Shopify merchants — no API key, nothing is saved.
export function useShopifyCatalog() {
	const toast = useToast();
	const catalog = ref({ enabled: false, endpoint: "", profile_url: "", catalog_id: "" });
	const saving = ref(false);
	const testing = ref(false);
	const error = ref("");

	async function load() {
		try {
			const { data } = await api.get("/settings/shopify-catalog");
			catalog.value = { ...catalog.value, ...data };
		} catch {
			// catalog stays disabled until connected
		}
	}

	function resetError() {
		error.value = "";
	}

	async function save(): Promise<boolean> {
		saving.value = true;
		error.value = "";
		try {
			const { data } = await api.put("/settings/shopify-catalog", {
				enabled: catalog.value.enabled,
				endpoint: catalog.value.endpoint,
				profile_url: catalog.value.profile_url,
				catalog_id: catalog.value.catalog_id,
			});
			catalog.value = { ...catalog.value, ...data };
			toast.add({
				color: "success",
				description: catalog.value.enabled ? "Shopify catalog enabled." : "Shopify catalog disabled.",
				icon: "i-lucide-check-circle",
				timeout: 5000,
				title: "Saved",
			});
			return true;
		} catch (e: any) {
			error.value = e?.response?.data?.detail || "Could not save catalog settings.";
			return false;
		} finally {
			saving.value = false;
		}
	}

	async function test() {
		testing.value = true;
		error.value = "";
		try {
			const { data } = await api.post("/settings/shopify-catalog/test");
			if (!data.ok) {
				error.value = data.message;
			} else {
				toast.add({
					color: "success",
					description: data.message,
					icon: "i-lucide-check-circle",
					timeout: 5000,
					title: "Connected",
				});
			}
		} catch (e: any) {
			error.value = e?.response?.data?.detail || "Connection test failed.";
		} finally {
			testing.value = false;
		}
	}

	return { catalog, error, load, resetError, save, saving, test, testing };
}
