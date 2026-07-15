<script setup lang="ts">
import api from '../../../api'

const router = useRouter()
const channels = ref<any[]>([])
const loading = ref(true)
const activeTab = ref('facebook')
const deleting = ref(false)

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

async function disconnect() {
  deleting.value = true
  try {
    await api.delete('/facebook/config')
    channels.value = []
  } finally {
    deleting.value = false
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
          <UButton v-if="channels.length" icon="i-lucide-plus" @click="router.push('/admin/integrations/connect')">
            Connect Channel
          </UButton>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <ULoader />
      </div>

      <!-- Empty State -->
      <div v-else-if="!channels.length" class="flex flex-col items-center justify-center py-24">
        <UIcon name="i-lucide-plug" class="text-muted size-16 mb-4" />
        <h3 class="text-lg font-semibold mb-2">No channels connected</h3>
        <p class="text-muted text-sm mb-6">Connect Facebook Messenger to start auto-replying to messages.</p>
        <UButton icon="i-lucide-plus" @click="router.push('/admin/integrations/connect')">
          Connect Channel
        </UButton>
      </div>

      <!-- Channel Tabs -->
      <div v-else>
        <UTabs :items="[{ label: channels[0].page_name, icon: 'i-lucide-facebook', value: 'facebook' }]" v-model="activeTab" />

        <!-- Facebook Channel Detail -->
        <div v-if="activeTab === 'facebook' && channels.length" class="mt-6">
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
              <UButton variant="outline" icon="i-lucide-pencil" @click="router.push('/admin/integrations/edit')">
                Edit
              </UButton>
              <UButton color="error" variant="outline" icon="i-lucide-trash-2" :loading="deleting" @click="disconnect">
                Disconnect
              </UButton>
            </div>
          </UCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
