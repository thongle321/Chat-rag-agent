<script setup lang="ts">
import api from '../../api'

const router = useRouter()

const dashStats = ref({ total_documents: 0, total_chunks: 0, total_sessions: 0, total_queries: 0 })

const stats = computed(() => [
  { label: 'Documents', value: dashStats.value.total_documents, icon: 'i-lucide-file-text', color: 'primary' as const },
  { label: 'Chunks', value: dashStats.value.total_chunks, icon: 'i-lucide-layers', color: 'info' as const },
  { label: 'Sessions', value: dashStats.value.total_sessions, icon: 'i-lucide-message-square', color: 'success' as const },
  { label: 'Queries', value: dashStats.value.total_queries, icon: 'i-lucide-search', color: 'warning' as const },
])

const recentSessions = ref<any[]>([])

const health = ref({ api: false, vector_store: false })

onMounted(async () => {
  try {
    const { data } = await api.get('/stats')
    dashStats.value = data
  } catch {
    // keep defaults
  }
  try {
    const { data } = await api.get('/chat/sessions')
    recentSessions.value = data.slice(0, 5)
  } catch {
    // keep empty
  }
  try {
    const { data } = await api.get('/health/detailed')
    health.value = {
      api: data.status === 'ok',
      vector_store: data.components?.vector_store === 'ok',
    }
  } catch {
    health.value = { api: false, vector_store: false }
  }
})
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

            <div v-if="recentSessions.length">
              <div
                v-for="session in recentSessions"
                :key="session.id"
                class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                @click="router.push('/')"
              >
                <UIcon name="i-lucide-message-square" class="text-primary" />
                <span class="flex-1 truncate text-sm">{{ session.title }}</span>
                <span class="text-xs text-muted shrink-0">{{ session.message_count }} msgs</span>
              </div>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-8">
              <UIcon name="i-lucide-inbox" class="text-4xl text-muted mb-2" />
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

            <div class="flex flex-col gap-3">
              <div class="flex items-center justify-between">
                <span class="text-sm">API Server</span>
                <UBadge :color="health.api ? 'success' : 'error'" variant="soft" size="sm">
                  {{ health.api ? 'Normal' : 'Error' }}
                </UBadge>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm">Vector Store</span>
                <UBadge :color="health.vector_store ? 'success' : 'error'" variant="soft" size="sm">
                  {{ health.vector_store ? 'Normal' : 'Error' }}
                </UBadge>
              </div>
            </div>
          </UCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
