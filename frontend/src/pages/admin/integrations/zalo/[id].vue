<script setup lang="ts">
import api, { getErrorMessage } from "../../../../api";

const route = useRoute();
const router = useRouter();
const toast = useToast();
const id = computed(() => route.params.id as string);

const loading = ref(true);
const config = ref<any | null>(null);
const health = ref<{ ok: boolean | null; error?: string }>({ ok: null });

const healthChecking = ref(false);
const saving = ref(false);
const deleting = ref(false);
const editDialog = ref(false);
const confirmDelete = ref(false);

const editForm = reactive({ bot_username: "", is_active: true });

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

async function load() {
    loading.value = true;
    const param = id.value;
    let found: any = null;
    try {
        const { data } = await api.get(`/zalo/channels/${param}`);
        found = data;
    } catch {
        found = null;
    }
    config.value = found;
    if (found) {
        try {
            const { data: h } = await api.get(`/zalo/channels/${param}/health`);
            health.value = { ok: !!h.ok, error: h.error };
        } catch {
            health.value = { ok: null };
        }
    } else health.value = { ok: null };
    loading.value = false;
    if (found) {
        editForm.bot_username = found.bot_username;
        editForm.is_active = found.is_active ?? true;
    }
}

watch(editDialog, (v) => {
    if (v && config.value) {
        editForm.bot_username = config.value.bot_username;
        editForm.is_active = config.value.is_active ?? true;
    }
});

async function doTest() {
    if (!config.value) return;
    healthChecking.value = true;
    try {
        const { data } = await api.get(`/zalo/channels/${id.value}/health`);
        toast.add({
            title: data.ok ? "Connection successful" : "Connection failed",
            description: data.ok ? undefined : data.error,
            color: data.ok ? "success" : "error",
        });
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

async function saveEdit() {
    if (!config.value) return;
    saving.value = true;
    try {
        await api.put(`/zalo/channels/${config.value.id}`, {
            bot_username: editForm.bot_username,
            is_active: editForm.is_active,
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
        await api.delete(`/zalo/channels/${config.value.id}`);
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
    <UDashboardPanel id="zalo-integration-detail">
        <template #header>
            <UDashboardNavbar
                :title="
                    config
                        ? `Zalo Bot ${config.bot_username || config.bot_id}`
                        : 'Zalo detail'
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
                        name="i-lucide-bot"
                        class="size-12 text-muted mb-3"
                    />
                    <p class="text-muted mb-4">Bot not found</p>
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
                                    Bot ID
                                </div>
                                <div class="text-sm font-mono">
                                    {{ config.bot_id }}
                                </div>
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Bot Username
                                </div>
                                <div class="text-sm">
                                    {{ config.bot_username || "—" }}
                                </div>
                            </div>
                            <div>
                                <div class="text-xs text-muted mb-1">
                                    Webhook URL
                                </div>
                                <div class="text-sm truncate">
                                    {{ config.webhook_url || "—" }}
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

                    <UModal v-model:open="editDialog" title="Edit Zalo bot">
                        <template #body>
                            <div class="space-y-3">
                                <UFormField label="Bot Username"
                                    ><UInput
                                        v-model="editForm.bot_username"
                                        class="w-full"
                                /></UFormField>
                                <USwitch
                                    v-model="editForm.is_active"
                                    label="Active"
                                />
                            </div>
                        </template>
                        <template #footer>
                            <div class="flex justify-end gap-2 w-full">
                                <UButton
                                    variant="ghost"
                                    @click="editDialog = false"
                                    >Cancel</UButton
                                ><UButton
                                    color="primary"
                                    :loading="saving"
                                    @click="saveEdit"
                                    >Save</UButton
                                >
                            </div>
                        </template>
                    </UModal>

                    <UModal
                        v-model:open="confirmDelete"
                        title="Delete Zalo bot"
                    >
                        <template #body
                            ><p class="text-sm">
                                Delete bot <b>{{ config.bot_id }}</b> and all
                                related chats? This cannot be undone.
                            </p></template
                        >
                        <template #footer
                            ><div class="flex justify-end gap-2 w-full">
                                <UButton
                                    variant="ghost"
                                    @click="confirmDelete = false"
                                    >Cancel</UButton
                                ><UButton
                                    color="error"
                                    :loading="deleting"
                                    @click="doDelete"
                                    >Delete</UButton
                                >
                            </div></template
                        >
                    </UModal>
                </template>
            </div>
        </template>
    </UDashboardPanel>
</template>
