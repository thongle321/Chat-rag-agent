<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import api, { getErrorMessage } from "../../../api";

const activeTab = ref("facebook");

const channels = ref<any[]>([]);
const loading = ref(true);
// Zalo
const zaloChannels = ref<any[]>([]);
const zaloLoading = ref(true);
const zaloConnectModalOpen = ref(false);
const zaloConnectSaving = ref(false);
const zaloConnectError = ref("");
const zaloEditModalOpen = ref(false);
const zaloEditSaving = ref(false);
const zaloEditError = ref("");
const zaloDisconnectConfirmOpen = ref(false);
const zaloDisconnecting = ref(false);
const zaloDisconnectTarget = ref<any | null>(null);

const connectModalOpen = ref(false);
const connectSaving = ref(false);
const connectError = ref("");

const editModalOpen = ref(false);
const editSaving = ref(false);
const editError = ref("");

const disconnectConfirmOpen = ref(false);
const disconnecting = ref(false);
const disconnectTarget = ref<any | null>(null);

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

const connectSchema = z.object({
    page_id: z.string().min(1, "Page ID is required"),
    page_name: z.string().min(1, "Page name is required"),
    page_token: z.string().min(1, "Page access token is required"),
    sync_interval: z.number().int().min(1).default(15),
    verify_token: z.string().min(1, "Verify token is required"),
});
type ConnectSchema = z.output<typeof connectSchema>;
const connectState = reactive<Partial<ConnectSchema>>({
    page_id: "",
    page_name: "",
    page_token: "",
    sync_interval: 15,
    verify_token: "",
});

const editSchema = z.object({
    page_name: z.string().min(1, "Page name is required"),
    page_token: z.string().min(1, "Page access token is required"),
    sync_interval: z.number().int().min(1).default(15),
    verify_token: z.string().min(1, "Verify token is required"),
});
type EditSchema = z.output<typeof editSchema>;
const editState = reactive<Partial<EditSchema>>({
    page_name: "",
    page_token: "",
    sync_interval: 15,
    verify_token: "",
});

const zaloConnectSchema = z.object({
    bot_token: z.string().min(1, "Bot token is required"),
    bot_username: z.string().optional(),
    webhook_url: z.string().url("Must be a valid URL").optional().or(z.literal("")),
    verify_token: z.string().min(8, "Verify token 8..256 chars").max(256),
});
type ZaloConnectSchema = z.output<typeof zaloConnectSchema>;
const zaloConnectState = reactive<Partial<ZaloConnectSchema>>({ bot_token: "", bot_username: "", webhook_url: "", verify_token: "" });
const zaloEditSchema = z.object({
    bot_username: z.string().optional(),
    bot_token: z.string().optional(),
    verify_token: z.string().min(8).max(256).optional().or(z.literal("")),
    webhook_url: z.string().optional(),
});
type ZaloEditSchema = z.output<typeof zaloEditSchema>;
const zaloEditState = reactive<Partial<ZaloEditSchema>>({ bot_username: "", bot_token: "", verify_token: "", webhook_url: "" });
const zaloEditTarget = ref<any | null>(null);

const editTarget = ref<any | null>(null);
const toast = useToast();

watch(connectModalOpen, (open) => {
    if (open) {
        connectState.page_name = "";
        connectState.page_id = "";
        connectState.page_token = "";
        connectState.verify_token = "";
        connectState.sync_interval = 15;
        connectError.value = "";
    }
});

watch(editModalOpen, (open) => {
    if (open) {
        editState.page_name = editTarget.value?.page_name || "";
        editState.page_token = "";
        editState.verify_token = editTarget.value?.verify_token || "";
        editState.sync_interval = editTarget.value?.sync_interval ?? 15;
        editError.value = "";
    }
});
watch(zaloConnectModalOpen, (open) => {
    if (open) { zaloConnectState.bot_token = ""; zaloConnectState.bot_username = ""; zaloConnectState.webhook_url = ""; zaloConnectState.verify_token = ""; zaloConnectError.value = ""; }
});
watch(zaloEditModalOpen, (open) => {
    if (open) { zaloEditState.bot_username = zaloEditTarget.value?.bot_username || ""; zaloEditState.bot_token = ""; zaloEditState.verify_token = zaloEditTarget.value?.verify_token || ""; zaloEditState.webhook_url = zaloEditTarget.value?.webhook_url || ""; zaloEditError.value = ""; }
});

