<script setup lang="ts">
import api from "../../api";

const dashStats = ref({
	total_documents: 0,
	total_chunks: 0,
	total_sessions: 0,
	total_queries: 0,
});

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
		label: "Sessions",
		value: dashStats.value.total_sessions,
		icon: "i-lucide-message-square",
		color: "success" as const,
	},
	{
		label: "Queries",
		value: dashStats.value.total_queries,
		icon: "i-lucide-search",
		color: "warning" as const,
	},
]);

const health = ref({ api: false, vector_store: false });

onMounted(async () => {
	try {
		const { data } = await api.get("/stats");
		dashStats.value = data;
	} catch {
		// keep defaults
	}
	try {
		const { data } = await api.get("/health/detailed");
		health.value = {
			api: data.status === "ok",
			vector_store: data.components?.vector_store === "ok",
		};
	} catch {
		health.value = { api: false, vector_store: false };
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
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <UCard v-for="stat in stats" :key="stat.label">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-sm text-muted">{{ stat.label }}</p>
                <p class="text-2xl font-bold mt-1 font-[var(--font-display)]">{{ stat.value }}</p>
              </div>
              <UIcon :name="stat.icon" class="text-3xl text-muted opacity-50" />
            </div>
          </UCard>
        </div>

        <div class="grid gap-6">
          <UCard>
            <template #header>
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-check-circle" class="text-success" />
                <span class="font-semibold">System Status</span>
              </div>
            </template>

            <div class="flex flex-col gap-3">
              <div class="flex items-center justify-between">
                <span class="text-sm">API Server</span>
                <UBadge :color="health.api ? 'success' : 'error'" variant="soft" size="sm">
                  {{ health.api ? 'Normal' : 'Error' }}
                </UBadge>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm">Vector Store</span>
                <UBadge :color="health.vector_store ? 'success' : 'error'" variant="soft" size="sm">
                  {{ health.vector_store ? 'Normal' : 'Error' }}
                </UBadge>
              </div>
            </div>
          </UCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
