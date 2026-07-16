<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useHead } from '@unhead/vue'
import { useColorMode } from '@vueuse/core'
import { useAuthStore } from './stores/auth'

const colorMode = useColorMode()
const auth = useAuthStore()

onMounted(() => auth.fetchUser())

const themeColor = computed(() => colorMode.value === 'dark' ? '#18181b' : '#ffffff')

useHead({
  meta: [
    { name: 'theme-color', content: themeColor }
  ]
})
</script>

<template>
  <UApp>
    <RouterView />
  </UApp>
</template>
