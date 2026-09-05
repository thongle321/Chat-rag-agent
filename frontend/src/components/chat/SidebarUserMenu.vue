<script setup lang="ts">
import { useAuthStore } from "../../stores/auth";

defineProps<{ collapsed?: boolean }>();
const emit = defineEmits<{ logout: [] }>();

const authStore = useAuthStore();
const colorMode = useColorMode();

const userMenuItems = computed(() => [
	[
		{
			label: authStore.user?.email ?? "Guest",
			type: "label" as const,
			icon: "i-lucide-user",
		},
	],
	[
		{
			label: "Appearance",
			icon: "i-lucide-sun-moon",
			children: [
				{
					label: "Light",
					icon: "i-lucide-sun",
					type: "checkbox" as const,
					checked: colorMode.value === "light",
					onSelect(e: Event) {
						e.preventDefault();
						colorMode.value = "light";
					},
				},
				{
					label: "Dark",
					icon: "i-lucide-moon",
					type: "checkbox" as const,
					checked: colorMode.value === "dark",
					onUpdateChecked(checked: boolean) {
						if (checked) colorMode.value = "dark";
					},
					onSelect(e: Event) {
						e.preventDefault();
					},
				},
			],
		},
	],
	[
		{
			label: authStore.user ? "Logout" : "Login",
			icon: authStore.user ? "i-lucide-log-out" : "i-lucide-log-in",
			onSelect: () => emit("logout"),
		},
	],
]);
</script>

<template>
  <UDropdownMenu
    :items="userMenuItems"
    :content="{ align: 'center', collisionPadding: 12 }"
    :ui="{ content: collapsed ? 'w-48' : 'w-(--reka-dropdown-menu-trigger-width)' }"
  >
    <UButton
      v-bind="{ label: collapsed ? undefined : (authStore.user?.email ?? 'Guest'), trailingIcon: collapsed ? undefined : 'i-lucide-chevrons-up-down' }"
      :avatar="{ icon: 'i-lucide-user', alt: authStore.user?.email ?? 'Guest' }"
      color="neutral"
      variant="ghost"
      block
      :square="collapsed"
      class="data-[state=open]:bg-elevated"
      :ui="{ trailingIcon: 'text-dimmed' }"
    />
  </UDropdownMenu>
</template>
