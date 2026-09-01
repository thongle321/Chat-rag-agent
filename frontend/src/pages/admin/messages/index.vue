<script setup lang="ts">
import api from "../../../api";

const activeTab = ref<"facebook" | "zalo">("facebook");
const loading = ref(true);
const channels = ref<any[]>([]);
const zaloChannels = ref<any[]>([]);
const selectedPageId = ref<string>("");
const selectedZaloId = ref<string>("");
const users = ref<any[]>([]);

function formatDateTime(v: string | null) {
	if (!v) return "—";
	const iso = v.includes("T") ? v : `${v.replace(" ", "T")}Z`;
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return v;
	return d.toLocaleString();
}

async function loadChannels() {
	try {
		const { data } = await api.get("/facebook/channels");
		channels.value = Array.isArray(data) ? data : [];
		if (channels.value.length && !selectedPageId.value)
			selectedPageId.value = channels.value[0].page_id;
	} catch {
		channels.value = [];
	}
}
async function loadZaloChannels() {
	try {
		const { data } = await api.get("/zalo/channels");
		zaloChannels.value = Array.isArray(data) ? data : [];
		if (zaloChannels.value.length && !selectedZaloId.value)
			selectedZaloId.value = zaloChannels.value[0].bot_id;
	} catch { zaloChannels.value = []; }
}

const currentPage = ref(1);
const perPage = 10;
const pagedUsers = computed(() => {
	const start = (currentPage.value - 1) * perPage;
	return users.value.slice(start, start + perPage);
});
const totalPages = computed(() => Math.ceil(users.value.length / perPage));

async function loadUsers() {
	loading.value = true;
	try {
		if (activeTab.value === "facebook") {
			if (!selectedPageId.value) { users.value = []; return; }
			const { data } = await api.get(`/facebook/channels/${selectedPageId.value}/conversations`);
			const list = data.conversations || [];
			users.value = list.map((c: any) => ({
				session_id: c.session_id,
				username: c.username || "Facebook User",
				displayName: c.username || "Facebook User",
				channel_type: "facebook",
				message_count: c.message_count ?? 0,
				updated_at: c.updated_at,
				page_id: selectedPageId.value,
			}));
		} else {
			if (!selectedZaloId.value) { users.value = []; return; }
			const { data } = await api.get(`/zalo/channels/${selectedZaloId.value}/conversations`);
			const list = data.conversations || [];
			users.value = list.map((c: any) => ({
				session_id: c.session_id,
				username: c.username || "Zalo User",
				displayName: c.username || "Zalo User",
				channel_type: "zalo",
				message_count: c.message_count ?? 0,
				updated_at: c.updated_at,
				page_id: selectedZaloId.value,
			}));
		}
	} catch { users.value = []; } finally { loading.value = false; }
}

watch(selectedPageId, () => {
	if (activeTab.value === "facebook") { currentPage.value = 1; loadUsers(); }
});
watch(selectedZaloId, () => {
	if (activeTab.value === "zalo") { currentPage.value = 1; loadUsers(); }
});
watch(activeTab, () => { currentPage.value = 1; loadUsers(); });

onMounted(async () => {
	await Promise.all([loadChannels(), loadZaloChannels()]);
	await loadUsers();
});
</script>

<template>
  <UDashboardPanel id="messages">
    <template #header>
      <UDashboardNavbar title="Messages">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <USelect v-if="activeTab === 'facebook' && channels.length" v-model="selectedPageId" :items="channels.map(c => ({ label: `${c.page_name} (${c.page_id})`, value: c.page_id }))" size="sm" class="min-w-64" />
          <USelect v-if="activeTab === 'zalo' && zaloChannels.length" v-model="selectedZaloId" :items="zaloChannels.map(c => ({ label: `${c.bot_username || c.bot_id} (${c.bot_id})`, value: c.bot_id }))" size="sm" class="min-w-64" />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UTabs v-model="activeTab" :items="[{ label: 'Facebook', icon: 'i-lucide-facebook', value: 'facebook' }, { label: 'Zalo', icon: 'i-lucide-bot', value: 'zalo' }]" class="mb-4" />
      <div v-if="loading" class="flex justify-center py-12"><ULoader /></div>
      <div v-else-if="activeTab === 'facebook' && !channels.length" class="flex flex-col items-center py-16">
        <UIcon name="i-lucide-messages-square" class="size-12 text-muted mb-3" />
        <p class="text-muted">No Facebook channels — connect one in Integrations first.</p>
        <UButton to="/admin/integrations" class="mt-4">Go to integrations</UButton>
      </div>
      <div v-else-if="activeTab === 'zalo' && !zaloChannels.length" class="flex flex-col items-center py-16">
        <UIcon name="i-lucide-bot" class="size-12 text-muted mb-3" />
        <p class="text-muted">No Zalo bots — connect one in Integrations first.</p>
        <UButton to="/admin/integrations" class="mt-4">Go to integrations</UButton>
      </div>
      <div v-else-if="!users.length" class="flex flex-col items-center py-16">
        <UIcon name="i-lucide-inbox" class="size-12 text-muted mb-3" />
        <p class="text-muted">No conversations yet — messages via webhook will appear here.</p>
      </div>
      <div v-else class="p-0 w-full">
        <UCard :ui="{ body: 'p-0' }">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-xs text-muted">
                  <th class="text-left py-2 px-3 font-medium">Username</th>
                  <th class="text-left py-2 px-3 font-medium">Channel</th>
                  <th class="text-left py-2 px-3 font-medium">Total messages</th>
                  <th class="text-left py-2 px-3 font-medium">Date</th>
                  <th class="w-8"></th>
                </tr>
              </thead>
              <tbody class="divide-y">
                <tr
                  v-for="u in pagedUsers"
                  :key="u.session_id"
                  class="hover:bg-muted/30 cursor-pointer"
                  @click="$router.push(`/admin/messages/${u.session_id}?page_id=${u.page_id}`)"
                >
                  <td class="py-3 px-3">
                    <div class="flex items-center gap-2">
                      <div class="size-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <UIcon name="i-lucide-user" class="size-4 text-primary" />
                      </div>
                      <span class="font-medium truncate">{{ u.displayName }}</span>
                    </div>
                  </td>
                  <td class="py-3 px-3"><UBadge :color="u.channel_type === 'zalo' ? 'success' : 'primary'" variant="soft" size="xs">{{ u.channel_type }}</UBadge></td>
                  <td class="py-3 px-3 text-xs text-muted">{{ u.message_count }}</td>
                  <td class="py-3 px-3 text-xs text-muted whitespace-nowrap">{{ formatDateTime(u.updated_at) }}</td>
                  <td class="py-3 px-3"><UIcon name="i-lucide-chevron-right" class="text-muted" /></td>
                </tr>
                <tr v-if="!pagedUsers.length">
                  <td colspan="5" class="py-8 text-center text-muted text-sm">No conversations</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="totalPages > 1" class="flex justify-center p-3 border-t">
            <UPagination v-model="currentPage" :length="totalPages" :total-visible="5" />
          </div>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
