<script setup lang="ts">
import ChatView from "../components/ChatView.vue";
</script>

<template>
  <!-- Always a blank composer like ChatGPT — first send routes to /c/:id -->
  <ChatView :session-id="null" />
</template>
