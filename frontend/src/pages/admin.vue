<script setup lang="ts">
import { useRoute } from 'vue-router'
import DefaultLayout from '../layouts/default.vue'

const route = useRoute()
</script>

<template>
  <DefaultLayout v-if="route.path !== '/admin/login'">
    <RouterView />
  </DefaultLayout>
  <RouterView v-else />
</template>
