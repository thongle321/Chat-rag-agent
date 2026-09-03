<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatView from "../../components/ChatView.vue";

const route = useRoute();
const router = useRouter();
// :key forces a fresh ChatView per session so back/forward just works
const id = computed(() => String(route.params.id ?? ""));
</script>

<template>
  <ChatView :session-id="id" :key="id" @not-found="router.replace('/')" />
</template>
