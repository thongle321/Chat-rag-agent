<script setup lang="ts">
import api, { getErrorMessage } from '../../../api'

const router = useRouter()
const pageName = ref('')
const pageId = ref('')
const pageToken = ref('')
const verifyToken = ref('')
const saving = ref(false)
const error = ref('')

async function connect() {
  saving.value = true
  error.value = ''
  try {
    await api.post('/facebook/config', {
      page_id: pageId.value,
      page_name: pageName.value || 'Facebook Page',
      page_token: pageToken.value,
      verify_token: verifyToken.value,
    })
    router.push('/admin/integrations')
  } catch (err: any) {
    error.value = getErrorMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <UDashboardPanel id="integrations-connect">
    <template #header>
      <UDashboardNavbar title="Connect Channel">
        <template #leading>
          <UButton icon="i-lucide-arrow-left" variant="ghost" @click="router.push('/admin/integrations')" />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="max-w-lg">
        <UCard>
          <div class="flex items-center gap-3 mb-6">
            <div class="flex items-center justify-center size-10 rounded-lg bg-primary/10">
              <UIcon name="i-lucide-facebook" class="text-primary size-5" />
            </div>
            <div>
              <h3 class="font-semibold">Facebook Messenger</h3>
              <p class="text-sm text-muted">Connect your Facebook fanpage</p>
            </div>
          </div>

          <form @submit.prevent="connect" class="space-y-4">
            <UFormField label="Page Name" hint="Display name for this channel" required>
              <UInput
                v-model="pageName"
                placeholder="e.g. My Business Page"
                size="sm"
                class="w-full"
              />
            </UFormField>

            <UFormField label="Page ID" hint="From Facebook Page Settings" required>
              <UInput
                v-model="pageId"
                placeholder="e.g. 1234567890"
                size="sm"
                class="w-full"
              />
            </UFormField>

            <UFormField label="Page Access Token" hint="Use a long-lived token for production" required>
              <UInput
                v-model="pageToken"
                placeholder="Paste your Page Access Token"
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
              <UButton type="submit" :loading="saving" :disabled="!pageId || !pageToken || !verifyToken">
                Connect
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
