<script setup lang="ts">
export interface Product {
  id: string;
  name: string;
  description?: string | null;
  price?: number | null;
  currency?: string;
  image_url?: string | null;
  product_url?: string | null;
  category?: string | null;
  stock?: number;
  score?: number;
}

defineProps<{ product: Product; index: number }>();
</script>

<template>
  <a
    v-if="product.product_url"
    :href="product.product_url"
    target="_blank"
    rel="noopener"
    class="flex gap-3 p-3 rounded-xl ring-1 ring-default bg-elevated hover:ring-primary transition text-left"
  >
    <img v-if="product.image_url" :src="product.image_url" :alt="product.name" class="size-16 rounded-lg object-cover shrink-0" loading="lazy" />
    <div class="min-w-0 flex-1">
      <div class="text-sm font-medium text-default truncate">[P{{ index + 1 }}] {{ product.name }}</div>
      <div v-if="product.description" class="text-xs text-muted line-clamp-2 mt-0.5">{{ product.description }}</div>
      <div class="flex items-center gap-2 mt-1.5">
        <span v-if="product.price != null" class="text-sm font-semibold text-primary">{{ product.price }} {{ product.currency || 'USD' }}</span>
        <span v-if="product.stock != null && product.stock <= 5" class="text-[11px] text-warning">Only {{ product.stock }} left</span>
        <span class="text-[11px] text-muted ml-auto inline-flex items-center gap-1">Buy <UIcon name="i-lucide-external-link" class="size-3" /></span>
      </div>
    </div>
  </a>
  <div v-else class="flex gap-3 p-3 rounded-xl ring-1 ring-default bg-elevated">
    <img v-if="product.image_url" :src="product.image_url" :alt="product.name" class="size-16 rounded-lg object-cover shrink-0" loading="lazy" />
    <div class="min-w-0 flex-1">
      <div class="text-sm font-medium text-default truncate">[P{{ index + 1 }}] {{ product.name }}</div>
      <div v-if="product.description" class="text-xs text-muted line-clamp-2 mt-0.5">{{ product.description }}</div>
      <div class="flex items-center gap-2 mt-1.5">
        <span v-if="product.price != null" class="text-sm font-semibold text-primary">{{ product.price }} {{ product.currency || 'USD' }}</span>
      </div>
    </div>
  </div>
</template>
