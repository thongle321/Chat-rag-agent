<script setup lang="ts">
const hour = new Date().getHours();
const greeting =
	hour < 11 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
</script>

<template>
  <div class="max-w-[760px] mx-auto px-8 py-10">
    <div class="text-center mb-9">
      <div class="flex items-center justify-center size-14 rounded-2xl bg-primary/10 mx-auto mb-4">
        <UIcon name="i-lucide-message-square" class="size-7 text-primary" />
      </div>
      <h1 class="text-2xl font-bold text-default">{{ greeting }}, what would you like to look up?</h1>
      <p class="mt-2 text-muted text-sm">
        Ask questions about your document content to get answers from your AI assistant.
      </p>
    </div>
  </div>
</template>
