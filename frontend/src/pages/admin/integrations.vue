<script setup lang="ts">
import api, { getErrorMessage } from '../../api'

const channels = ref<any[]>([])
const loading = ref(true)
const connectModalOpen = ref(false)
const connectPageName = ref('')
const connectPageId = ref('')
const connectPageToken = ref('')
const connectVerifyToken = ref('')
const connectSaving = ref(false)
const connectError = ref('')

const editModalOpen = ref(false)
const editLoading = ref(true)
const editPageId = ref('')
const editPageName = ref('')
const editPageToken = ref('')
const editVerifyToken = ref('')
const editSaving = ref(false)
const editError = ref('')

const disconnectConfirmOpen = ref(false)
const disconnecting = ref(false)

watch(connectModalOpen, (open) => {
  if (open) {
    connectPageName.value = ''
    connectPageId.value = ''
    connectPageToken.value = ''
    connectVerifyToken.value = ''
    connectError.value = ''
  }
})

watch(editModalOpen, (open) => {
  if (open) {
    editError.value = ''
    editPageToken.value = ''
    loadEditConfig()
  }
})

async function loadChannels() {
  loading.value = true
  try {
    const { data } = await api.get('/facebook/config')
    channels.value = [{ type: 'facebook', ...data }]
  } catch {
    channels.value = []
  } finally {
    loading.value = false
  }
}

async function handleConnect() {
  connectSaving.value = true
  connectError.value = ''
  try {
    await api.post('/facebook/config', {
      page_id: connectPageId.value,
      page_name: connectPageName.value || 'Facebook Page',
      page_token: connectPageToken.value,
      verify_token: connectVerifyToken.value,
    })
    connectModalOpen.value = false
    await loadChannels()
  } catch (err: any) {
    connectError.value = getErrorMessage(err)
  } finally {
    connectSaving.value = false
  }
}

async function loadEditConfig() {
  editLoading.value = true
  try {
    const { data } = await api.get('/facebook/config')
    editPageId.value = data.page_id
    editPageName.value = data.page_name || 'Facebook Page'
    editPageToken.value = ''
    editVerifyToken.value = data.verify_token
  } catch {
    editModalOpen.value = false
  } finally {
    editLoading.value = false
  }
}

async function handleSave() {
  editSaving.value = true
  editError.value = ''
  try {
    await api.post('/facebook/config', {
      page_id: editPageId.value,
      page_name: editPageName.value || 'Facebook Page',
      page_token: editPageToken.value,
      verify_token: editVerifyToken.value,
    })
    editModalOpen.value = false
    await loadChannels()
  } catch (err: any) {
    editError.value = getErrorMessage(err)
  } finally {
    editSaving.value = false
  }
}

async function handleDisconnect() {
  disconnecting.value = true
  try {
    await api.delete('/facebook/config')
    channels.value = []
    disconnectConfirmOpen.value = false
  } finally {
    disconnecting.value = false
  }
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
          <UButton v-if="channels.length" icon="i-lucide-plus" @click="connectModalOpen = true">
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
        <p class="text-muted text-sm mb-6">Connect Facebook Messenger to start auto-replying to messages.</p>
        <UButton icon="i-lucide-plus" @click="connectModalOpen = true">
          Connect Channel
        </UButton>
      </div>

      <div v-else>
        <div class="mt-2">
          <UCard>
            <div class="flex items-center gap-3 mb-6">
              <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
                <UIcon name="i-lucide-facebook" class="text-primary size-5" />
              </div>
              <div>
                <h3 class="font-semibold">{{ channels[0].page_name }}</h3>
                <p class="text-sm text-muted">Page ID: {{ channels[0].page_id }}</p>
              </div>
              <UBadge color="success" variant="soft" size="xs" class="ml-auto">Connected</UBadge>
            </div>

            <div class="flex gap-2">
              <UButton variant="outline" icon="i-lucide-pencil" @click="editModalOpen = true">
                Edit
              </UButton>
              <UButton color="error" variant="outline" icon="i-lucide-trash-2" @click="disconnectConfirmOpen = true">
                Disconnect
              </UButton>
            </div>
          </UCard>
      </div>
      </div>
    </template>
  </UDashboardPanel>

  <UModal v-model:open="connectModalOpen" title="Connect Channel" description="Connect your Facebook fanpage">
    <template #body>
      <form id="connect-form" @submit.prevent="handleConnect" class="space-y-4">
        <UFormField label="Page Name" hint="Display name for this channel" required>
          <UInput v-model="connectPageName" placeholder="e.g. My Business Page" size="sm" class="w-full" />
        </UFormField>

        <UFormField label="Page ID" hint="From Facebook Page Settings" required>
          <UInput v-model="connectPageId" placeholder="e.g. 1234567890" size="sm" class="w-full" />
        </UFormField>

        <UFormField label="Page Access Token" hint="Use a long-lived token for production" required>
          <UInput v-model="connectPageToken" placeholder="Paste your Page Access Token" type="password" size="sm" class="w-full" />
        </UFormField>

        <UFormField label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
          <UInput v-model="connectVerifyToken" placeholder="e.g. my_verify_token" size="sm" class="w-full" />
        </UFormField>

        <UAlert v-if="connectError" type="error" :description="connectError" />
      </form>
    </template>

    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton type="submit" form="connect-form" label="Connect" :loading="connectSaving" :disabled="!connectPageId || !connectPageToken || !connectVerifyToken" />
    </template>
  </UModal>

  <UModal v-model:open="editModalOpen" title="Edit Channel">
    <template #body>
      <div v-if="editLoading" class="flex justify-center py-8">
        <ULoader />
      </div>

      <form v-else id="edit-form" @submit.prevent="handleSave" class="space-y-4">
        <div class="flex items-center gap-3 mb-4">
          <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
            <UIcon name="i-lucide-facebook" class="text-primary size-5" />
          </div>
          <div>
            <h3 class="font-semibold">Facebook Messenger</h3>
          </div>
        </div>

        <UFormField label="Page ID" hint="Cannot be changed">
          <UInput :model-value="editPageId" size="sm" class="w-full" disabled />
        </UFormField>

        <UFormField label="Page Name" hint="Display name for this channel" required>
          <UInput v-model="editPageName" placeholder="e.g. My Business Page" size="sm" class="w-full" />
        </UFormField>

        <UFormField label="Page Access Token" hint="Long-lived token for production" required>
          <UInput v-model="editPageToken" placeholder="Paste your Page Access Token" type="password" size="sm" class="w-full" />
        </UFormField>

        <UFormField label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
          <UInput v-model="editVerifyToken" placeholder="e.g. my_verify_token" size="sm" class="w-full" />
        </UFormField>

        <UAlert v-if="editError" type="error" :description="editError" />
      </form>
    </template>

    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton v-if="!editLoading" type="submit" form="edit-form" label="Save" :loading="editSaving" :disabled="!editPageName || !editPageToken || !editVerifyToken" />
    </template>
  </UModal>

  <UModal v-model:open="disconnectConfirmOpen" title="Disconnect channel" description="This will disconnect your Facebook Messenger integration. Auto-replies will stop working.">
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton label="Disconnect" color="error" :loading="disconnecting" @click="handleDisconnect" />
    </template>
  </UModal>
</template>
