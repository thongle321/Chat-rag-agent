<script setup lang="ts">
import type { TableColumn } from "@nuxt/ui";
import { computed, onMounted, ref, watch } from "vue";
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

interface UsageSummary {
	turns: number;
	input_tokens: number;
	output_tokens: number;
	cost_usd: number;
	cost_vnd: number;
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
const summary = ref<UsageSummary>({ turns: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0, cost_vnd: 0 });
const loading = ref(true);
const error = ref("");

const provider = ref("all");
const dateFrom = ref("");
const dateTo = ref("");
const page = ref(1);
const perPage = 20;

const providerItems = ["all", "ollama", "openai"];
const isFiltered = computed(() => provider.value !== "all" || !!dateFrom.value || !!dateTo.value);

function fmtUSD(v: number | null): string {
	if (v == null) return "—";
	return `$${v.toFixed(4)}`;
}

function fmtVND(v: number | null): string {
	if (v == null) return "—";
	return `₫${Math.round(v).toLocaleString("en-US")}`;
}

function fmtInt(v: number): string {
	return v.toLocaleString("en-US");
}

function filterParams() {
	return {
		...(provider.value !== "all" ? { provider: provider.value } : {}),
		...(dateFrom.value ? { date_from: dateFrom.value } : {}),
		...(dateTo.value ? { date_to: dateTo.value } : {}),
	};
}

function clearFilters() {
	provider.value = "all";
	dateFrom.value = "";
	dateTo.value = "";
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const [tableRes, summaryRes] = await Promise.all([
			api.get("/logs/usage", { params: { ...filterParams(), page: page.value, per_page: perPage } }),
			api.get("/logs/usage/summary", { params: filterParams() }),
		]);
		rows.value = tableRes.data.items ?? [];
		total.value = tableRes.data.total ?? 0;
		summary.value = summaryRes.data;
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
          <UFieldGroup>
            <UInput v-model="dateFrom" type="date" aria-label="From date" />
            <UInput v-model="dateTo" type="date" aria-label="To date" />
          </UFieldGroup>
          <UButton v-if="isFiltered" color="neutral" variant="ghost" icon="i-lucide-x" label="Clear" @click="clearFilters" />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <div class="flex flex-col gap-4">
        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />

        <UPageGrid class="sm:grid-cols-2 lg:grid-cols-4">
          <UPageCard icon="i-lucide-messages-square" title="Turns" :description="fmtInt(summary.turns)" />
          <UPageCard icon="i-lucide-log-in" title="Input tokens" :description="fmtInt(summary.input_tokens)" />
          <UPageCard icon="i-lucide-log-out" title="Output tokens" :description="fmtInt(summary.output_tokens)" />
          <UPageCard icon="i-lucide-coins" title="Total cost" :description="`${fmtUSD(summary.cost_usd)} · ${fmtVND(summary.cost_vnd)}`" />
        </UPageGrid>

        <UCard :ui="{ body: 'p-0' }">
          <UTable :data="rows" :columns="columns" :loading="loading">
            <template #empty>
              <UEmpty
                icon="i-lucide-receipt"
                title="No usage recorded"
                :description="isFiltered ? 'No turns match these filters.' : 'Rows appear here as chats run.'"
              >
                <template v-if="isFiltered" #actions>
                  <UButton color="neutral" variant="outline" label="Clear filters" @click="clearFilters" />
                </template>
              </UEmpty>
            </template>
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
              {{ fmtInt(row.original.input_tokens) }}
            </template>
            <template #output_tokens-cell="{ row }">
              {{ fmtInt(row.original.output_tokens) }}
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
      </div>
    </template>
  </UDashboardPanel>
</template>
