<script setup lang="ts">
import { onMounted, ref } from "vue";
import api from "../../api/index";

const products = ref<any[]>([]);
const loading = ref(false);
const csvFile = ref<File | null>(null);
const shopDomain = ref("");
const shopToken = ref("");
const form = ref({ name: "", description: "", price: null as number | null, currency: "USD", image_url: "", product_url: "", category: "", stock: 0, sku: "" });

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/products/");
    products.value = data.products ?? [];
  } finally { loading.value = false; }
}
async function create() {
  if (!form.value.name.trim()) return;
  await api.post("/products/", { ...form.value, price: form.value.price ?? null });
  form.value = { name: "", description: "", price: null, currency: "USD", image_url: "", product_url: "", category: "", stock: 0, sku: "" };
  await load();
}
async function remove(id: string) {
  await api.delete(`/products/${id}`);
  await load();
}
async function uploadCsv(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  await api.post("/products/import-csv", fd);
  await load();
}
async function syncShopify() {
  if (!shopDomain.value || !shopToken.value) return;
  await api.post("/products/sync-shopify", { shop_domain: shopDomain.value, access_token: shopToken.value });
  await load();
}
onMounted(load);
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto flex flex-col gap-6">
    <h1 class="text-xl font-bold">Products — recommendations catalog</h1>

    <UCard>
      <template #header><span class="font-medium">Add product (manual)</span></template>
      <div class="grid sm:grid-cols-2 gap-2">
        <UInput v-model="form.name" placeholder="Name *" />
        <UInput v-model="form.category" placeholder="Category" />
        <UInput v-model="form.price" type="number" placeholder="Price" />
        <UInput v-model="form.currency" placeholder="Currency (USD)" />
        <UInput v-model="form.image_url" placeholder="Image URL" />
        <UInput v-model="form.product_url" placeholder="Buy / checkout URL" />
        <UInput v-model="form.sku" placeholder="SKU" />
        <UInput v-model="form.stock" type="number" placeholder="Stock" />
      </div>
      <UTextarea v-model="form.description" placeholder="Description" class="mt-2" />
      <UButton class="mt-3" label="Add product" icon="i-lucide-plus" @click="create" />
    </UCard>

    <UCard>
      <template #header><span class="font-medium">CSV import</span></template>
      <p class="text-xs text-muted mb-2">Columns: name,description,price,currency,image_url,product_url,category,stock,sku</p>
      <input type="file" accept=".csv" @change="uploadCsv" />
    </UCard>

    <UCard>
      <template #header><span class="font-medium">Shopify sync (online store)</span></template>
      <div class="grid sm:grid-cols-2 gap-2">
        <UInput v-model="shopDomain" placeholder="mystore.myshopify.com" />
        <UInput v-model="shopToken" type="password" placeholder="Admin API token" />
      </div>
      <UButton class="mt-3" label="Sync from Shopify" icon="i-lucide-refresh-cw" @click="syncShopify" />
    </UCard>

    <UCard>
      <template #header><span class="font-medium">Catalog ({{ products.length }})</span></template>
      <div v-if="loading">Loading…</div>
      <div v-else class="flex flex-col gap-2">
        <div v-for="p in products" :key="p.id" class="flex items-center gap-3 p-2 rounded-lg ring-1 ring-default">
          <img v-if="p.image_url" :src="p.image_url" class="size-10 rounded object-cover" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium truncate">{{ p.name }}</div>
            <div class="text-xs text-muted">{{ p.price }} {{ p.currency }} · {{ p.category }} · stock {{ p.stock }} · {{ p.source }}</div>
          </div>
          <UButton size="xs" color="error" variant="ghost" icon="i-lucide-trash" @click="remove(p.id)" />
        </div>
      </div>
    </UCard>
  </div>
</template>