async function loadChannels() {
    loading.value = true;
    try {
        const { data } = await api.get("/facebook/channels");
        channels.value = Array.isArray(data) ? data : [];
    } catch {
        channels.value = [];
    } finally {
        loading.value = false;
    }
}
async function loadZaloChannels() {
    zaloLoading.value = true;
    try {
        const { data } = await api.get("/zalo/channels");
        zaloChannels.value = Array.isArray(data) ? data : [];
    } catch { zaloChannels.value = []; } finally { zaloLoading.value = false; }
}

async function handleConnect(event: FormSubmitEvent<ConnectSchema>) {
    connectSaving.value = true;
    connectError.value = "";
    try {
        await api.post("/facebook/channels", {
            page_id: event.data.page_id,
            page_name: event.data.page_name || "Facebook Page",
            page_token: event.data.page_token,
            sync_interval: event.data.sync_interval ?? 15,
            verify_token: event.data.verify_token,
        });
        connectModalOpen.value = false;
        await loadChannels();
        toast.add({
            color: "success",
            icon: "i-lucide-check",
            title: "Connected",
        });
    } catch (err: unknown) {
        connectError.value = getErrorMessage(err);
    } finally {
        connectSaving.value = false;
    }
}

function openEdit(ch: any) {
    editTarget.value = ch;
    editModalOpen.value = true;
}

async function handleSave(event: FormSubmitEvent<EditSchema>) {
    if (!editTarget.value) {
        return;
    }
    editSaving.value = true;
    editError.value = "";
    try {
        await api.put(`/facebook/channels/${editTarget.value.id}`, {
            page_name: event.data.page_name || "Facebook Page",
            page_token: event.data.page_token || undefined,
            sync_interval: event.data.sync_interval ?? 15,
            verify_token: event.data.verify_token,
        });
        editModalOpen.value = false;
        await loadChannels();
        toast.add({ color: "success", title: "Saved" });
    } catch (err: unknown) {
        editError.value = getErrorMessage(err);
    } finally {
        editSaving.value = false;
    }
}

function confirmDisconnect(ch: any) {
    disconnectTarget.value = ch;
    disconnectConfirmOpen.value = true;
}

async function handleDisconnect() {
    if (!disconnectTarget.value) {
        return;
    }
    disconnecting.value = true;
    try {
        await api.delete(`/facebook/channels/${disconnectTarget.value.id}`);
        await loadChannels();
        disconnectConfirmOpen.value = false;
        disconnectTarget.value = null;
    } finally {
        disconnecting.value = false;
    }
}

async function handleZaloConnect(event: FormSubmitEvent<ZaloConnectSchema>) {
    zaloConnectSaving.value = true; zaloConnectError.value = "";
    try {
        await api.post("/zalo/channels", { bot_token: event.data.bot_token, bot_username: event.data.bot_username || undefined, webhook_url: event.data.webhook_url || undefined, verify_token: event.data.verify_token });
        zaloConnectModalOpen.value = false; await loadZaloChannels(); toast.add({ color: "success", icon: "i-lucide-check", title: "Zalo Connected" });
    } catch (err: unknown) { zaloConnectError.value = getErrorMessage(err); } finally { zaloConnectSaving.value = false; }
}
function openZaloEdit(ch: any) { zaloEditTarget.value = ch; zaloEditModalOpen.value = true; }
async function handleZaloSave(event: FormSubmitEvent<ZaloEditSchema>) {
    if (!zaloEditTarget.value) return; zaloEditSaving.value = true; zaloEditError.value = "";
    try {
        await api.put(`/zalo/channels/${zaloEditTarget.value.id}`, { bot_username: event.data.bot_username || undefined, bot_token: event.data.bot_token || undefined, verify_token: event.data.verify_token || undefined, webhook_url: event.data.webhook_url || undefined });
        zaloEditModalOpen.value = false; await loadZaloChannels(); toast.add({ color: "success", title: "Saved" });
    } catch (err: unknown) { zaloEditError.value = getErrorMessage(err); } finally { zaloEditSaving.value = false; }
}
function confirmZaloDisconnect(ch: any) { zaloDisconnectTarget.value = ch; zaloDisconnectConfirmOpen.value = true; }
async function handleZaloDisconnect() {
    if (!zaloDisconnectTarget.value) return; zaloDisconnecting.value = true;
    try { await api.delete(`/zalo/channels/${zaloDisconnectTarget.value.id}`); await loadZaloChannels(); zaloDisconnectConfirmOpen.value = false; zaloDisconnectTarget.value = null; } finally { zaloDisconnecting.value = false; }
}
async function testZaloConnection(ch: any) {
    healthChecking.value = ch.id;
    try { const { data } = await api.get(`/zalo/channels/${ch.id}/health`); toast.add({ color: data.ok ? "success" : "error", description: data.ok ? data.account_name || "Reachable" : data.error, title: data.ok ? "Connection OK" : "Connection failed" }); await loadZaloChannels(); }
    catch (err: unknown) { toast.add({ color: "error", description: getErrorMessage(err), title: "Connection failed" }); } finally { healthChecking.value = null; }
}
async function syncZaloNow(ch: any) {
    syncing.value = ch.id;
    try { const { data } = await api.post(`/zalo/channels/${ch.id}/sync`); toast.add({ color: data.status === "success" ? "success" : "error", title: data.status === "success" ? "Synced" : "Sync error" }); await loadZaloChannels(); }
    catch (err: unknown) { toast.add({ color: "error", description: getErrorMessage(err), title: "Sync failed" }); } finally { syncing.value = null; }
}

