<script setup lang="ts">
import type { TableColumn } from "@nuxt/ui";
import { onMounted, ref, watch } from "vue";
import api, { getErrorMessage } from "../../api";
import { formatDateTime } from "../../utils/format";

interface UsageRow {
	id: string;
	provider: string | null;
	model: string | null;
	input_tokens: number;
	output_tokens: number;
	cost_usd: number | null;
	cost_vnd: number | null;
	created_at: string | null;
}

const columns: TableColumn<UsageRow>[] = [
	{ accessorKey: "created_at", header: "Sent" },
	{ accessorKey: "provider", header: "Provider" },
	{ accessorKey: "model", header: "Model" },
	{ accessorKey: "input_tokens", header: "Input tokens" },
	{ accessorKey: "output_tokens", header: "Output tokens" },
	{ accessorKey: "cost_usd", header: "Cost (USD)" },
	{ accessorKey: "cost_vnd", header: "Cost (VND)" },
];

const rows = ref<UsageRow[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");

const provider = ref("all");
const dateFrom = ref("");
const dateTo = ref("");
const page = ref(1);
const perPage = 20;

const providerItems = ["all", "ollama", "openai"];

function fmtUSD(v: number | null): string {
	if (v == null) return "—";
	return `$${v.toFixed(4)}`;
}

function fmtVND(v: number | null): string {
	if (v == null) return "—";
	return `₫${Math.round(v).toLocaleString("en-US")}`;
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const { data } = await api.get("/logs/usage", {
			params: {
				...(provider.value !== "all" ? { provider: provider.value } : {}),
				...(dateFrom.value ? { date_from: dateFrom.value } : {}),
				...(dateTo.value ? { date_to: dateTo.value } : {}),
				page: page.value,
				per_page: perPage,
			},
		});
		rows.value = data.items ?? [];
		total.value = data.total ?? 0;
	} catch (err: unknown) {
		error.value = getErrorMessage(err);
		rows.value = [];
		total.value = 0;
	} finally {
		loading.value = false;
	}
}

watch([provider, dateFrom, dateTo], () => {
	page.value = 1;
	load();
});

onMounted(load);
</script>

<template>
  <UDashboardPanel id="usage">
    <template #header>
      <UDashboardNavbar title="AI Usage">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar>
        <template #left>
          <USelect v-model="provider" :items="providerItems" placeholder="Provider" class="w-36" />
          <UInput v-model="dateFrom" type="date" aria-label="From date" class="w-40" />
          <UInput v-model="dateTo" type="date" aria-label="To date" class="w-40" />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" class="mb-4" />

      <UCard :ui="{ body: 'p-0' }">
        <UTable :data="rows" :columns="columns" :loading="loading" :empty="'No usage recorded yet — rows appear as chats run.'">
          <template #created_at-cell="{ row }">
            <span class="whitespace-nowrap">{{ formatDateTime(row.original.created_at) }}</span>
          </template>
          <template #provider-cell="{ row }">
            <UBadge v-if="row.original.provider" color="neutral" variant="subtle" size="sm">{{ row.original.provider }}</UBadge>
            <span v-else class="text-muted text-xs">—</span>
          </template>
          <template #model-cell="{ row }">
            <span class="font-mono text-xs">{{ row.original.model || "—" }}</span>
          </template>
          <template #input_tokens-cell="{ row }">
            {{ row.original.input_tokens.toLocaleString("en-US") }}
          </template>
          <template #output_tokens-cell="{ row }">
            {{ row.original.output_tokens.toLocaleString("en-US") }}
          </template>
          <template #cost_usd-cell="{ row }">
            <span class="font-medium">{{ fmtUSD(row.original.cost_usd) }}</span>
          </template>
          <template #cost_vnd-cell="{ row }">
            <span class="font-medium">{{ fmtVND(row.original.cost_vnd) }}</span>
          </template>
        </UTable>

        <div v-if="total > perPage" class="flex justify-center p-3 border-t">
          <UPagination v-model="page" :total="total" :items-per-page="perPage" @update:page="load" />
        </div>
      </UCard>
    </template>
  </UDashboardPanel>
</template>
