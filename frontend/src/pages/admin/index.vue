<script setup lang="ts">
import api from "../../api";

const dashStats = ref({
	total_documents: 0,
	total_chunks: 0,
	web_conversations: 0,
	facebook_conversations: 0,
	total_conversations: 0,
	total_messages: 0,
	active_channels: 0,
});
const loadError = ref("");

const stats = computed(() => [
	{
		label: "Documents",
		value: dashStats.value.total_documents,
		icon: "i-lucide-file-text",
		color: "primary" as const,
	},
	{
		label: "Chunks",
		value: dashStats.value.total_chunks,
		icon: "i-lucide-layers",
		color: "info" as const,
	},
	{
		label: "Web Conversations",
		value: dashStats.value.web_conversations,
		icon: "i-lucide-globe",
		color: "success" as const,
	},
	{
		label: "Facebook Conversations",
		value: dashStats.value.facebook_conversations,
		icon: "i-lucide-facebook",
		color: "info" as const,
	},
	{
		label: "Total Conversations",
		value: dashStats.value.total_conversations,
		icon: "i-lucide-messages-square",
		color: "primary" as const,
	},
	{
		label: "Total Messages",
		value: dashStats.value.total_messages,
		icon: "i-lucide-mail",
		color: "warning" as const,
	},
	{
		label: "Active Channels",
		value: dashStats.value.active_channels,
		icon: "i-lucide-plug",
		color: "success" as const,
	},
]);

onMounted(async () => {
	try {
		const { data } = await api.get("/stats");
		Object.assign(dashStats.value, data);
	} catch {
		loadError.value = "Couldn't load dashboard stats. Check the API server and retry.";
	}
});
</script>

<template>
    <UDashboardPanel id="home">
        <template #header>
            <UDashboardNavbar title="Dashboard">
                <template #leading>
                    <UDashboardSidebarCollapse />
                </template>
            </UDashboardNavbar>
        </template>

        <template #body>
            <div class="flex flex-col gap-6">
                <UAlert v-if="loadError" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="loadError" />
                <div
                    class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
                >
                    <UCard v-for="stat in stats" :key="stat.label">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-sm text-muted">
                                    {{ stat.label }}
                                </p>
                                <p
                                    class="text-2xl font-bold mt-1 font-[var(--font-display)]"
                                >
                                    {{ stat.value }}
                                </p>
                            </div>
                            <UIcon
                                :name="stat.icon"
                                class="text-3xl text-muted opacity-50"
                            />
                        </div>
                    </UCard>
                </div>
            </div>
        </template>
    </UDashboardPanel>
</template>
