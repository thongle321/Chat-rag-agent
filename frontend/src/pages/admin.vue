<script lang="ts" setup>
import { useRoute } from "vue-router";
import DefaultLayout from "../layouts/default.vue";

const route = useRoute();
</script>

<template>
  <!-- biome-ignore lint/correctness/useYamlInstead: admin.vue requires route check -->
  <DefaultLayout v-if="route.path !== '/admin/login'">
    <RouterView />
  </DefaultLayout>
  <RouterView v-else />
</template>
