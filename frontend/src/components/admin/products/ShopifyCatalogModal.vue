<script setup lang="ts">
import { useShopifyCatalog } from "../../../composables/useShopifyCatalog";

const open = defineModel<boolean>("open", { default: false });
const catalog = useShopifyCatalog();

watch(open, (v) => {
	if (v) {
		catalog.resetError();
		catalog.load();
	}
});

async function onSave() {
	if (await catalog.save()) open.value = false;
}
</script>

<template>
  <UModal v-model:open="open" title="Shopify Global Catalog" description="Live product recommendations from all Shopify merchants — no API key, nothing is saved">
    <template #body>
      <div class="flex flex-col gap-4">
        <div v-if="catalog.error.value" class="p-2.5 rounded-md bg-error/10 border border-error/30 text-xs text-error">
          {{ catalog.error.value }}
        </div>
        <p class="text-xs text-muted">Chat searches this catalog when your local products have no match. Results are live and never saved.</p>
        <UFormField label="Enabled">
          <USwitch v-model="catalog.catalog.value.enabled" />
        </UFormField>
        <UFormField label="Catalog endpoint" hint="Default connects to Shopify's global catalog.">
          <UInput v-model="catalog.catalog.value.endpoint" placeholder="https://catalog.shopify.com/api/ucp/mcp" class="w-full font-mono text-sm" />
        </UFormField>
        <UFormField label="Agent profile URL">
          <UInput v-model="catalog.catalog.value.profile_url" placeholder="https://shopify.dev/ucp/agent-profiles/2026-08-25/valid-with-capabilities.json" class="w-full font-mono text-sm" />
        </UFormField>
        <UFormField label="Saved catalog ID (optional)" hint="Only if you created a saved catalog in the Dev Dashboard.">
          <UInput v-model="catalog.catalog.value.catalog_id" placeholder="" class="w-full font-mono text-sm" />
        </UFormField>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2 w-full">
        <UButton variant="outline" color="neutral" label="Test Connection" :loading="catalog.testing.value" @click="catalog.test" />
        <UButton color="primary" variant="solid" label="Save" :loading="catalog.saving.value" @click="onSave" />
      </div>
    </template>
  </UModal>
</template>
