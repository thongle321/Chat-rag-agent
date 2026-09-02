import { defineStore } from "pinia";
import { ref } from "vue";
import api, { getErrorMessage } from "../api/index.ts";

export interface AISettings {
	ai_provider: string;
	ollama_api_key: string;
	ollama_base_url: string;
	ollama_model: string;
	openai_api_key: string;
	openai_model: string;
	zalo_api_key: string;
	zalo_verify_token: string;
	zalo_webhook_url: string;
}

export interface TestResult {
	message: string;
	ok: boolean;
}

export const useSettingsStore = defineStore("settings", () => {
	const settings = ref<AISettings>({
		ai_provider: "ollama",
		ollama_api_key: "",
		ollama_base_url: "",
		ollama_model: "",
		openai_api_key: "",
		openai_model: "",
		zalo_api_key: "",
		zalo_verify_token: "",
		zalo_webhook_url: "",
	});
	const loading = ref(false);
	const error = ref("");
	const models = ref<string[]>([]);
	const modelsCache = ref<Record<string, string[]>>({});
	const modelLoading = ref(false);

	function modelsKey(provider: string, baseUrl = "") {
		return `${provider}|${baseUrl}`;
	}

	async function fetchSettings() {
		loading.value = true;
		error.value = "";
		try {
			const { data } = await api.get("/settings/ai");
			settings.value = data;
		} catch (err: any) {
			error.value = getErrorMessage(err);
		} finally {
			loading.value = false;
		}
	}

	async function updateSettings(payload: Partial<AISettings>) {
		loading.value = true;
		error.value = "";
		try {
			const { data } = await api.put("/settings/ai", payload);
			settings.value = data;
		} catch (err: any) {
			error.value = getErrorMessage(err);
			throw err;
		} finally {
			loading.value = false;
		}
	}

	async function testConnection(opts?: {
		provider?: string;
		ollama_base_url?: string;
		ollama_api_key?: string;
		openai_api_key?: string;
	}): Promise<TestResult> {
		try {
			const { data } = await api.post("/settings/test", opts ?? {});
			return data;
		} catch (err: any) {
			return { message: getErrorMessage(err), ok: false };
		}
	}

	async function fetchModels(opts?: {
		provider?: string;
		ollama_base_url?: string;
		ollama_api_key?: string;
		openai_api_key?: string;
	}) {
		if (modelLoading.value) {
			return;
		}
		modelLoading.value = true;
		error.value = "";
		try {
			const { data } = await api.post("/settings/models", opts ?? {});
			models.value = data.models;
			modelsCache.value[
				modelsKey(opts?.provider ?? "", opts?.ollama_base_url ?? "")
			] = data.models;
		} catch {
			models.value = [];
		} finally {
			modelLoading.value = false;
		}
	}

	async function useCachedModels(
		provider: string,
		baseUrl = "",
		opts?: { ollama_api_key?: string; openai_api_key?: string },
	) {
		const key = modelsKey(provider, baseUrl);
		if (modelsCache.value[key] !== undefined) {
			models.value = modelsCache.value[key];
			return;
		}
		await fetchModels({ ollama_base_url: baseUrl, provider, ...opts });
	}

	return {
		error,
		fetchModels,
		fetchSettings,
		loading,
		modelLoading,
		models,
		settings,
		testConnection,
		updateSettings,
		useCachedModels,
	};
});
