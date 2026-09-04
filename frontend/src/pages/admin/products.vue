<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import api from "../../api/index";

const toast = useToast();

type Product = {
	id: string;
	name: string;
	description?: string;
	price?: number | null;
	currency?: string | null;
	image_url?: string | null;
	product_url?: string | null;
	category?: string | null;
	stock?: number | null;
	source?: string | null;
};

const products = ref<Product[]>([]);
const loading = ref(false);
const saving = ref(false);
const importing = ref(false);
const query = ref("");
const sortBy = ref<keyof Product>("name");
const sortDir = ref<"asc" | "desc">("asc");

const modalOpen = ref(false);
const editing = ref<Product | null>(null);
const form = ref({
	name: "",
	description: "",
	price: null as number | null,
	currency: "USD",
	image_url: "",
	product_url: "",
	category: "",
	stock: 0,
});

const connectOpen = ref(false);
const catalog = ref({
	enabled: false,
	endpoint: "",
	profile_url: "",
	catalog_id: "",
});
const catalogSaving = ref(false);
const catalogTesting = ref(false);
const catalogError = ref("");
const productTab = ref<"manual" | "csv">("manual");
const csvInputRef = ref<HTMLInputElement | null>(null);

const filtered = computed(() => {
	let list = products.value.slice();
	const q = query.value.trim().toLowerCase();
	if (q) {
		list = list.filter(
			(p) =>
				(p.name || "").toLowerCase().includes(q) ||
				(p.category || "").toLowerCase().includes(q),
		);
	}
	list.sort((a, b) => {
		const av = a[sortBy.value];
		const bv = b[sortBy.value];
		const aStr = (av ?? "").toString().toLowerCase();
		const bStr = (bv ?? "").toString().toLowerCase();
		const cmp = aStr < bStr ? -1 : aStr > bStr ? 1 : 0;
		return sortDir.value === "asc" ? cmp : -cmp;
	});
	return list;
});

function toggleSort(field: keyof Product) {
	if (sortBy.value === field) {
		sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
	} else {
		sortBy.value = field;
		sortDir.value = "asc";
	}
}

function openCreate() {
	editing.value = null;
	form.value = {
		name: "",
		description: "",
		price: null,
		currency: "USD",
		image_url: "",
		product_url: "",
		category: "",
		stock: 0,
	};
	productTab.value = "manual";
	modalOpen.value = true;
}

function openEdit(p: Product) {
	editing.value = p;
	form.value = {
		name: p.name,
		description: p.description || "",
		price: p.price ?? null,
		currency: p.currency || "USD",
		image_url: p.image_url || "",
		product_url: p.product_url || "",
		category: p.category || "",
		stock: p.stock ?? 0,
	};
	productTab.value = "manual";
	modalOpen.value = true;
}

async function load() {
	loading.value = true;
	try {
		const { data } = await api.get("/products/");
		products.value = data.products ?? [];
	} finally {
		loading.value = false;
	}
}

async function submit() {
	if (!form.value.name.trim()) return;
	saving.value = true;
	const payload = {
		name: form.value.name.trim(),
		description: form.value.description.trim() || "",
		price: form.value.price ?? null,
		currency: form.value.currency.trim() || "USD",
		image_url: form.value.image_url.trim() || "",
		product_url: form.value.product_url.trim() || "",
		category: form.value.category.trim() || "",
		stock: form.value.stock ?? 0,
	};
	try {
		if (editing.value) {
			await api.put(`/products/${editing.value.id}`, payload);
		} else {
			await api.post("/products/", payload);
		}
		modalOpen.value = false;
		await load();
	} finally {
		saving.value = false;
	}
}

async function remove(id: string) {
	if (!confirm("Delete this product?")) return;
	await api.delete(`/products/${id}`);
	await load();
}

async function uploadCsv(e: Event) {
	const input = e.target as HTMLInputElement;
	const f = input.files?.[0];
	if (!f) return;
	importing.value = true;
	try {
		const fd = new FormData();
		fd.append("file", f);
		const { data } = await api.post("/products/import-csv", fd);
		modalOpen.value = false;
		await load();
		toast.add({
			color: (data.imported ?? 0) > 0 ? "success" : "warning",
			description:
				`Imported ${data.imported ?? 0} products` +
				(data.skipped
					? `, skipped ${data.skipped} rows missing name/price.`
					: "."),
			icon: "i-lucide-file-spreadsheet",
			timeout: 6000,
			title: "CSV import",
		});
	} finally {
		importing.value = false;
		input.value = "";
	}
}

