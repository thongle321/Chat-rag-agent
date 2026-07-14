<script setup lang="ts">
const route = useRoute()
const router = useRouter()

if (route.params.all === 'index') {
  router.replace('/')
}
</script>

<template>
  <UDashboardPanel id="not-found">
    <template #header>
      <UDashboardNavbar title="Not Found">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col items-center justify-center h-full">
        <UIcon name="i-lucide-circle-question" class="text-8xl text-muted mb-4" />
        <h1 class="text-4xl font-bold mb-2 font-[var(--font-display)]">404</h1>
        <p class="text-muted">Page not found</p>
        <UButton to="/" class="mt-4">
          Dashboard
        </UButton>
      </div>
    </template>
  </UDashboardPanel>
</template>
