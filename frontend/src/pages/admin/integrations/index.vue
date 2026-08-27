<script setup lang="ts">
import api, { getErrorMessage } from '../../../api'
import { z } from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const channels = ref<any[]>([])
const loading = ref(true)

const connectModalOpen = ref(false)
const connectSaving = ref(false)
const connectError = ref('')

const editModalOpen = ref(false)
const editLoading = ref(true)
const editSaving = ref(false)
const editError = ref('')

const disconnectConfirmOpen = ref(false)
const disconnecting = ref(false)
const disconnectTarget = ref<any | null>(null)

const syncIntervalOptions = [
  { label: 'Every 1 minute', value: 1 },
  { label: 'Every 5 minutes', value: 5 },
  { label: 'Every 10 minutes', value: 10 },
  { label: 'Every 15 minutes (default)', value: 15 },
  { label: 'Every 30 minutes', value: 30 },
  { label: 'Every 1 hour', value: 60 },
  { label: 'Every 6 hours', value: 360 },
  { label: 'Every day', value: 1440 },
]

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60) || 'channel'
}

function channelSlug(ch: any): string {
  return ch.slug || slugify(ch.page_name || ch.page_id)
}

const connectSchema = z.object({
  page_name: z.string().min(1, 'Page name is required'),
  page_id: z.string().min(1, 'Page ID is required'),
  page_token: z.string().min(1, 'Page access token is required'),
  verify_token: z.string().min(1, 'Verify token is required'),
  sync_interval: z.number().int().min(1).default(15),
})
type ConnectSchema = z.output<typeof connectSchema>
const connectState = reactive<Partial<ConnectSchema>>({
  page_name: '',
  page_id: '',
  page_token: '',
  verify_token: '',
  sync_interval: 15,
})

const editSchema = z.object({
  page_name: z.string().min(1, 'Page name is required'),
  page_token: z.string().min(1, 'Page access token is required'),
  verify_token: z.string().min(1, 'Verify token is required'),
  sync_interval: z.number().int().min(1).default(15),
})
type EditSchema = z.output<typeof editSchema>
const editState = reactive<Partial<EditSchema>>({
  page_name: '',
  page_token: '',
  verify_token: '',
  sync_interval: 15,
})

const editTarget = ref<any | null>(null)
const toast = useToast()

watch(connectModalOpen, (open) => {
  if (open) {
    connectState.page_name = ''
    connectState.page_id = ''
    connectState.page_token = ''
    connectState.verify_token = ''
    connectState.sync_interval = 15
    connectError.value = ''
  }
})

watch(editModalOpen, (open) => {
  if (open) {
    editState.page_name = editTarget.value?.page_name || ''
    editState.page_token = ''
    editState.verify_token = editTarget.value?.verify_token || ''
    editState.sync_interval = editTarget.value?.sync_interval ?? 15
    editError.value = ''
  }
})

async function loadChannels() {
  loading.value = true
  try {
    const { data } = await api.get('/facebook/channels')
    channels.value = Array.isArray(data) ? data : []
    // Fallback: legacy single config id=1 with no channels yet may return legacy-1; keep as is
  } catch {
    channels.value = []
  } finally {
    loading.value = false
  }
}

async function handleConnect(event: FormSubmitEvent<ConnectSchema>) {
  connectSaving.value = true
  connectError.value = ''
  try {
    await api.post('/facebook/channels', {
      page_id: event.data.page_id,
      page_name: event.data.page_name || 'Facebook Page',
      page_token: event.data.page_token,
      verify_token: event.data.verify_token,
      sync_interval: event.data.sync_interval ?? 15,
    })
    connectModalOpen.value = false
    await loadChannels()
    toast.add({ title: 'Connected', color: 'success', icon: 'i-lucide-check' })
  } catch (err: unknown) {
    connectError.value = getErrorMessage(err)
  } finally {
    connectSaving.value = false
  }
}

function openEdit(ch: any) {
  editTarget.value = ch
  editModalOpen.value = true
}

async function handleSave(event: FormSubmitEvent<EditSchema>) {
  if (!editTarget.value) return
  editSaving.value = true
  editError.value = ''
  try {
    await api.put(`/facebook/channels/${editTarget.value.id}`, {
      page_name: event.data.page_name || 'Facebook Page',
      page_token: event.data.page_token || undefined,
      verify_token: event.data.verify_token,
      sync_interval: event.data.sync_interval ?? 15,
    })
    editModalOpen.value = false
    await loadChannels()
    toast.add({ title: 'Saved', color: 'success' })
  } catch (err: unknown) {
    editError.value = getErrorMessage(err)
  } finally {
    editSaving.value = false
  }
}

