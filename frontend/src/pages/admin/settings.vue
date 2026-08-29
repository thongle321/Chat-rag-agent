<script lang="ts" setup>
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import { useSettingsStore } from "../../stores/settings";

const settingsStore = useSettingsStore();
const toast = useToast();

const saving = ref(false);
const error = ref("");
const showOpenaiKey = ref(false);
const showOllamaKey = ref(false);
const testing = ref(false);

const required = (label: string) =>
	z.preprocess(
		(v: unknown) => v ?? "",
		z
			.string()
			.trim()
			.min(1, { message: `${label} is required` }),
	);

const schema = computed(() => {
	const base: Record<string, z.ZodType> = {
		ai_provider: z.string(),
		ollama_api_key: z.string().default(""),
		ollama_base_url: z.string().default(""),
		ollama_model: z.string().default(""),
		openai_api_key: z.string().default(""),
		openai_model: z.string().default(""),
	};
	if (state.ai_provider === "ollama") {
		base.ollama_base_url = required("Base URL");
		base.ollama_model = required("Model Name");
		// ollama_api_key optional — keep as-is
	} else {
		base.openai_api_key = required("API Key");
		base.openai_model = required("Model Name");
	}
	return z.object(base);
});

type Schema = z.output<typeof schema.value>;
const state = reactive<Partial<Schema>>({
	ai_provider: "ollama",
	ollama_api_key: "",
	ollama_base_url: "",
	ollama_model: "",
	openai_api_key: "",
	openai_model: "",
});

const providerOptions = [
	{ label: "Ollama", value: "ollama" },
	{ label: "OpenAI", value: "openai" },
];

onMounted(async () => {
	try {
		await settingsStore.fetchSettings();
		Object.assign(state, settingsStore.settings);
		await ensureModels();
	} catch {
		error.value = settingsStore.error || "Failed to load settings";
	}
});

async function onProviderChange() {
	settingsStore.models = [];
	await ensureModels();
}

async function ensureModels() {
	await settingsStore.useCachedModels(
		state.ai_provider ?? "ollama",
		state.ollama_base_url ?? "",
		{
			ollama_api_key: state.ollama_api_key,
			openai_api_key: state.openai_api_key,
		},
	);
}

async function testConnection() {
	testing.value = true;
	try {
		const result = await settingsStore.testConnection({
			ollama_api_key: state.ollama_api_key,
			ollama_base_url: state.ollama_base_url,
			openai_api_key: state.openai_api_key,
			provider: state.ai_provider,
		});
		toast.add({
			color: result.ok ? "success" : "error",
			description: result.message,
			icon: result.ok ? "i-lucide-check-circle" : "i-lucide-x-circle",
			timeout: result.ok ? 5000 : 0,
			title: result.ok ? "Connected" : "Connection failed",
		});
	} finally {
		testing.value = false;
	}
}

async function refreshModels() {
	await settingsStore.fetchModels({
		ollama_api_key: state.ollama_api_key,
		ollama_base_url: state.ollama_base_url,
		openai_api_key: state.openai_api_key,
		provider: state.ai_provider,
	});
}

async function save(event: FormSubmitEvent<Schema>) {
	error.value = "";

	saving.value = true;
	try {
		const payload: Record<string, string> = {
			ai_provider: event.data.ai_provider,
			ollama_base_url: event.data.ollama_base_url ?? "",
			ollama_model: event.data.ollama_model ?? "",
			openai_model: event.data.openai_model ?? "",
		};
		if (event.data.ai_provider === "ollama" && event.data.ollama_api_key) {
			payload.ollama_api_key = event.data.ollama_api_key;
		}
		if (event.data.ai_provider === "openai" && event.data.openai_api_key) {
			payload.openai_api_key = event.data.openai_api_key;
		}
		await settingsStore.updateSettings(payload);
		toast.add({
			color: "success",
			description: "Settings saved successfully",
			icon: "i-lucide-check",
			timeout: 3000,
			title: "Saved",
		});
	} catch (err: unknown) {
		error.value =
			settingsStore.error ||
			(err instanceof Error ? err.message : "Save failed");
	} finally {
		saving.value = false;
	}
}
</script>