const healthChecking = ref<string | null>(null);
const syncing = ref<string | null>(null);

async function testConnection(ch: any) {
    healthChecking.value = ch.id;
    try {
        const { data } = await api.get(`/facebook/channels/${ch.id}/health`);
        toast.add({
            color: data.ok ? "success" : "error",
            description: data.ok ? data.page_name || "Reachable" : data.error,
            title: data.ok ? "Connection OK" : "Connection failed",
        });
        await loadChannels();
    } catch (err: unknown) {
        toast.add({
            color: "error",
            description: getErrorMessage(err),
            title: "Connection failed",
        });
    } finally {
        healthChecking.value = null;
    }
}

async function syncNow(ch: any) {
    syncing.value = ch.id;
    try {
        const { data } = await api.post(`/facebook/channels/${ch.id}/sync`);
        toast.add({
            color: data.status === "success" ? "success" : "error",
            title: data.status === "success" ? "Synced" : "Sync error",
        });
        await loadChannels();
    } catch (err: unknown) {
        toast.add({
            color: "error",
            description: getErrorMessage(err),
            title: "Sync failed",
        });
    } finally {
        syncing.value = null;
    }
}

function _formatSyncInterval(v: number) {
    if (!v) {
        return "15 min";
    }
    if (v < 60) {
        return `${v} min`;
    }
    if (v < 1440) {
        return `${v / 60} h`;
    }
    return `${v / 1440} day`;
}

onMounted(() => {
    loadChannels(); loadZaloChannels();
});
</script>

