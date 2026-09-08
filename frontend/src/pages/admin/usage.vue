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

// Reka calendar value (serializes to YYYY-MM-DD) — structural typing only,
// no @internationalized/date import needed.
interface CalendarDay {
	toString(): string;
	day?: number;
	month?: number;
	year?: number;
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
const dateFrom = ref<CalendarDay | undefined>();
const dateTo = ref<CalendarDay | undefined>();
const page = ref(1);
const perPage = 20;

const providerItems = ["all", "ollama", "openai"];
const isFiltered = computed(() => provider.value !== "all" || dateFrom.value != null || dateTo.value != null);

function fmtDay(v: CalendarDay | undefined, placeholder: string): string {
	if (!v) return placeholder;
	if (v.day != null && v.month != null && v.year != null) {
		const dd = String(v.day).padStart(2, "0");
		const mm = String(v.month).padStart(2, "0");
		return `${dd}/${mm}/${v.year}`;
	}
	const iso = v.toString().slice(0, 10).split("-");
	return iso.length === 3 ? `${iso[2]}/${iso[1]}/${iso[0]}` : placeholder;
}

function fmtUSD(v: number | null): string {
	if (v == null) return "—";
	return `$${v.toFixed(4)}`;
}

function fmtVND(v: number | null): string {
	if (v == null) return "—";
	return `₫${Math.round(v).toLocaleString("en-US")}`;
}

function clearFilters() {
	provider.value = "all";
	dateFrom.value = undefined;
	dateTo.value = undefined;
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const { data } = await api.get("/logs/usage", {
			params: {
				...(provider.value !== "all" ? { provider: provider.value } : {}),
				...(dateFrom.value ? { date_from: dateFrom.value.toString().slice(0, 10) } : {}),
				...(dateTo.value ? { date_to: dateTo.value.toString().slice(0, 10) } : {}),
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
          <UPopover>
            <UInput :model-value="fmtDay(dateFrom, '')" placeholder="From" icon="i-lucide-calendar" readonly class="w-40" />
            <template #content>
              <UCalendar v-model="dateFrom" />
            </template>
          </UPopover>
          <UPopover>
            <UInput :model-value="fmtDay(dateTo, '')" placeholder="To" icon="i-lucide-calendar" readonly class="w-40" />
            <template #content>
              <UCalendar v-model="dateTo" />
            </template>
          </UPopover>
          <UButton v-if="isFiltered" color="neutral" variant="ghost" icon="i-lucide-x" label="Clear" @click="clearFilters" />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <div class="flex flex-col gap-4">
        <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="error" />

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
      </div>
    </template>
  </UDashboardPanel>
</template>
