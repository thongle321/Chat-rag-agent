<script setup lang="ts">
import type { FormSubmitEvent } from "@nuxt/ui";
import { z } from "zod";
import api, { getErrorMessage } from "../../../api";

const channels = ref<any[]>([]);
const loading = ref(true);

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
    loadChannels();
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
                        @click="connectModalOpen = true"
                    >
                        Connect Channel
                    </UButton>
                </template>
            </UDashboardNavbar>
        </template>

        <template #body>
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
                            Disconnect
                        </UButton>
                    </div>
                </UCard>
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
</template>
