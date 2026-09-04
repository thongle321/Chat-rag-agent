<script setup lang="ts">
import type { StreamProduct } from "../../api/index";

defineProps<{ product: StreamProduct }>();
</script>

<template>
  <component
    :is="product.product_url ? 'a' : 'div'"
    v-bind="product.product_url ? { href: product.product_url, target: '_blank', rel: 'noopener' } : {}"
    class="flex gap-3 p-3 rounded-xl ring-1 ring-default bg-elevated text-left"
    :class="product.product_url ? 'hover:ring-primary transition' : ''"
  >
    <img v-if="product.image_url" :src="product.image_url" :alt="product.name" class="size-16 rounded-lg object-cover shrink-0" loading="lazy" />
    <div class="min-w-0 flex-1">
      <div class="text-sm font-medium text-default truncate">{{ product.name }}</div>
      <div v-if="product.description" class="text-xs text-muted line-clamp-2 mt-0.5">{{ product.description }}</div>
      <div class="flex items-center gap-2 mt-1.5">
        <span v-if="product.price != null" class="text-sm font-semibold text-primary">{{ product.price }} {{ product.currency || 'USD' }}</span>
        <span v-if="product.stock != null && product.stock <= 5" class="text-[11px] text-warning">Only {{ product.stock }} left</span>
        <span v-if="product.product_url" class="text-[11px] text-muted ml-auto inline-flex items-center gap-1">Buy <UIcon name="i-lucide-external-link" class="size-3" /></span>
      </div>
    </div>
  </component>
</template>
