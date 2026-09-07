<script setup lang="ts">
import type { Product } from "../../../composables/useProductCatalog";
import { formatUSD } from "../../../utils/format";

defineProps<{
	products: Product[];
	sortBy: keyof Product;
	sortDir: "asc" | "desc";
}>();
const emit = defineEmits<{
	sort: [field: keyof Product];
	edit: [product: Product];
	delete: [id: string];
}>();

function sortIcon(field: keyof Product, sortBy: keyof Product, sortDir: "asc" | "desc") {
	if (sortBy !== field) return "i-lucide-arrow-up-down";
	return sortDir === "asc" ? "i-lucide-arrow-up" : "i-lucide-arrow-down";
}
</script>

<template>
  <div class="flex-1 min-h-0 overflow-auto">
    <table class="w-full text-sm">
      <thead class="text-left text-xs uppercase tracking-wider text-muted bg-elevated/50 sticky top-0 z-10 border-b border-default backdrop-blur-xs">
        <tr>
          <th class="py-3 px-4 w-16">Image</th>
          <th class="py-3 px-4 cursor-pointer select-none" tabindex="0" role="button" :aria-sort="sortBy === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'" @click="emit('sort', 'name')" @keydown.enter="emit('sort', 'name')" @keydown.space.prevent="emit('sort', 'name')">
            <span class="inline-flex items-center gap-1.5 font-medium">
              Name
              <UIcon :name="sortIcon('name', sortBy, sortDir)" class="size-3.5" :class="sortBy === 'name' ? 'text-primary' : 'opacity-40'" />
            </span>
          </th>
          <th class="py-3 px-4">Category</th>
          <th class="py-3 px-4 cursor-pointer select-none" tabindex="0" role="button" :aria-sort="sortBy === 'price' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'" @click="emit('sort', 'price')" @keydown.enter="emit('sort', 'price')" @keydown.space.prevent="emit('sort', 'price')">
            <span class="inline-flex items-center gap-1.5 font-medium">
              Price
              <UIcon :name="sortIcon('price', sortBy, sortDir)" class="size-3.5" :class="sortBy === 'price' ? 'text-primary' : 'opacity-40'" />
            </span>
          </th>
          <th class="py-3 px-4 cursor-pointer select-none" tabindex="0" role="button" :aria-sort="sortBy === 'stock' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'" @click="emit('sort', 'stock')" @keydown.enter="emit('sort', 'stock')" @keydown.space.prevent="emit('sort', 'stock')">
            <span class="inline-flex items-center gap-1.5 font-medium">
              Stock
              <UIcon :name="sortIcon('stock', sortBy, sortDir)" class="size-3.5" :class="sortBy === 'stock' ? 'text-primary' : 'opacity-40'" />
            </span>
          </th>
          <th class="py-3 px-4 text-right w-24">Actions</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-default">
        <tr v-for="p in products" :key="p.id" class="hover:bg-elevated/40 transition-colors">
          <td class="py-2.5 px-4 align-middle">
            <img v-if="p.image_url" :src="p.image_url" :alt="p.name" class="size-10 rounded-md object-cover ring-1 ring-default bg-muted/10" loading="lazy" />
            <div v-else class="size-10 rounded-md bg-muted/20 flex items-center justify-center text-muted">
              <UIcon name="i-lucide-image" class="size-4" />
            </div>
          </td>
          <td class="py-2.5 px-4 align-middle max-w-xs">
            <div class="font-medium text-default truncate">{{ p.name }}</div>
            <div class="text-xs text-muted truncate">{{ p.description || "No description" }}</div>
          </td>
          <td class="py-2.5 px-4 align-middle">
            <UBadge v-if="p.category" variant="subtle" color="neutral" size="sm">{{ p.category }}</UBadge>
            <span v-else class="text-muted text-xs">—</span>
          </td>
          <td class="py-2.5 px-4 align-middle text-default font-medium">{{ formatUSD(p.price, p.currency) }}</td>
          <td class="py-2.5 px-4 align-middle">
            <UBadge v-if="p.stock != null" :color="p.stock > 10 ? 'success' : p.stock > 0 ? 'warning' : 'error'" variant="subtle" size="sm">
              {{ p.stock }} in stock
            </UBadge>
            <span v-else class="text-muted text-xs">—</span>
          </td>
          <td class="py-2.5 px-4 align-middle text-right">
            <div class="inline-flex items-center gap-1 justify-end">
              <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-pen" title="Edit" aria-label="Edit product" @click="emit('edit', p)" />
              <UButton size="xs" color="error" variant="ghost" icon="i-lucide-trash" title="Delete" aria-label="Delete product" @click="emit('delete', p.id)" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