function confirmDisconnect(ch: any) {
  disconnectTarget.value = ch
  disconnectConfirmOpen.value = true
}

async function handleDisconnect() {
  if (!disconnectTarget.value) return
  disconnecting.value = true
  try {
    await api.delete(`/facebook/channels/${disconnectTarget.value.id}`)
    await loadChannels()
    disconnectConfirmOpen.value = false
    disconnectTarget.value = null
  } finally {
    disconnecting.value = false
  }
}

const healthChecking = ref<string | null>(null)
const syncing = ref<string | null>(null)

async function testConnection(ch: any) {
  healthChecking.value = ch.id
  try {
    const { data } = await api.get(`/facebook/channels/${ch.id}/health`)
    toast.add({ title: data.ok ? 'Connection OK' : 'Connection failed', description: data.ok ? data.page_name || 'Reachable' : data.error, color: data.ok ? 'success' : 'error' })
    await loadChannels()
  } catch (err: unknown) {
    toast.add({ title: 'Connection failed', description: getErrorMessage(err), color: 'error' })
  } finally {
    healthChecking.value = null
  }
}

async function syncNow(ch: any) {
  syncing.value = ch.id
  try {
    const { data } = await api.post(`/facebook/channels/${ch.id}/sync`)
    toast.add({ title: data.status === 'success' ? 'Synced' : 'Sync error', color: data.status === 'success' ? 'success' : 'error' })
    await loadChannels()
  } catch (err: unknown) {
    toast.add({ title: 'Sync failed', description: getErrorMessage(err), color: 'error' })
  } finally {
    syncing.value = null
  }
}

function formatSyncInterval(v: number) {
  if (!v) return '15 min'
  if (v < 60) return `${v} min`
  if (v < 1440) return `${v / 60} h`
  return `${v / 1440} day`
}

onMounted(() => {
  loadChannels()
})
</script>