<template>
    <UDashboardPanel id="integrations">
        <template #header>
            <UDashboardNavbar title="Integrations">
                <template #leading>
                    <UDashboardSidebarCollapse />
                </template>
                <template #right>
                    <UButton
                        icon="i-lucide-plus"
                        @click="activeTab === 'zalo' ? zaloConnectModalOpen = true : connectModalOpen = true"
                    >
                        Connect Channel
                    </UButton>
                </template>
            </UDashboardNavbar>
        </template>

        <template #body>
            <UTabs v-model="activeTab" :items="[{ label: 'Facebook', icon: 'i-lucide-facebook', value: 'facebook' }, { label: 'Zalo', icon: 'i-lucide-bot', value: 'zalo' }]" class="mb-4" />
            <div v-if="activeTab === 'facebook'">
            <div class="flex justify-center py-12" v-if="loading">
                <ULoader />
            </div>

            <div
                class="flex flex-col items-center justify-center py-24"
                v-else-if="!channels.length"
            >
                <UIcon class="text-muted size-16 mb-4" name="i-lucide-plug" />
                <h3 class="text-lg font-semibold mb-2">
                    No channels connected
                </h3>
                <p class="text-muted text-sm mb-6">
                    Connect Facebook Messenger to start auto-replying to
                    messages. Add unlimited Pages.
                </p>
                <UButton icon="i-lucide-plus" @click="connectModalOpen = true">
                    Connect Channel
                </UButton>
            </div>

            <div
                class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
                v-else
            >
                <UCard
                    class="flex flex-col cursor-pointer hover:shadow-md transition"
                    v-for="ch in channels"
                    :key="ch.id"
                    @click="$router.push(`/admin/integrations/${ch.slug}`)"
                >
                    <div class="flex items-center gap-3 mb-4">
                        <div
                            class="flex items-center justify-center size-10 rounded-lg bg-primary/10 shrink-0"
                        >
                            <UIcon
                                class="text-primary size-5"
                                name="i-lucide-facebook"
                            />
                        </div>
                        <div class="flex-1 min-w-0">
                            <h3 class="font-semibold truncate">
                                {{ ch.page_name }}
                            </h3>
                            <p class="text-xs text-muted truncate">
                                Page ID: {{ ch.page_id }}
                            </p>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-2 text-xs mb-4">
                        <div class="p-2 rounded-lg col-span-2">
                            <div class="text-muted">Status</div>
                            <div class="font-medium">
                                <UBadge
                                    size="md"
                                    variant="soft"
                                    :color="
                                        ch.is_active ? 'success' : 'neutral'
                                    "
                                >
                                    {{ ch.is_active ? "Active" : "Inactive" }}
                                </UBadge>
                            </div>
                        </div>
                        <div class="p-2 rounded-lg col-span-2">
                            <div class="text-muted">Sync status</div>
                            <div class="font-medium">
                                <UBadge
                                    color="success"
                                    size="md"
                                    variant="soft"
                                    v-if="ch.last_sync_status === 'success'"
                                    >Synced</UBadge
                                >
                                <UBadge
                                    color="error"
                                    size="md"
                                    variant="soft"
                                    v-else-if="ch.last_sync_status === 'error'"
                                    >Error</UBadge
                                >
                                <span class="text-muted" v-else>—</span>
                            </div>
                        </div>
                        <div class="p-2 rounded-lg col-span-2">
                            <div class="text-muted">Last sync</div>
                            <div class="font-medium truncate">
                                {{
                                    ch.last_sync_at
                                        ? new Date(
                                              ch.last_sync_at,
                                          ).toLocaleString()
                                        : "—"
                                }}
                            </div>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-2 mt-auto">
                        <UButton
                            icon="i-lucide-pencil"
                            size="xs"
                            variant="ghost"
                            @click.stop="openEdit(ch)"
                        >
                            Edit
                        </UButton>
                        <UButton
                            icon="i-lucide-activity"
                            size="xs"
                            variant="ghost"
                            :loading="healthChecking === ch.id"
                            @click.stop="testConnection(ch)"
                        >
                            Test
                        </UButton>
                        <UButton
                            icon="i-lucide-refresh-cw"
                            size="xs"
                            variant="ghost"
                            :loading="syncing === ch.id"
                            @click.stop="syncNow(ch)"
                        >
                            Sync
                        </UButton>
                        <UButton
                            color="error"
                            icon="i-lucide-trash-2"
                            size="xs"
                            variant="ghost"
                            @click.stop="confirmDisconnect(ch)"
                        >
                            Delete
                        </UButton>
                    </div>
                </UCard>
            </div>
            </div>
            <div v-if="activeTab === 'zalo'">
                <div class="flex justify-center py-12" v-if="zaloLoading"><ULoader /></div>
                <div class="flex flex-col items-center justify-center py-24" v-else-if="!zaloChannels.length">
                    <UIcon class="text-muted size-16 mb-4" name="i-lucide-bot" />
                    <h3 class="text-lg font-semibold mb-2">No Zalo bots connected</h3>
                    <p class="text-muted text-sm mb-6">Connect a Zalo Bot (from Zalo Bot Creator) to auto-reply. Paste Bot Token + Verify Token.</p>
                    <UButton icon="i-lucide-plus" @click="zaloConnectModalOpen = true">Connect Zalo Bot</UButton>
                    <UAlert class="mt-6 max-w-xl" color="info" variant="soft" title="Webhook" description="Set webhook URL to https://your-host/api/zalo/webhook and use same Verify Token as secret_token via setWebhook." />
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" v-else>
                    <UCard v-for="ch in zaloChannels" :key="ch.id" class="flex flex-col hover:shadow-md transition">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10 shrink-0"><UIcon class="text-primary size-5" name="i-lucide-bot" /></div>
                            <div class="flex-1 min-w-0"><h3 class="font-semibold truncate">{{ ch.bot_username || 'Zalo Bot' }}</h3><p class="text-xs text-muted truncate">Bot ID: {{ ch.bot_id }}</p></div>
                        </div>
                        <div class="grid grid-cols-2 gap-2 text-xs mb-4"><div class="p-2 rounded-lg col-span-2"><div class="text-muted">Status</div><UBadge size="md" variant="soft" :color="ch.is_active ? 'success' : 'neutral'">{{ ch.is_active ? "Active" : "Inactive" }}</UBadge></div></div>
                        <div class="flex flex-wrap gap-2 mt-auto">
                            <UButton icon="i-lucide-pencil" size="xs" variant="ghost" @click.stop="openZaloEdit(ch)">Edit</UButton>
                            <UButton icon="i-lucide-activity" size="xs" variant="ghost" :loading="healthChecking === ch.id" @click.stop="testZaloConnection(ch)">Test</UButton>
                            <UButton icon="i-lucide-refresh-cw" size="xs" variant="ghost" :loading="syncing === ch.id" @click.stop="syncZaloNow(ch)">Sync</UButton>
                            <UButton color="error" icon="i-lucide-trash-2" size="xs" variant="ghost" @click.stop="confirmZaloDisconnect(ch)">Delete</UButton>
                        </div>
                    </UCard>
                </div>
            </div>
        </template>
    </UDashboardPanel>

    <UModal
        description="Connect your Facebook fanpage"
        title="Connect Channel"
        v-model:open="connectModalOpen"
    >
        <template #body>
            <UForm
                class="space-y-4"
                id="connect-form"
                :schema="connectSchema"
                :state="connectState"
                @submit="handleConnect"
            >
                <UFormField
                    hint="Display name for this channel"
                    label="Page Name"
                    name="page_name"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="e.g. My Business Page"
                        size="sm"
                        v-model="connectState.page_name"
                    />
                </UFormField>
                <UFormField
                    hint="From Facebook Page Settings"
                    label="Page ID"
                    name="page_id"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="e.g. 1234567890"
                        size="sm"
                        v-model="connectState.page_id"
                    />
                </UFormField>
                <UFormField
                    hint="Use a long-lived token for production"
                    label="Page Access Token"
                    name="page_token"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="Paste your Page Access Token"
                        size="sm"
                        type="password"
                        v-model="connectState.page_token"
                    />
                </UFormField>
                <UFormField
                    hint="Must match the verification code in Facebook Developer Console"
                    label="Verify Token"
                    name="verify_token"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="e.g. my_verify_token"
                        size="sm"
                        v-model="connectState.verify_token"
                    />
                </UFormField>
                <UFormField
                    hint="Polling cadence for backfill"
                    label="Sync interval"
                    name="sync_interval"
                >
                    <USelect
                        class="w-full"
                        size="sm"
                        v-model="connectState.sync_interval"
                        :items="syncIntervalOptions"
                    />
                </UFormField>
                <UAlert
                    color="error"
                    icon="i-lucide-alert-circle"
                    variant="subtle"
                    v-if="connectError"
                    :description="connectError"
                />
            </UForm>
        </template>
        <template #footer="{ close }">
            <UButton
                color="neutral"
                label="Cancel"
                variant="outline"
                @click="close"
            />
            <UButton
                form="connect-form"
                label="Connect"
                type="submit"
                :loading="connectSaving"
            />
        </template>
    </UModal>

    <UModal title="Edit Channel" v-model:open="editModalOpen">
        <template #body>
            <UForm
                class="space-y-4"
                id="edit-form"
                :schema="editSchema"
                :state="editState"
                @submit="handleSave"
            >
                <div class="flex items-center gap-3 mb-2">
                    <div
                        class="flex items-center justify-center size-10 rounded-lg bg-primary/10"
                    >
                        <UIcon
                            class="text-primary size-5"
                            name="i-lucide-facebook"
                        />
                    </div>
                    <div>
                        <h3 class="font-semibold">Facebook Messenger</h3>
                        <p class="text-xs text-muted">
                            Page ID: {{ editTarget?.page_id }}
                        </p>
                    </div>
                </div>
                <UFormField
                    hint="Display name for this channel"
                    label="Page Name"
                    name="page_name"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="e.g. My Business Page"
                        size="sm"
                        v-model="editState.page_name"
                    />
                </UFormField>
                <UFormField
                    hint="Leave blank to keep existing"
                    label="Page Access Token"
                    name="page_token"
                >
                    <UInput
                        class="w-full"
                        placeholder="Paste new token or leave blank"
                        size="sm"
                        type="password"
                        v-model="editState.page_token"
                    />
                </UFormField>
                <UFormField
                    hint="Must match the verification code in Facebook Developer Console"
                    label="Verify Token"
                    name="verify_token"
                    required
                >
                    <UInput
                        class="w-full"
                        placeholder="e.g. my_verify_token"
                        size="sm"
                        v-model="editState.verify_token"
                    />
                </UFormField>
                <UFormField label="Sync interval" name="sync_interval">
                    <USelect
                        class="w-full"
                        size="sm"
                        v-model="editState.sync_interval"
                        :items="syncIntervalOptions"
                    />
                </UFormField>
                <UAlert
                    color="error"
                    icon="i-lucide-alert-circle"
                    variant="subtle"
                    v-if="editError"
                    :description="editError"
                />
            </UForm>
        </template>
        <template #footer="{ close }">
            <UButton
                color="neutral"
                label="Cancel"
                variant="outline"
                @click="close"
            />
            <UButton
                form="edit-form"
                label="Save"
                type="submit"
                :loading="editSaving"
            />
        </template>
    </UModal>

    <UModal
        title="Disconnect channel"
        v-model:open="disconnectConfirmOpen"
        :description="`This will disconnect ${disconnectTarget?.page_name || 'this channel'}. Auto-replies will stop.`"
    >
        <template #footer="{ close }">
            <UButton
                color="neutral"
                label="Cancel"
                variant="outline"
                @click="close"
            />
            <UButton
                color="error"
                label="Disconnect"
                :loading="disconnecting"
                @click="handleDisconnect"
            />
        </template>
    </UModal>
    <UModal title="Connect Zalo Bot" v-model:open="zaloConnectModalOpen" description="Paste Bot Token from Zalo Bot Creator">
        <template #body>
            <UForm class="space-y-4" id="zalo-connect-form" :schema="zaloConnectSchema" :state="zaloConnectState" @submit="handleZaloConnect">
                <UFormField label="Bot Token" name="bot_token" required hint="From Zalo Bot Creator message, e.g. 123456:abc-xyz"><UInput class="w-full" size="sm" type="password" v-model="zaloConnectState.bot_token" placeholder="123456:abc-xyz" /></UFormField>
                <UFormField label="Webhook URL" name="webhook_url" hint="https://your-host/api/zalo/webhook"><UInput class="w-full" size="sm" v-model="zaloConnectState.webhook_url" placeholder="https://example.com/api/zalo/webhook" /></UFormField>
                <UFormField label="Verify Token" name="verify_token" required hint="8..256 chars, also as secret_token"><UInput class="w-full" size="sm" v-model="zaloConnectState.verify_token" placeholder="my_verify_token" /></UFormField>
                <p class="text-xs text-muted">Bot name will be auto-filled from Zalo via getMe (account_name).</p>
                <UAlert v-if="zaloConnectError" color="error" variant="subtle" :description="zaloConnectError" />
            </UForm>
        </template>
        <template #footer="{ close }">
            <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
            <UButton form="zalo-connect-form" label="Connect" type="submit" :loading="zaloConnectSaving" />
        </template>
    </UModal>
    <UModal title="Edit Zalo Bot" v-model:open="zaloEditModalOpen">
        <template #body>
            <UForm class="space-y-4" id="zalo-edit-form" :schema="zaloEditSchema" :state="zaloEditState" @submit="handleZaloSave">
                <UFormField label="Bot Token" name="bot_token" hint="Leave blank to keep"><UInput class="w-full" size="sm" type="password" v-model="zaloEditState.bot_token" placeholder="Leave blank" /></UFormField>
                <UFormField label="Verify Token" name="verify_token"><UInput class="w-full" size="sm" v-model="zaloEditState.verify_token" /></UFormField>
                <UFormField label="Webhook URL" name="webhook_url"><UInput class="w-full" size="sm" v-model="zaloEditState.webhook_url" /></UFormField>
                <p class="text-xs text-muted">Bot name is always synced from Zalo account_name.</p>
                <UAlert v-if="zaloEditError" color="error" variant="subtle" :description="zaloEditError" />
            </UForm>
        </template>
        <template #footer="{ close }"><UButton color="neutral" label="Cancel" variant="outline" @click="close" /><UButton form="zalo-edit-form" label="Save" type="submit" :loading="zaloEditSaving" /></template>
    </UModal>
    <UModal title="Disconnect Zalo bot" v-model:open="zaloDisconnectConfirmOpen" :description="`Disconnect ${zaloDisconnectTarget?.bot_username || 'this bot'}?`">
        <template #footer="{ close }"><UButton color="neutral" label="Cancel" variant="outline" @click="close" /><UButton color="error" label="Disconnect" :loading="zaloDisconnecting" @click="handleZaloDisconnect" /></template>
    </UModal>
</template>