async function loadCatalog() {
	try {
		const { data } = await api.get("/settings/shopify-catalog");
		catalog.value = { ...catalog.value, ...data };
	} catch {
		// catalog stays disabled until connected
	}
}

async function saveCatalog() {
	catalogSaving.value = true;
	catalogError.value = "";
	try {
		const { data } = await api.put("/settings/shopify-catalog", {
			enabled: catalog.value.enabled,
			endpoint: catalog.value.endpoint,
			profile_url: catalog.value.profile_url,
			catalog_id: catalog.value.catalog_id,
		});
		catalog.value = { ...catalog.value, ...data };
		connectOpen.value = false;
		toast.add({
			color: "success",
			description: catalog.value.enabled
				? "Shopify catalog recommendations enabled."
				: "Shopify catalog disabled.",
			icon: "i-lucide-check-circle",
			timeout: 5000,
			title: "Saved",
		});
	} catch (e: any) {
		catalogError.value =
			e?.response?.data?.detail || "Could not save catalog settings.";
	} finally {
		catalogSaving.value = false;
	}
}

async function testCatalog() {
	catalogTesting.value = true;
	catalogError.value = "";
	try {
		const { data } = await api.post("/settings/shopify-catalog/test");
		if (!data.ok) {
			catalogError.value = data.message;
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
		catalogError.value = e?.response?.data?.detail || "Connection test failed.";
	} finally {
		catalogTesting.value = false;
	}
}

function openConnect() {
	catalogError.value = "";
	connectOpen.value = true;
	loadCatalog();
}

onMounted(() => {
	load();
});
</script>

<template>
  <UDashboardPanel id="products">
    <template #header>
      <UDashboardNavbar title="Products">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="px-6 py-3 flex items-center justify-end gap-2">
        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-shopping-bag"
          label="Shopify Catalog"
          @click="openConnect"
        />
        <UButton
          color="primary"
          variant="solid"
          icon="i-lucide-plus"
          label="Add product"
          @click="openCreate"
        />
      </div>
      <!-- ponytail: full-height card flex column with overflow table; paginate when catalog > 500 -->
      <UCard class="flex-1 flex flex-col min-h-0" :ui="{ body: 'p-0 flex-1 flex flex-col min-h-0 overflow-hidden' }">
        <template #header>
          <div class="flex items-center justify-end gap-2">
            <UInput
              v-model="query"
              icon="i-lucide-search"
              placeholder="Search name, category…"
              class="w-72"
            />
          </div>
        </template>
        <!-- Table / States -->
        <div v-if="loading" class="flex-1 flex items-center justify-center p-12 text-muted text-sm gap-2">
          <UIcon name="i-lucide-loader-2" class="size-4 animate-spin text-primary" />
          <span>Loading catalog…</span>
        </div>

        <div v-else-if="!products.length" class="flex-1 flex flex-col items-center justify-center gap-3 p-12 text-center">
          <div class="p-3 rounded-full bg-muted/20 text-muted">
            <UIcon name="i-lucide-package" class="size-8" />
          </div>
          <div class="flex flex-col gap-1">
            <p class="font-medium text-default">No products yet</p>
            <p class="text-xs text-muted max-w-sm">Add manual products or import catalog via CSV or Shopify to start powering chat recommendations.</p>
          </div>
        </div>

        <div v-else-if="!filtered.length" class="flex-1 flex flex-col items-center justify-center gap-2 p-12 text-center text-muted">
          <UIcon name="i-lucide-search-x" class="size-6" />
          <p class="text-sm">No products matching "{{ query }}"</p>
          <UButton variant="ghost" size="xs" label="Clear search" @click="query = ''" />
        </div>

        <div v-else class="flex-1 min-h-0 overflow-auto">
          <table class="w-full text-sm">
            <thead class="text-left text-xs uppercase tracking-wider text-muted bg-elevated/50 sticky top-0 z-10 border-b border-default backdrop-blur-xs">
              <tr>
                <th class="py-3 px-4 w-16">Image</th>
                <th class="py-3 px-4 cursor-pointer select-none" @click="toggleSort('name')">
                  <span class="inline-flex items-center gap-1.5 font-medium">
                    Name
                    <UIcon
                      :name="sortBy === 'name' ? (sortDir === 'asc' ? 'i-lucide-arrow-up' : 'i-lucide-arrow-down') : 'i-lucide-arrow-up-down'"
                      class="size-3.5"
                      :class="sortBy === 'name' ? 'text-primary' : 'opacity-40'"
                    />
                  </span>
                </th>
                <th class="py-3 px-4">Category</th>
                <th class="py-3 px-4 cursor-pointer select-none" @click="toggleSort('price')">
                  <span class="inline-flex items-center gap-1.5 font-medium">
                    Price
                    <UIcon
                      :name="sortBy === 'price' ? (sortDir === 'asc' ? 'i-lucide-arrow-up' : 'i-lucide-arrow-down') : 'i-lucide-arrow-up-down'"
                      class="size-3.5"
                      :class="sortBy === 'price' ? 'text-primary' : 'opacity-40'"
                    />
                  </span>
                </th>
                <th class="py-3 px-4 cursor-pointer select-none" @click="toggleSort('stock')">
                  <span class="inline-flex items-center gap-1.5 font-medium">
                    Stock
                    <UIcon
                      :name="sortBy === 'stock' ? (sortDir === 'asc' ? 'i-lucide-arrow-up' : 'i-lucide-arrow-down') : 'i-lucide-arrow-up-down'"
                      class="size-3.5"
                      :class="sortBy === 'stock' ? 'text-primary' : 'opacity-40'"
                    />
                  </span>
                </th>
                <th class="py-3 px-4 text-right w-24">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-default">
              <tr
                v-for="p in filtered"
                :key="p.id"
                class="hover:bg-elevated/40 transition-colors"
              >
                <td class="py-2.5 px-4 align-middle">
                  <img
                    v-if="p.image_url"
                    :src="p.image_url"
                    :alt="p.name"
                    class="size-10 rounded-md object-cover ring-1 ring-default bg-muted/10"
                    loading="lazy"
                  />
                  <div
                    v-else
                    class="size-10 rounded-md bg-muted/20 flex items-center justify-center text-muted"
                  >
                    <UIcon name="i-lucide-image" class="size-4" />
                  </div>
                </td>
                <td class="py-2.5 px-4 align-middle max-w-xs">
                  <div class="font-medium text-default truncate">{{ p.name }}</div>
                  <div class="text-xs text-muted truncate">{{ p.description || "No description" }}</div>
                </td>
                <td class="py-2.5 px-4 align-middle">
                  <UBadge v-if="p.category" variant="subtle" color="neutral" size="sm">
                    {{ p.category }}
                  </UBadge>
                  <span v-else class="text-muted text-xs">—</span>
                </td>
                <td class="py-2.5 px-4 align-middle text-default font-medium">
                  {{ p.price != null ? p.price.toLocaleString() : "—" }}
                </td>
                <td class="py-2.5 px-4 align-middle">
                  <UBadge
                    v-if="p.stock != null"
                    :color="p.stock > 10 ? 'success' : p.stock > 0 ? 'warning' : 'error'"
                    variant="subtle"
                    size="sm"
                  >
                    {{ p.stock }} in stock
                  </UBadge>
                  <span v-else class="text-muted text-xs">—</span>
                </td>
                <td class="py-2.5 px-4 align-middle text-right">
                  <div class="inline-flex items-center gap-1 justify-end">
                    <UButton
                      size="xs"
                      variant="ghost"
                      color="neutral"
                      icon="i-lucide-pen"
                      title="Edit"
                      @click="openEdit(p)"
                    />
                    <UButton
                      size="xs"
                      color="error"
                      variant="ghost"
                      icon="i-lucide-trash"
                      title="Delete"
                      @click="remove(p.id)"
                    />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UCard>
    </template>
  </UDashboardPanel>

  <!-- Modal: Add / Edit Product -->
  <UModal v-model:open="modalOpen" :title="editing ? 'Edit product' : 'Add product'" :description="editing ? 'Update product details in catalog' : 'Create a new product for recommendations'">
    <template #body>
      <div class="grid grid-cols-2 p-1 bg-muted/20 rounded-lg text-sm mb-3">
        <button
          type="button"
          class="py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-2"
          :class="productTab === 'manual' ? 'bg-elevated text-default shadow-xs' : 'text-muted hover:text-default'"
          @click="productTab = 'manual'"
        >
          <UIcon name="i-lucide-plus" class="size-4" />
          <span>Manual</span>
        </button>
        <button
          type="button"
          class="py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-2"
          :class="productTab === 'csv' ? 'bg-elevated text-default shadow-xs' : 'text-muted hover:text-default'"
          @click="productTab = 'csv'"
        >
          <UIcon name="i-lucide-file-spreadsheet" class="size-4" />
          <span>Import CSV</span>
        </button>
      </div>
      <form v-if="productTab === 'manual'" class="flex flex-col gap-3" @submit.prevent="submit">
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
      <input
        ref="csvInputRef"
        type="file"
        accept=".csv"
        class="hidden"
        @change="uploadCsv"
      />
      <div
        class="border-2 border-dashed border-default rounded-lg p-6 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-primary transition-colors bg-elevated/20"
        @click="csvInputRef?.click()"
      >
        <UIcon :name="importing ? 'i-lucide-loader-2' : 'i-lucide-upload'" class="size-8 text-muted" :class="{ 'animate-spin text-primary': importing }" />
        <div class="text-sm font-medium text-default">
          {{ importing ? 'Importing CSV…' : 'Click to select CSV file' }}
        </div>
        <span class="text-xs text-muted">.csv files up to 50MB</span>
      </div>
      </div>
    </template>

    <template #footer>
      <div v-if="productTab === 'manual'" class="flex justify-end gap-2 w-full">
        <UButton variant="ghost" color="neutral" label="Cancel" :disabled="saving" @click="modalOpen = false" />
        <UButton color="primary" variant="solid" :label="editing ? 'Save changes' : 'Create product'" :loading="saving" @click="submit" />
      </div>
      <div v-else class="flex justify-end w-full">
        <UButton variant="ghost" color="neutral" label="Close" @click="modalOpen = false" />
      </div>
    </template>
  </UModal>

  <!-- Modal: Shopify Global Catalog -->
  <UModal v-model:open="connectOpen" title="Shopify Global Catalog" description="Live product recommendations from all Shopify merchants — no API key, nothing is saved">
    <template #body>
      <div class="flex flex-col gap-4">
        <div v-if="catalogError" class="p-2.5 rounded-md bg-error/10 border border-error/30 text-xs text-error">
          {{ catalogError }}
        </div>
        <p class="text-xs text-muted">Chat searches this catalog when your local products have no match. Results are live and never saved.</p>
        <UFormField label="Enabled">
          <USwitch v-model="catalog.enabled" />
        </UFormField>
        <UFormField label="Catalog endpoint" hint="Default connects to Shopify's global catalog.">
          <UInput v-model="catalog.endpoint" placeholder="https://catalog.shopify.com/api/ucp/mcp" class="w-full font-mono text-sm" />
        </UFormField>
        <UFormField label="Agent profile URL">
          <UInput v-model="catalog.profile_url" placeholder="https://shopify.dev/ucp/agent-profiles/2026-08-25/valid-with-capabilities.json" class="w-full font-mono text-sm" />
        </UFormField>
        <UFormField label="Saved catalog ID (optional)" hint="Only if you created a saved catalog in the Dev Dashboard.">
          <UInput v-model="catalog.catalog_id" placeholder="" class="w-full font-mono text-sm" />
        </UFormField>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2 w-full">
        <UButton variant="outline" color="neutral" label="Test Connection" :loading="catalogTesting" @click="testCatalog" />
        <UButton color="primary" variant="solid" label="Save" :loading="catalogSaving" @click="saveCatalog" />
      </div>
    </template>
  </UModal>
</template>