<template>
  <UDashboardPanel id="settings" :ui="{ body: 'lg:py-12' }">
    <template #header>
      <UDashboardNavbar title="Settings">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UForm
        class="flex flex-col gap-4 sm:gap-6 lg:gap-8 w-full lg:max-w-2xl mx-auto"
        :schema="schema"
        :state="state"
        @submit="save"
      >
        <UCard>
          <template #header>
            <span class="font-semibold">AI Provider</span>
          </template>

          <UFormField label="Provider" name="ai_provider">
            <USelect
              class="w-full"
              v-model="state.ai_provider"
              :disabled="saving"
              :items="providerOptions"
              @update:model-value="onProviderChange"
            />
          </UFormField>
        </UCard>

        <UCard v-if="state.ai_provider === 'ollama'">
          <template #header>
            <span class="font-semibold">Ollama Configuration</span>
          </template>

          <div class="flex flex-col gap-4">
            <UFormField label="Base URL" name="ollama_base_url" required>
              <UInput
                class="w-full"
                placeholder="http://localhost:11434"
                v-model="state.ollama_base_url"
                :disabled="saving"
              />
            </UFormField>
            <UFormField label="API Key" name="ollama_api_key">
              <UInput
                class="w-full"
                placeholder="ollama-api-key"
                v-model="state.ollama_api_key"
                :disabled="saving"
                :type="showOllamaKey ? 'text' : 'password'"
              >
                <template #trailing>
                  <UButton
                    size="sm"
                    variant="ghost"
                    :icon="showOllamaKey ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                    @click="showOllamaKey = !showOllamaKey"
                  />
                </template>
              </UInput>
            </UFormField>
            <UFormField label="Model Name" name="ollama_model" required>
              <USelectMenu
                class="w-full"
                create-item
                placeholder="llama3.2"
                search-input
                v-model="state.ollama_model"
                :disabled="saving"
                :items="settingsStore.models"
                :loading="settingsStore.modelLoading"
                @create="(value) => (state.ollama_model = value)"
              >
                <template #trailing>
                  <UButton
                    icon="i-lucide-refresh-cw"
                    size="sm"
                    variant="ghost"
                    :loading="settingsStore.modelLoading"
                    @click.stop="refreshModels"
                  />
                </template>
              </USelectMenu>
            </UFormField>
          </div>
        </UCard>

        <UCard v-if="state.ai_provider === 'openai'">
          <template #header>
            <span class="font-semibold">OpenAI Configuration</span>
          </template>

          <div class="flex flex-col gap-4">
            <UFormField label="API Key" name="openai_api_key" required>
              <UInput
                class="w-full"
                placeholder="sk-..."
                v-model="state.openai_api_key"
                :disabled="saving"
                :type="showOpenaiKey ? 'text' : 'password'"
              >
                <template #trailing>
                  <UButton
                    size="sm"
                    variant="ghost"
                    :icon="showOpenaiKey ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                    @click="showOpenaiKey = !showOpenaiKey"
                  />
                </template>
              </UInput>
            </UFormField>
            <UFormField label="Model Name" name="openai_model" required>
              <USelectMenu
                class="w-full"
                create-item
                placeholder="gpt-4o"
                search-input
                v-model="state.openai_model"
                :disabled="saving"
                :items="settingsStore.models"
                :loading="settingsStore.modelLoading"
                @create="(value) => (state.openai_model = value)"
              >
                <template #trailing>
                  <UButton
                    icon="i-lucide-refresh-cw"
                    size="sm"
                    variant="ghost"
                    :loading="settingsStore.modelLoading"
                    @click.stop="refreshModels"
                  />
                </template>
              </USelectMenu>
            </UFormField>
          </div>
        </UCard>

        <UAlert
          closable
          color="error"
          icon="i-lucide-alert-circle"
          variant="subtle"
          v-if="error"
          :description="error"
          @close="error = ''"
        />

        <div class="flex gap-2">
          <UButton
            type="button"
            variant="outline"
            :loading="testing"
            @click="testConnection"
          >
            Test Connection
          </UButton>
          <UButton type="submit" :loading="saving"> Save </UButton>
        </div>
      </UForm>
    </template>
  </UDashboardPanel>
</template>
