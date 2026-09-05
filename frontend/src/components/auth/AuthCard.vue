<script setup lang="ts">
withDefaults(
	defineProps<{
		icon?: string;
		title: string;
		subtitle?: string;
	}>(),
	{ icon: "i-lucide-log-in", subtitle: "" },
);
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30 px-4">
    <UCard class="w-full max-w-md shadow-lg">
      <template #header>
        <div class="text-center py-2">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <UIcon class="h-6 w-6 text-primary" :name="icon" />
          </div>
          <h1 class="text-xl font-bold">{{ title }}</h1>
          <p v-if="subtitle" class="text-sm text-muted mt-1">{{ subtitle }}</p>
        </div>
      </template>
      <slot />
    </UCard>
  </div>
</template>
