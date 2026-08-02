<script setup lang="ts">
import api, { getErrorMessage } from '../../api'
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

const connectSchema = z.object({
  page_name: z.string().min(1, 'Page name is required'),
  page_id: z.string().min(1, 'Page ID is required'),
  page_token: z.string().min(1, 'Page access token is required'),
  verify_token: z.string().min(1, 'Verify token is required'),
})
type ConnectSchema = z.output<typeof connectSchema>
const connectState = reactive<Partial<ConnectSchema>>({
  page_name: '',
  page_id: '',
  page_token: '',
  verify_token: '',
})

const editSchema = z.object({
  page_name: z.string().min(1, 'Page name is required'),
  page_token: z.string().min(1, 'Page access token is required'),
  verify_token: z.string().min(1, 'Verify token is required'),
})
type EditSchema = z.output<typeof editSchema>
const editState = reactive<Partial<EditSchema>>({
  page_name: '',
  page_token: '',
  verify_token: '',
})

const editPageId = ref('')

watch(connectModalOpen, (open) => {
  if (open) {
    connectState.page_name = ''
    connectState.page_id = ''
    connectState.page_token = ''
    connectState.verify_token = ''
    connectError.value = ''
  }
})

watch(editModalOpen, (open) => {
  if (open) {
    editState.page_name = ''
    editState.page_token = ''
    editState.verify_token = ''
    editError.value = ''
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

async function submitConfig(
  saving: Ref<boolean>,
  error: Ref<string>,
  modal: Ref<boolean>,
  payload: Record<string, string>,
) {
  saving.value = true
  error.value = ''
  try {
    await api.post('/facebook/config', payload)
    modal.value = false
    await loadChannels()
  } catch (err: any) {
    error.value = getErrorMessage(err)
  } finally {
    saving.value = false
  }
}

function handleConnect(event: FormSubmitEvent<ConnectSchema>) {
  submitConfig(connectSaving, connectError, connectModalOpen, {
    page_id: event.data.page_id,
    page_name: event.data.page_name || 'Facebook Page',
    page_token: event.data.page_token,
    verify_token: event.data.verify_token,
  })
}

async function loadEditConfig() {
  editLoading.value = true
  try {
    const { data } = await api.get('/facebook/config')
    editPageId.value = data.page_id
    editState.page_name = data.page_name || 'Facebook Page'
    editState.verify_token = data.verify_token
  } catch {
    editModalOpen.value = false
  } finally {
    editLoading.value = false
  }
}

function handleSave(event: FormSubmitEvent<EditSchema>) {
  submitConfig(editSaving, editError, editModalOpen, {
    page_id: editPageId.value,
    page_name: event.data.page_name || 'Facebook Page',
    page_token: event.data.page_token,
    verify_token: event.data.verify_token,
  })
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
      <div v-if="editLoading" class="flex justify-center py-8">
        <ULoader />
      </div>

      <UForm v-else id="edit-form" :schema="editSchema" :state="editState" class="space-y-4" @submit="handleSave">
        <div class="flex items-center gap-3 mb-4">
          <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
            <UIcon name="i-lucide-facebook" class="text-primary size-5" />
          </div>
          <div>
            <h3 class="font-semibold">Facebook Messenger</h3>
          </div>
        </div>

        <UFormField name="page_id" label="Page ID" hint="Cannot be changed">
          <UInput :model-value="editPageId" size="sm" class="w-full" disabled />
        </UFormField>

        <UFormField name="page_name" label="Page Name" hint="Display name for this channel" required>
          <UInput v-model="editState.page_name" placeholder="e.g. My Business Page" size="sm" class="w-full" />
        </UFormField>

        <UFormField name="page_token" label="Page Access Token" hint="Long-lived token for production" required>
          <UInput v-model="editState.page_token" placeholder="Paste your Page Access Token" type="password" size="sm" class="w-full" />
        </UFormField>

        <UFormField name="verify_token" label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
          <UInput v-model="editState.verify_token" placeholder="e.g. my_verify_token" size="sm" class="w-full" />
        </UFormField>

        <UAlert v-if="editError" color="error" variant="subtle" icon="i-lucide-alert-circle" :description="editError" />
      </UForm>
    </template>

    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton v-if="!editLoading" type="submit" form="edit-form" label="Save" :loading="editSaving" />
    </template>
  </UModal>

  <UModal v-model:open="disconnectConfirmOpen" title="Disconnect channel" description="This will disconnect your Facebook Messenger integration. Auto-replies will stop working.">
    <template #footer="{ close }">
      <UButton label="Cancel" color="neutral" variant="outline" @click="close" />
      <UButton label="Disconnect" color="error" :loading="disconnecting" @click="handleDisconnect" />
    </template>
  </UModal>
</template>
