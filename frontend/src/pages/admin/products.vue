<script setup lang="ts">
import { onMounted, ref } from "vue";
import ConfirmModal from "../../components/admin/ConfirmModal.vue";
import EmptyState from "../../components/admin/EmptyState.vue";
import ProductFormModal from "../../components/admin/products/ProductFormModal.vue";
import ProductTable from "../../components/admin/products/ProductTable.vue";
import ShopifyCatalogModal from "../../components/admin/products/ShopifyCatalogModal.vue";
import { type Product, useProductCatalog } from "../../composables/useProductCatalog";

const catalog = useProductCatalog();

const formModalOpen = ref(false);
const editing = ref<Product | null>(null);
const deleteTarget = ref<string | null>(null);
const deleteOpen = ref(false);
const catalogOpen = ref(false);

function openCreate() {
	editing.value = null;
	formModalOpen.value = true;
}

function openEdit(p: Product) {
	editing.value = p;
	formModalOpen.value = true;
}

async function onSubmit(form: Parameters<typeof catalog.saveProduct>[1]) {
	await catalog.saveProduct(editing.value, form);
	formModalOpen.value = false;
}

async function onImport(file: File) {
	await catalog.importCsv(file);
	formModalOpen.value = false;
}

function confirmDelete(id: string) {
	deleteTarget.value = id;
	deleteOpen.value = true;
}

async function onDelete() {
	if (!deleteTarget.value) return;
	await catalog.removeProduct(deleteTarget.value);
	deleteOpen.value = false;
	deleteTarget.value = null;
}

onMounted(() => {
	catalog.load();
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
        <UButton color="neutral" variant="outline" icon="i-lucide-shopping-bag" label="Shopify Catalog" @click="catalogOpen = true" />
        <UButton color="primary" variant="solid" icon="i-lucide-plus" label="Add product" @click="openCreate" />
      </div>
      <!-- ponytail: full-height card flex column with overflow table; paginate when catalog > 500 -->
      <UCard class="flex-1 flex flex-col min-h-0" :ui="{ body: 'p-0 flex-1 flex flex-col min-h-0 overflow-hidden' }">
        <template #header>
          <div class="flex items-center justify-end gap-2">
            <UInput v-model="catalog.query.value" icon="i-lucide-search" placeholder="Search name, category…" class="w-72" />
          </div>
        </template>
        <!-- Table / States -->
        <div v-if="catalog.loading.value" class="flex-1 flex items-center justify-center p-12 text-muted text-sm gap-2">
          <UIcon name="i-lucide-loader-2" class="size-4 animate-spin text-primary" />
          <span>Loading catalog…</span>
        </div>

        <EmptyState
          v-else-if="!catalog.products.value.length"
          icon="i-lucide-package"
          title="No products yet"
          hint="Add manual products or import catalog via CSV or Shopify to start powering chat recommendations."
        />

        <div v-else-if="!catalog.filtered.value.length" class="flex-1 flex flex-col items-center justify-center gap-2 p-12 text-center text-muted">
          <UIcon name="i-lucide-search-x" class="size-6" />
          <p class="text-sm">No products matching "{{ catalog.query.value }}"</p>
          <UButton variant="ghost" size="xs" label="Clear search" @click="catalog.query.value = ''" />
        </div>

        <ProductTable
          v-else
          :products="catalog.filtered.value"
          :sort-by="catalog.sortBy.value"
          :sort-dir="catalog.sortDir.value"
          @sort="catalog.toggleSort"
          @edit="openEdit"
          @delete="confirmDelete"
        />
      </UCard>
    </template>
  </UDashboardPanel>

  <ProductFormModal
    v-model:open="formModalOpen"
    :editing="editing"
    :saving="catalog.saving.value"
    :importing="catalog.importing.value"
    @submit="onSubmit"
    @import="onImport"
  />

  <ShopifyCatalogModal v-model:open="catalogOpen" />

  <ConfirmModal
    v-model:open="deleteOpen"
    title="Delete product"
    description="This product will be removed from the catalog and chat recommendations."
    @confirm="onDelete"
  />
</template>
