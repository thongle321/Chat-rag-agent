<script setup lang="ts">
import api, { getErrorMessage } from "../../../api";
import ConfirmModal from "../../../components/admin/ConfirmModal.vue";
import ChannelCard from "../../../components/admin/channels/ChannelCard.vue";
import FacebookConnectForm from "../../../components/admin/channels/FacebookConnectForm.vue";
import FacebookEditForm from "../../../components/admin/channels/FacebookEditForm.vue";
import ZaloConnectForm from "../../../components/admin/channels/ZaloConnectForm.vue";
import ZaloEditForm from "../../../components/admin/channels/ZaloEditForm.vue";
import EmptyState from "../../../components/admin/EmptyState.vue";
import { useChannelCrud } from "../../../composables/useChannelCrud";
import { useSettingsStore } from "../../../stores/settings";

const activeTab = ref("facebook");
const toast = useToast();
const settingsStore = useSettingsStore();

const fb = useChannelCrud("/facebook/channels", (data) => data.page_name);
const zalo = useChannelCrud("/zalo/channels", (data) => data.account_name);

// Connect / edit modals (payloads differ per provider; post-save funnels into the crud loaders)
const connectModalOpen = ref(false);
const connectSaving = ref(false);
const connectError = ref("");
const editModalOpen = ref(false);
const editSaving = ref(false);
const editError = ref("");
const editTarget = ref<any | null>(null);

const zaloConnectModalOpen = ref(false);
const zaloConnectSaving = ref(false);
const zaloConnectError = ref("");
const zaloEditModalOpen = ref(false);
const zaloEditSaving = ref(false);
const zaloEditError = ref("");
const zaloEditTarget = ref<any | null>(null);

