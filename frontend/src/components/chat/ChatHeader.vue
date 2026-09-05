<script setup lang="ts">
import { useAuthStore } from "../../stores/auth";

defineProps<{ title: string }>();
const emit = defineEmits<{ rename: []; delete: [] }>();

const authStore = useAuthStore();

const menuItems = computed(() => [
	[{ label: "Rename", icon: "i-lucide-pencil", onSelect: () => emit("rename") }],
	[{ label: "Delete", icon: "i-lucide-trash", color: "error" as const, onSelect: () => emit("delete") }],
]);
</script>

<template>
  <header class="flex items-center justify-between px-3 md:px-7 py-2.5 bg-default/75 min-h-[44px]">
    <div class="flex items-center gap-2 min-w-0">
      <slot name="leading" />
      <div v-if="title" class="min-w-0">
        <UDropdownMenu :items="menuItems" :content="{ align: 'start' }" :ui="{ content: 'min-w-44' }">
          <UButton
            color="neutral"
            variant="ghost"
            :label="title"
            trailing-icon="i-lucide-chevron-down"
            class="group min-w-0 max-w-[280px] data-[state=open]:bg-elevated"
            :ui="{ trailingIcon: 'text-dimmed group-data-[state=open]:rotate-180 transition-transform duration-200' }"
          />
        </UDropdownMenu>
      </div>
    </div>
    <div v-if="!authStore.isAuthenticated" class="flex items-center gap-2">
      <UButton to="/login" color="neutral" variant="ghost" size="sm" label="Log in" />
      <UButton to="/login?mode=signup" color="primary" variant="solid" size="sm" label="Sign up" />
    </div>
  </header>
</template>
