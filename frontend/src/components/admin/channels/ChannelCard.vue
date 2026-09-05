<script setup lang="ts">
withDefaults(
	defineProps<{
		icon?: string;
		title: string;
		subtitle?: string;
		active?: boolean;
		to?: string;
	}>(),
	{ active: false, icon: "i-lucide-plug", subtitle: "", to: "" },
);
</script>

<template>
  <UCard class="flex flex-col cursor-pointer hover:shadow-md transition" @click="$router.push(to)">
    <div class="flex items-center gap-3 mb-4">
      <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10 shrink-0">
        <UIcon class="text-primary size-5" :name="icon" />
      </div>
      <div class="flex-1 min-w-0">
        <h3 class="font-semibold truncate">{{ title }}</h3>
        <p v-if="subtitle" class="text-xs text-muted truncate">{{ subtitle }}</p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs mb-4">
      <div class="p-2 rounded-lg col-span-2">
        <div class="text-muted">Status</div>
        <div class="font-medium">
          <UBadge size="md" variant="soft" :color="active ? 'success' : 'neutral'">{{ active ? "Active" : "Inactive" }}</UBadge>
        </div>
      </div>
      <slot name="extra" />
    </div>

    <div class="flex flex-wrap gap-2 mt-auto">
      <slot name="actions" />
    </div>
  </UCard>
</template>