<template>
  <UDashboardPanel id="integrations">
    <template #header>
      <UDashboardNavbar title="Integrations">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UButton icon="i-lucide-plus" @click="connectModalOpen = true">
            Connect Channel
          </UButton>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div v-if="loading" class="flex justify-center py-12">
        <ULoader />
      </div>

      <div v-else-if="!channels.length" class="flex flex-col items-center justify-center py-24">
        <UIcon name="i-lucide-plug" class="text-muted size-16 mb-4" />
        <h3 class="text-lg font-semibold mb-2">No channels connected</h3>
        <p class="text-muted text-sm mb-6">Connect Facebook Messenger to start auto-replying to messages. Add unlimited Pages.</p>
        <UButton icon="i-lucide-plus" @click="connectModalOpen = true">
          Connect Channel
        </UButton>
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <UCard
          v-for="ch in channels"
          :key="ch.id"
          class="flex flex-col cursor-pointer hover:shadow-md transition"
          @click="$router.push(`/admin/integrations/${channelSlug(ch)}`)"
        >
          <div class="flex items-center gap-3 mb-4">
            <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10 shrink-0">
              <UIcon name="i-lucide-facebook" class="text-primary size-5" />
            </div>
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold truncate">{{ ch.page_name }}</h3>
              <p class="text-xs text-muted truncate">Page ID: {{ ch.page_id }}</p>
            </div>
            <UBadge v-if="ch.last_sync_status === 'success'" color="success" variant="soft" size="xs">Synced</UBadge>
            <UBadge v-else-if="ch.last_sync_status === 'error'" color="error" variant="soft" size="xs">Error</UBadge>
          </div>

          <div class="grid grid-cols-2 gap-2 text-xs mb-4">
            <div class="p-2 rounded-lg bg-muted/50">
              <div class="text-muted">Sync interval</div>
              <div class="font-medium">{{ formatSyncInterval(ch.sync_interval || 15) }}</div>
            </div>
            <div class="p-2 rounded-lg bg-muted/50">
              <div class="text-muted">Total conversations</div>
              <div class="font-medium">{{ ch.total_conversations ?? 0 }}</div>
            </div>
            <div class="p-2 rounded-lg bg-muted/50 col-span-2">
              <div class="text-muted">Last sync</div>
              <div class="font-medium truncate">{{ ch.last_sync_at ? new Date(ch.last_sync_at.replace(' ', 'T') + 'Z').toLocaleString() : '—' }}</div>
            </div>
            <div class="p-2 rounded-lg bg-muted/50 col-span-2">
              <div class="text-muted">Date created</div>
              <div class="font-medium truncate">{{ ch.created_at ? new Date(ch.created_at.replace(' ', 'T') + 'Z').toLocaleString() : '—' }}</div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 mt-auto">
            <UButton variant="ghost" size="xs" icon="i-lucide-pencil" @click.stop="openEdit(ch)">
              Edit
            </UButton>
            <UButton variant="ghost" size="xs" icon="i-lucide-activity" :loading="healthChecking === ch.id" @click.stop="testConnection(ch)">
              Test
            </UButton>
            <UButton variant="ghost" size="xs" icon="i-lucide-refresh-cw" :loading="syncing === ch.id" @click.stop="syncNow(ch)">
              Sync
            </UButton>
            <UButton color="error" variant="ghost" size="xs" icon="i-lucide-trash-2" @click.stop="confirmDisconnect(ch)">
              Disconnect
            </UButton>
          </div>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>

  <UModal v-model:open="connectModalOpen" title="Connect Channel" description="Connect your Facebook fanpage">
    <template #body>
      <UForm id="connect-form" :schema="connectSchema" :state="connectState" class="space-y-4" @submit="handleConnect">
        <UFormField name="page_name" label="Page Name" hint="Display name for this channel" required>
          <UInput v-model="connectState.page_name" placeholder="e.g. My Business Page" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="page_id" label="Page ID" hint="From Facebook Page Settings" required>
          <UInput v-model="connectState.page_id" placeholder="e.g. 1234567890" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="page_token" label="Page Access Token" hint="Use a long-lived token for production" required>
          <UInput v-model="connectState.page_token" placeholder="Paste your Page Access Token" type="password" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="verify_token" label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
          <UInput v-model="connectState.verify_token" placeholder="e.g. my_verify_token" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="sync_interval" label="Sync interval" hint="Polling cadence for backfill">
          <USelect v-model="connectState.sync_interval" :items="syncIntervalOptions" size="sm" class="w-full" />
        </UFormField>
        <UAlert v-if="connectError" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="connectError" />
      </UForm>
    </template>
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="connect-form" label="Connect" :loading="connectSaving" />
    </template>
  </UModal>

  <UModal v-model:open="editModalOpen" title="Edit Channel">
    <template #body>
      <UForm id="edit-form" :schema="editSchema" :state="editState" class="space-y-4" @submit="handleSave">
        <div class="flex items-center gap-3 mb-2">
          <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
            <UIcon name="i-lucide-facebook" class="text-primary size-5" />
          </div>
          <div>
            <h3 class="font-semibold">Facebook Messenger</h3>
            <p class="text-xs text-muted">Page ID: {{ editTarget?.page_id }}</p>
          </div>
        </div>
        <UFormField name="page_name" label="Page Name" hint="Display name for this channel" required>
          <UInput v-model="editState.page_name" placeholder="e.g. My Business Page" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="page_token" label="Page Access Token" hint="Leave blank to keep existing">
          <UInput v-model="editState.page_token" placeholder="Paste new token or leave blank" type="password" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="verify_token" label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
          <UInput v-model="editState.verify_token" placeholder="e.g. my_verify_token" size="sm" class="w-full" />
        </UFormField>
        <UFormField name="sync_interval" label="Sync interval">
          <USelect v-model="editState.sync_interval" :items="syncIntervalOptions" size="sm" class="w-full" />
        </UFormField>
        <UAlert v-if="editError" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="editError" />
      </UForm>
    </template>
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="edit-form" label="Save" :loading="editSaving" />
    </template>
  </UModal>

  <UModal v-model:open="disconnectConfirmOpen" title="Disconnect channel" :description="`This will disconnect ${disconnectTarget?.page_name || 'this channel'}. Auto-replies will stop.`">
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton label="Disconnect" color="error" :loading="disconnecting" @click="handleDisconnect" />
    </template>
  </UModal>
</template>