async function handleConnect(data: {
	page_id: string;
	page_name: string;
	page_token: string;
	verify_token: string;
	sync_interval?: number;
}) {
	connectSaving.value = true;
	connectError.value = "";
	try {
		await api.post("/facebook/channels", {
			page_id: data.page_id,
			page_name: data.page_name || "Facebook Page",
			page_token: data.page_token,
			sync_interval: data.sync_interval ?? 15,
			verify_token: data.verify_token,
		});
		connectModalOpen.value = false;
		await fb.load();
		toast.add({ color: "success", icon: "i-lucide-check", title: "Connected" });
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

async function handleSave(data: {
	page_name: string;
	page_token: string;
	verify_token: string;
	sync_interval?: number;
}) {
	if (!editTarget.value) return;
	editSaving.value = true;
	editError.value = "";
	try {
		await api.put(`/facebook/channels/${editTarget.value.id}`, {
			page_name: data.page_name || "Facebook Page",
			page_token: data.page_token || undefined,
			sync_interval: data.sync_interval ?? 15,
			verify_token: data.verify_token,
		});
		editModalOpen.value = false;
		await fb.load();
		toast.add({ color: "success", title: "Saved" });
	} catch (err: unknown) {
		editError.value = getErrorMessage(err);
	} finally {
		editSaving.value = false;
	}
}

async function handleZaloConnect(data: { bot_token: string; bot_username?: string; verify_token: string }) {
	zaloConnectSaving.value = true;
	zaloConnectError.value = "";
	try {
		// Webhook URL is now global in Settings → Integration, not per-channel
		const globalWebhook = settingsStore.settings.zalo_webhook_url;
		if (!globalWebhook) {
			zaloConnectError.value = "No global Webhook URL set. Go to Settings → Integration and set it first.";
			return;
		}
		const { data: created } = await api.post("/zalo/channels", {
			bot_token: data.bot_token,
			bot_username: data.bot_username || undefined,
			verify_token: data.verify_token,
			webhook_url: globalWebhook || undefined,
		});
		zaloConnectModalOpen.value = false;
		await zalo.load();
		// auto-verify so chat works immediately without manual Test
		try {
			const newId = (created as any)?.id || zalo.items.value.find((c) => c.bot_id === (created as any)?.bot_id)?.id;
			if (newId) {
				await api.get(`/zalo/channels/${newId}/health`);
				await zalo.load();
			}
		} catch {}
		toast.add({ color: "success", icon: "i-lucide-check", title: "Zalo Connected" });
	} catch (err: unknown) {
		zaloConnectError.value = getErrorMessage(err);
	} finally {
		zaloConnectSaving.value = false;
	}
}

function openZaloEdit(ch: any) {
	zaloEditTarget.value = ch;
	zaloEditModalOpen.value = true;
}

async function handleZaloSave(data: {
	bot_username?: string;
	bot_token?: string;
	verify_token?: string;
	webhook_url?: string;
}) {
	if (!zaloEditTarget.value) return;
	zaloEditSaving.value = true;
	zaloEditError.value = "";
	try {
		await api.put(`/zalo/channels/${zaloEditTarget.value.id}`, {
			bot_username: data.bot_username || undefined,
			bot_token: data.bot_token || undefined,
			verify_token: data.verify_token || undefined,
			webhook_url: data.webhook_url || undefined,
		});
		zaloEditModalOpen.value = false;
		await zalo.load();
		toast.add({ color: "success", title: "Saved" });
	} catch (err: unknown) {
		zaloEditError.value = getErrorMessage(err);
	} finally {
		zaloEditSaving.value = false;
	}
}

onMounted(() => {
	fb.load();
	zalo.load();
	settingsStore.fetchSettings().catch(() => {});
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
          <UButton icon="i-lucide-plus" @click="activeTab === 'zalo' ? (zaloConnectModalOpen = true) : (connectModalOpen = true)">Connect Channel</UButton>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UTabs
        v-model="activeTab"
        :items="[
          { label: 'Facebook', icon: 'i-lucide-facebook', value: 'facebook' },
          { label: 'Zalo', icon: 'i-lucide-bot', value: 'zalo' },
        ]"
        class="mb-4"
      />
      <div v-if="activeTab === 'facebook'">
        <div v-if="fb.loading.value" class="flex justify-center py-12">
          <ULoader />
        </div>

        <EmptyState
          v-else-if="!fb.items.value.length"
          title="No channels connected"
          hint="Connect Facebook Messenger"
          action-label="Connect Channel"
          @action="connectModalOpen = true"
        />

        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <ChannelCard
            v-for="ch in fb.items.value"
            :key="ch.id"
            icon="i-lucide-facebook"
            :title="ch.page_name"
            :subtitle="`Page ID: ${ch.page_id}`"
            :active="ch.is_active"
            :to="`/admin/integrations/${ch.slug}`"
          >
            <template #extra>
              <div class="p-2 rounded-lg col-span-2">
                <div class="text-muted">Sync status</div>
                <div class="font-medium">
                  <UBadge v-if="ch.last_sync_status === 'success'" color="success" size="md" variant="soft">Synced</UBadge>
                  <UBadge v-else-if="ch.last_sync_status === 'error'" color="error" size="md" variant="soft">Error</UBadge>
                  <span v-else class="text-muted">—</span>
                </div>
              </div>
              <div class="p-2 rounded-lg col-span-2">
                <div class="text-muted">Last sync</div>
                <div class="font-medium truncate">{{ ch.last_sync_at ? new Date(ch.last_sync_at).toLocaleString() : "—" }}</div>
              </div>
            </template>
            <template #actions>
              <UButton icon="i-lucide-pencil" size="xs" variant="ghost" @click.stop="openEdit(ch)">Edit</UButton>
              <UButton icon="i-lucide-activity" size="xs" variant="ghost" :loading="fb.busyId.value === ch.id" @click.stop="fb.checkHealth(ch)">Test</UButton>
              <UButton icon="i-lucide-refresh-cw" size="xs" variant="ghost" :loading="fb.busyId.value === ch.id" @click.stop="fb.syncNow(ch)">Sync</UButton>
              <UButton color="error" icon="i-lucide-trash-2" size="xs" variant="ghost" @click.stop="fb.confirmDisconnect(ch)">Delete</UButton>
            </template>
          </ChannelCard>
        </div>
      </div>
      <div v-if="activeTab === 'zalo'">
        <div v-if="zalo.loading.value" class="flex justify-center py-12">
          <ULoader />
        </div>
        <EmptyState
          v-else-if="!zalo.items.value.length"
          icon="i-lucide-bot"
          title="No Zalo bots connected"
          hint="Connect a Zalo Bot"
          action-label="Connect Zalo Bot"
          @action="zaloConnectModalOpen = true"
        />
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <ChannelCard
            v-for="ch in zalo.items.value"
            :key="ch.id"
            icon="i-lucide-bot"
            :title="ch.bot_username || 'Zalo Bot'"
            :subtitle="`Bot ID: ${ch.bot_id}`"
            :active="ch.is_active"
            :to="`/admin/integrations/zalo/${ch.slug || ch.id}`"
          >
            <template #actions>
              <UButton icon="i-lucide-pencil" size="xs" variant="ghost" @click.stop="openZaloEdit(ch)">Edit</UButton>
              <UButton icon="i-lucide-activity" size="xs" variant="ghost" :loading="zalo.busyId.value === ch.id" @click.stop="zalo.checkHealth(ch)">Test</UButton>
              <UButton color="error" icon="i-lucide-trash-2" size="xs" variant="ghost" @click.stop="zalo.confirmDisconnect(ch)">Delete</UButton>
            </template>
          </ChannelCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>

  <UModal title="Connect Channel" v-model:open="connectModalOpen">
    <template #body>
      <FacebookConnectForm :open="connectModalOpen" :error="connectError" @submit="handleConnect" />
    </template>
    <template #footer="{ close }">
      <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
      <UButton form="connect-form" label="Connect" type="submit" :loading="connectSaving" />
    </template>
  </UModal>

  <UModal title="Edit Channel" v-model:open="editModalOpen">
    <template #body>
      <FacebookEditForm :open="editModalOpen" :error="editError" :initial="editTarget ?? {}" @submit="handleSave" />
    </template>
    <template #footer="{ close }">
      <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
      <UButton form="edit-form" label="Save" type="submit" :loading="editSaving" />
    </template>
  </UModal>

  <ConfirmModal
    v-model:open="fb.disconnectOpen.value"
    title="Disconnect channel"
    :description="`This will disconnect ${fb.disconnectTarget.value?.page_name || 'this channel'}. Auto-replies will stop.`"
    confirm-label="Disconnect"
    :loading="fb.disconnecting.value"
    @confirm="fb.handleDisconnect"
  />

  <UModal title="Connect Zalo Bot" v-model:open="zaloConnectModalOpen">
    <template #body>
      <ZaloConnectForm :open="zaloConnectModalOpen" :error="zaloConnectError" @submit="handleZaloConnect" />
    </template>
    <template #footer="{ close }">
      <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
      <UButton form="zalo-connect-form" label="Connect" type="submit" :loading="zaloConnectSaving" />
    </template>
  </UModal>

  <UModal title="Edit Zalo Bot" v-model:open="zaloEditModalOpen">
    <template #body>
      <ZaloEditForm :open="zaloEditModalOpen" :error="zaloEditError" :initial="zaloEditTarget ?? {}" @submit="handleZaloSave" />
    </template>
    <template #footer="{ close }">
      <UButton color="neutral" label="Cancel" variant="outline" @click="close" />
      <UButton form="zalo-edit-form" label="Save" type="submit" :loading="zaloEditSaving" />
    </template>
  </UModal>

  <ConfirmModal
    v-model:open="zalo.disconnectOpen.value"
    title="Disconnect Zalo bot"
    :description="`Disconnect ${zalo.disconnectTarget.value?.bot_username || 'this bot'}?`"
    confirm-label="Disconnect"
    :loading="zalo.disconnecting.value"
    @confirm="zalo.handleDisconnect"
  />
</template>
