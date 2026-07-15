<script setup lang="ts">
import { useDocumentStore } from '../../stores/documents'
import { useChatStore } from '../../stores/chat'

const router = useRouter()
const documentStore = useDocumentStore()
const chatStore = useChatStore()

const stats = computed(() => [
  { label: 'Documents', value: documentStore.documents.length, icon: 'i-lucide-file-text', color: 'primary' as const },
  { label: 'Queries', value: chatStore.messages.filter(m => m.role === 'user').length, icon: 'i-lucide-message-square', color: 'success' as const },
])

const recentChats = computed(() =>
  chatStore.messages
    .filter(m => m.role === 'user')
    .slice(-5)
    .reverse()
)

const apiStatus = ref(true)
</script>

<template>
  <UDashboardPanel id="home">
    <template #header>
      <UDashboardNavbar title="Dashboard">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col gap-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <UCard v-for="stat in stats" :key="stat.label">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-sm text-muted">{{ stat.label }}</p>
                <p class="text-2xl font-bold mt-1 font-[var(--font-display)]">{{ stat.value }}</p>
              </div>
              <UIcon :name="stat.icon" class="text-3xl text-muted opacity-50" />
            </div>
          </UCard>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <UCard class="lg:col-span-2">
            <template #header>
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-bell" class="text-primary" />
                <span class="font-semibold">Recent Activity</span>
              </div>
            </template>

            <div v-if="recentChats.length">
              <div
                v-for="chat in recentChats"
                :key="chat.id"
                class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                @click="router.push('/')"
              >
                <UIcon name="i-lucide-message-square" class="text-primary" />
                <span class="flex-1 truncate text-sm">{{ chat.text }}</span>
              </div>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-8">
              <UIcon name="i-lucide-check-circle" class="text-4xl text-success mb-2" />
              <p class="text-muted">No data</p>
            </div>
          </UCard>

          <UCard>
            <template #header>
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-check-circle" class="text-success" />
                <span class="font-semibold">System Status</span>
              </div>
            </template>

            <div class="flex items-center justify-between">
              <span class="text-sm">API Server</span>
              <UBadge :color="apiStatus ? 'success' : 'error'" variant="soft" size="sm">
                {{ apiStatus ? 'Normal' : 'Error' }}
              </UBadge>
            </div>
          </UCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
