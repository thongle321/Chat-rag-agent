<script setup lang="ts">
import { blankProductForm, type Product, type ProductForm } from "../../../composables/useProductCatalog";

const open = defineModel<boolean>("open", { default: false });
const props = defineProps<{ editing: Product | null; saving: boolean; importing: boolean }>();
const emit = defineEmits<{ submit: [form: ProductForm]; import: [file: File] }>();

const tab = ref<"manual" | "csv">("manual");
const form = ref<ProductForm>(blankProductForm());
const csvInput = useTemplateRef<HTMLInputElement>("csvInput");

watch(open, (v) => {
	if (!v) return;
	tab.value = "manual";
	const p = props.editing;
	form.value = p
		? {
				name: p.name,
				description: p.description || "",
				price: p.price ?? null,
				currency: p.currency || "USD",
				image_url: p.image_url || "",
				product_url: p.product_url || "",
				category: p.category || "",
				stock: p.stock ?? 0,
			}
		: blankProductForm();
});

function onFile(e: Event) {
	const f = (e.target as HTMLInputElement).files?.[0];
	if (!f) return;
	emit("import", f);
	(e.target as HTMLInputElement).value = "";
}
</script>

<template>
  <UModal v-model:open="open" :title="editing ? 'Edit product' : 'Add product'" :description="editing ? 'Update product details in catalog' : 'Create a new product for recommendations'">
    <template #body>
      <div class="grid grid-cols-2 p-1 bg-muted/20 rounded-lg text-sm mb-3">
        <button
          type="button"
          class="py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-2"
          :class="tab === 'manual' ? 'bg-elevated text-default shadow-xs' : 'text-muted hover:text-default'"
          @click="tab = 'manual'"
        >
          <UIcon name="i-lucide-plus" class="size-4" />
          <span>Manual</span>
        </button>
        <button
          type="button"
          class="py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-2"
          :class="tab === 'csv' ? 'bg-elevated text-default shadow-xs' : 'text-muted hover:text-default'"
          @click="tab = 'csv'"
        >
          <UIcon name="i-lucide-file-spreadsheet" class="size-4" />
          <span>Import CSV</span>
        </button>
      </div>
      <form v-if="tab === 'manual'" class="flex flex-col gap-3" @submit.prevent="emit('submit', form)">
        <div class="grid sm:grid-cols-2 gap-3">
          <div class="sm:col-span-2">
            <UFormField label="Product name *" required>
              <UInput v-model="form.name" placeholder="e.g. Arabica Coffee Beans" class="w-full" />
            </UFormField>
          </div>
          <UFormField label="Category">
            <UInput v-model="form.category" placeholder="e.g. Beverages" class="w-full" />
          </UFormField>
          <UFormField label="Price (USD)">
            <UInput v-model.number="form.price" type="number" step="any" placeholder="0.00" class="w-full" />
          </UFormField>
          <UFormField label="Stock">
            <UInput v-model.number="form.stock" type="number" placeholder="0" class="w-full" />
          </UFormField>
          <UFormField label="Image URL">
            <UInput v-model="form.image_url" placeholder="https://..." class="w-full" />
          </UFormField>
          <div class="sm:col-span-2">
            <UFormField label="Checkout / Product URL">
              <UInput v-model="form.product_url" placeholder="https://store.com/products/..." class="w-full" />
            </UFormField>
          </div>
          <div class="sm:col-span-2">
            <UFormField label="Description">
              <UTextarea v-model="form.description" placeholder="Short description used for product matching and recommendations…" :rows="3" class="w-full" />
            </UFormField>
          </div>
        </div>
      </form>
      <div v-else class="flex flex-col gap-3">
        <div class="p-3 rounded-md bg-elevated/60 border border-default text-xs text-muted flex flex-col gap-1">
          <span class="font-medium text-default">Supported columns:</span>
          <code class="font-mono text-[11px] break-all">name, description, price, currency, image_url, product_url, category, stock</code>
        </div>
        <input ref="csvInput" type="file" accept=".csv" class="hidden" @change="onFile" />
        <div
          class="border-2 border-dashed border-default rounded-lg p-6 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-primary transition-colors bg-elevated/20"
          @click="csvInput?.click()"
        >
          <UIcon :name="importing ? 'i-lucide-loader-2' : 'i-lucide-upload'" class="size-8 text-muted" :class="{ 'animate-spin text-primary': importing }" />
          <div class="text-sm font-medium text-default">{{ importing ? "Importing CSV…" : "Click to select CSV file" }}</div>
          <span class="text-xs text-muted">.csv files up to 50MB</span>
        </div>
      </div>
    </template>

    <template #footer>
      <div v-if="tab === 'manual'" class="flex justify-end gap-2 w-full">
        <UButton variant="ghost" color="neutral" label="Cancel" :disabled="saving" @click="open = false" />
        <UButton color="primary" variant="solid" :label="editing ? 'Save changes' : 'Create product'" :loading="saving" @click="emit('submit', form)" />
      </div>
      <div v-else class="flex justify-end w-full">
        <UButton variant="ghost" color="neutral" label="Close" @click="open = false" />
      </div>
    </template>
  </UModal>
</template>
