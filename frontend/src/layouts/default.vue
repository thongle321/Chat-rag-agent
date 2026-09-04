<script setup lang="ts">
import type { NavigationMenuItem } from "@nuxt/ui";
import { ref } from "vue";

const open = ref(false);

const links = [
	[
		{
			label: "Dashboard",
			icon: "i-lucide-layout-dashboard",
			to: "/admin",
			exact: true,
			onSelect: () => {
				open.value = false;
			},
		},
		{
			label: "Documents",
			icon: "i-lucide-file-text",
			to: "/admin/documents",
			onSelect: () => {
				open.value = false;
			},
		},
		{
			label: "Products",
			icon: "i-lucide-shopping-bag",
			to: "/admin/products",
			onSelect: () => {
				open.value = false;
			},
		},
		{
			label: "Integrations",
			icon: "i-lucide-plug",
			to: "/admin/integrations",
			onSelect: () => {
				open.value = false;
			},
		},
		{
			label: "Messages",
			icon: "i-lucide-messages-square",
			to: "/admin/messages",
			onSelect: () => {
				open.value = false;
			},
		},
		{
			label: "Settings",
			to: "/admin/settings",
			icon: "i-lucide-settings",
			onSelect: () => {
				open.value = false;
			},
		},
	],
] satisfies NavigationMenuItem[][];
</script>

<template>
  <UDashboardGroup unit="rem" storage="local">
    <UDashboardSidebar
      id="default"
      v-model:open="open"
      collapsible
      resizable
      class="bg-elevated"
      :ui="{ footer: 'lg:border-t lg:border-default' }"
    >
      <template #header="{ collapsed }">
        <AppLogo :collapsed="collapsed" />
      </template>

      <template #default="{ collapsed }">
        <UNavigationMenu
          :collapsed="collapsed"
          :items="links[0]"
          orientation="vertical"
          tooltip
          popover
        />
      </template>

      <template #footer="{ collapsed }">
        <UserMenu :collapsed="collapsed" />
      </template>
    </UDashboardSidebar>

    <RouterView />
  </UDashboardGroup>
</template>
