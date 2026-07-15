<script setup lang="ts">
import api, { getErrorMessage } from '../../../api'

const router = useRouter()
const pageId = ref('')
const pageName = ref('')
const pageToken = ref('')
const verifyToken = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')

async function loadConfig() {
  loading.value = true
  try {
    const { data } = await api.get('/facebook/config')
    pageId.value = data.page_id
    pageName.value = data.page_name || 'Facebook Page'
    verifyToken.value = data.verify_token
  } catch {
    router.push('/admin/integrations')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload: Record<string, string> = {
      page_id: pageId.value,
      page_name: pageName.value || 'Facebook Page',
      verify_token: verifyToken.value,
    }
    if (pageToken.value) {
      payload.page_token = pageToken.value
    }
    await api.post('/facebook/config', payload)
    router.push('/admin/integrations')
  } catch (err: any) {
    error.value = getErrorMessage(err)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<template>
  <UDashboardPanel id="integrations-edit">
    <template #header>
      <UDashboardNavbar title="Edit Channel">
        <template #leading>
          <UButton icon="i-lucide-arrow-left" variant="ghost" @click="router.push('/admin/integrations')" />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div v-if="loading" class="flex justify-center py-12">
        <ULoader />
      </div>

      <div v-else class="max-w-lg">
        <UCard>
          <div class="flex items-center gap-3 mb-6">
            <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
              <UIcon name="i-lucide-facebook" class="text-primary size-5" />
            </div>
            <div>
              <h3 class="font-semibold">Facebook Messenger</h3>
              <p class="text-sm text-muted">Page ID: {{ pageId }}</p>
            </div>
          </div>

          <form @submit.prevent="save" class="space-y-4">
            <UFormField label="Page Name" hint="Display name for this channel" required>
              <UInput
                v-model="pageName"
                placeholder="e.g. My Business Page"
                size="sm"
                class="w-full"
              />
            </UFormField>

            <UFormField label="Page Access Token" hint="Leave blank to keep current">
              <UInput
                v-model="pageToken"
                placeholder="Paste new token to update"
                type="password"
                size="sm"
                class="w-full"
              />
            </UFormField>

            <UFormField label="Verify Token" hint="Must match the verification code in Facebook Developer Console" required>
              <UInput
                v-model="verifyToken"
                placeholder="e.g. my_verify_token"
                size="sm"
                class="w-full"
              />
            </UFormField>

            <UAlert v-if="error" type="error" :description="error" />

            <div class="flex gap-2 pt-2">
              <UButton type="submit" :loading="saving">
                Save
              </UButton>
              <UButton variant="outline" @click="router.push('/admin/integrations')">
                Cancel
              </UButton>
            </div>
          </form>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
