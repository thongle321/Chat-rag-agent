<script setup lang="ts">
import api, { getErrorMessage } from "../../../api";

const route = useRoute();
const router = useRouter();
const toast = useToast();
const id = computed(() => route.params.id as string);

const loading = ref(true);
const config = ref<any | null>(null);
const health = ref<{ ok: boolean | null; error?: string }>({ ok: null });

const healthChecking = ref(false);
const syncing = ref(false);
const saving = ref(false);
const deleting = ref(false);
const editDialog = ref(false);
const confirmDelete = ref(false);
const syncLogs = ref<any[]>([]);

const editForm = reactive({ name: "", is_active: true, sync_interval: 15 });
const syncIntervalOptions = [
    { label: "Every 1 minute", value: 1 },
    { label: "Every 5 minutes", value: 5 },
    { label: "Every 10 minutes", value: 10 },
    { label: "Every 15 minutes (default)", value: 15 },
    { label: "Every 30 minutes", value: 30 },
    { label: "Every 1 hour", value: 60 },
    { label: "Every 6 hours", value: 360 },
    { label: "Every day", value: 1440 },
];

function formatDateTime(v: string | null) {
    if (!v) return "—";
    const iso = v.includes("T") ? v : `${v.replace(" ", "T")}Z`;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return v;
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${dd}/${mm}/${d.getFullYear()} ${hh}:${mi}`;
}

function formatSyncInterval(v: number) {
    if (!v) return "5 minutes";
    if (v < 60) return `${v} min`;
    if (v < 1440) return `${v / 60} h`;
    return `${v / 1440} day`;
}

async function loadSyncHistory(pageId: string) {
    try {
        const { data } = await api.get(
            `/facebook/channels/${pageId}/sync-history`,
            { params: { limit: 10 } },
        );
        syncLogs.value = data.logs || [];
    } catch {
        syncLogs.value = [];
    }
}

async function refreshSyncState() {
    const param = id.value;
    try {
        const { data: found } = await api.get(`/facebook/channels/${param}`);
        if (found) {
            Object.assign(config.value, {
                last_sync_at: found.last_sync_at,
                last_sync_status: found.last_sync_status,
                total_conversations: found.total_conversations,
                sync_interval: found.sync_interval,
                is_active: found.is_active,
                has_token: found.has_token,
            });
            await loadSyncHistory(found.page_id);
        }
    } catch {}
}

async function load() {
    loading.value = true;
    const param = id.value;
    let found: any = null;
    try {
        const { data } = await api.get(`/facebook/channels/${param}`);
        found = data;
    } catch {
        found = null;
    }
    config.value = found;
    if (found) {
        try {
            const { data: h } = await api.get(
                `/facebook/channels/${param}/health`,
            );
            health.value = { ok: !!h.ok, error: h.error };
        } catch {
            health.value = { ok: null };
        }
        await loadSyncHistory(found.page_id);
    } else health.value = { ok: null };
    loading.value = false;
    if (found) {
        editForm.name = found.page_name;
        editForm.is_active = found.is_active ?? true;
        editForm.sync_interval = found.sync_interval ?? 15;
    }
}

watch(editDialog, (v) => {
    if (v && config.value) {
        editForm.name = config.value.page_name;
        editForm.is_active = config.value.is_active ?? true;
        editForm.sync_interval = config.value.sync_interval ?? 15;
    }
});

async function doTest() {
    if (!config.value) return;
    healthChecking.value = true;
    try {
        const { data } = await api.get(`/facebook/channels/${id.value}/health`);
        toast.add({
            title: data.ok ? "Connection successful" : "Connection failed",
            description: data.ok ? undefined : data.error,
            color: data.ok ? "success" : "error",
        });
        // refresh health badge without full reload
        try {
            health.value = { ok: !!data.ok, error: data.error };
        } catch {}
    } catch (err: any) {
        toast.add({
            title: "Connection failed",
            description: getErrorMessage(err),
            color: "error",
        });
    } finally {
        healthChecking.value = false;
    }
}

async function doSync() {
    if (!config.value) return;
    syncing.value = true;
    try {
        const { data } = await api.post(`/facebook/channels/${id.value}/sync`);
        toast.add({
            title: data.status === "success" ? "Synced" : "Sync error",
            description: data.detail || data.health?.error,
            color: data.status === "success" ? "success" : "error",
        });
        await refreshSyncState();
    } catch (err: any) {
        toast.add({
            title: "Sync failed",
            description: getErrorMessage(err),
            color: "error",
        });
    } finally {
        syncing.value = false;
    }
}

async function saveEdit() {
    if (!config.value) return;
    saving.value = true;
    try {
        await api.put(`/facebook/channels/${config.value.id}`, {
            page_name: editForm.name,
            is_active: editForm.is_active,
            sync_interval: editForm.sync_interval,
        });
        editDialog.value = false;
        toast.add({ title: "Saved", color: "success" });
        await load();
    } catch (err: any) {
        toast.add({
            title: "Save failed",
            description: getErrorMessage(err),
            color: "error",
        });
    } finally {
        saving.value = false;
    }
}

async function doDelete() {
    if (!config.value) return;
    deleting.value = true;
    try {
        await api.delete(`/facebook/channels/${config.value.id}`);
        router.push("/admin/integrations");
    } catch (err: any) {
        toast.add({
            title: "Delete failed",
            description: getErrorMessage(err),
            color: "error",
        });
    } finally {
        deleting.value = false;
    }
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
    <UDashboardPanel id="integration-detail">
        <template #header>
            <UDashboardNavbar
                :title="
                    config ? `Channel ${config.page_name}` : 'Channel detail'
                "
            >
                <template #leading>
                    <UDashboardSidebarCollapse />
                    <UButton
                        icon="i-lucide-arrow-left"
                        variant="ghost"
                        color="neutral"
                        to="/admin/integrations"
                        class="ml-2"
                    />
                </template>
            </UDashboardNavbar>
        </template>

        <template #body>
            <div class="p-0 w-full">
                <div v-if="loading" class="flex justify-center py-16">
                    <ULoader />
                </div>
                <div
                    v-else-if="!config"
                    class="flex flex-col items-center py-12"
                >
                    <UIcon
                        name="i-lucide-plug"
                        class="size-12 text-muted mb-3"
                    />
                    <p class="text-muted mb-4">Channel not found</p>
                    <UButton to="/admin/integrations"
                        >Back to integrations</UButton
                    >
                </div>

                <template v-else>
                    <div
                        class="flex items-center justify-end mb-4 flex-wrap gap-2 px-1"
                    >
                        <UButton
                            variant="outline"
                            size="sm"
                            icon="i-lucide-pencil"
                            @click="editDialog = true"
                            >Edit</UButton
                        >
                        <UButton
                            color="primary"
                            size="sm"
                            icon="i-lucide-refresh-cw"
                            :loading="syncing"
                            @click="doSync"
                            >Sync</UButton
                        >
                        <UButton
                            variant="outline"
                            size="sm"
                            icon="i-lucide-activity"
                            :loading="healthChecking"
                            @click="doTest"
                            >Test connection</UButton
                        >
                        <UButton
                            color="error"
                            variant="outline"
                            size="sm"
                            icon="i-lucide-trash"
                            @click="confirmDelete = true"
                            >Delete</UButton
                        >
                    </div>

                    <UCard class="mb-4">
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Status
                                </div>
                                <UBadge
                                    :color="
                                        config.is_active ? 'success' : 'neutral'
                                    "
                                    variant="soft"
                                    size="md"
                                    >{{
                                        config.is_active ? "Active" : "Inactive"
                                    }}</UBadge
                                >
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Sync status
                                </div>
                                <UBadge
                                    :color="
                                        config.last_sync_status === 'success'
                                            ? 'success'
                                            : config.last_sync_status ===
                                                'error'
                                              ? 'error'
                                              : 'neutral'
                                    "
                                    variant="soft"
                                    size="md"
                                    >{{
                                        config.last_sync_status === "success"
                                            ? "Synced"
                                            : config.last_sync_status ===
                                                "error"
                                              ? "Error"
                                              : "Not synced"
                                    }}</UBadge
                                >
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Sync interval
                                </div>
                                <div class="text-sm">
                                    {{
                                        formatSyncInterval(config.sync_interval)
                                    }}
                                </div>
                            </div>

                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Last sync
                                </div>
                                <div class="text-sm">
                                    {{
                                        config.last_sync_at
                                            ? formatDateTime(
                                                  config.last_sync_at,
                                              )
                                            : "Not synced"
                                    }}
                                </div>
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Total conversations
                                </div>
                                <div class="text-sm font-bold text-primary">
                                    {{ config.total_conversations ?? 0 }}
                                </div>
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Created at
                                </div>
                                <div class="text-sm">
                                    {{ formatDateTime(config.created_at) }}
                                </div>
                            </div>
                        </div>
                        <UAlert
                            v-if="health.error"
                            color="error"
                            variant="soft"
                            :description="health.error"
                            class="mt-4"
                        />
                    </UCard>

                    <UCard>
                        <template #header>
                            <div class="flex items-center gap-2">
                                <UIcon name="i-lucide-history" class="size-4" />
                                <span class="font-semibold text-sm"
                                    >Sync history</span
                                >
                            </div>
                        </template>
                        <div class="overflow-x-auto">
                            <table class="w-full text-sm">
                                <thead>
                                    <tr class="border-b text-xs text-muted">
                                        <th
                                            class="text-left py-2 px-2 font-medium"
                                        >
                                            Time
                                        </th>
                                        <th
                                            class="text-left py-2 px-2 font-medium"
                                        >
                                            Status
                                        </th>
                                        <th
                                            class="text-left py-2 px-2 font-medium"
                                        >
                                            Detail
                                        </th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y">
                                    <tr v-for="log in syncLogs" :key="log.id">
                                        <td
                                            class="py-2 px-2 text-xs text-muted whitespace-nowrap"
                                        >
                                            {{
                                                new Date(
                                                    log.created_at.replace(
                                                        " ",
                                                        "T",
                                                    ) + "Z",
                                                ).toLocaleString()
                                            }}
                                        </td>
                                        <td class="py-2 px-2">
                                            <UBadge
                                                :color="
                                                    log.status === 'success'
                                                        ? 'success'
                                                        : log.status === 'error'
                                                          ? 'error'
                                                          : 'neutral'
                                                "
                                                variant="soft"
                                                size="md"
                                                >{{
                                                    log.status === "success"
                                                        ? "Success"
                                                        : log.status === "error"
                                                          ? "Error"
                                                          : log.status
                                                }}</UBadge
                                            >
                                        </td>
                                        <td
                                            class="py-2 px-2 truncate max-w-[28rem]"
                                        >
                                            {{ log.detail || "—" }}
                                        </td>
                                    </tr>
                                    <tr v-if="!syncLogs.length">
                                        <td
                                            colspan="3"
                                            class="py-8 text-center text-muted text-sm"
                                        ></td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <div
                            v-if="syncLogs[0]?.error_message"
                            class="text-xs text-error mt-2 px-2"
                        >
                            {{ syncLogs[0].error_message.slice(0, 180) }}
                        </div>
                    </UCard>

                    <!-- Edit Dialog — English, no Page name field shown (kept internally) -->
                    <UModal v-model:open="editDialog" title="Edit channel">
                        <template #body>
                            <div class="space-y-3">
                                <USwitch
                                    v-model="editForm.is_active"
                                    label="Active"
                                />
                                <UFormField label="Sync interval"
                                    ><USelect
                                        v-model="editForm.sync_interval"
                                        :items="syncIntervalOptions"
                                /></UFormField>
                            </div>
                        </template>
                        <template #footer>
                            <div class="flex justify-end gap-2 w-full">
                                <UButton
                                    variant="ghost"
                                    @click="editDialog = false"
                                    >Cancel</UButton
                                >
                                <UButton
                                    color="primary"
                                    :loading="saving"
                                    @click="saveEdit"
                                    >Save</UButton
                                >
                            </div>
                        </template>
                    </UModal>

                    <UModal v-model:open="confirmDelete" title="Delete channel">
                        <template #body>
                            <p class="text-sm">
                                Delete channel <b>{{ config.page_id }}</b> and
                                all related chats? This cannot be undone.
                            </p>
                        </template>
                        <template #footer>
                            <div class="flex justify-end gap-2 w-full">
                                <UButton
                                    variant="ghost"
                                    @click="confirmDelete = false"
                                    >Cancel</UButton
                                >
                                <UButton
                                    color="error"
                                    :loading="deleting"
                                    @click="doDelete"
                                    >Delete</UButton
                                >
                            </div>
                        </template>
                    </UModal>
                </template>
            </div>
        </template>
    </UDashboardPanel>
</template>
