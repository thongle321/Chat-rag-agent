<script lang="ts" setup>
import { useHead } from "@unhead/vue";
import { useColorMode } from "@vueuse/core";
import { computed } from "vue";

const colorMode = useColorMode();

const themeColor = computed(() =>
	colorMode.value === "dark" ? "#18181b" : "#ffffff",
);

useHead({
	meta: [{ content: themeColor, name: "theme-color" }],
});
</script>

<template>
  <UApp>
    <RouterView />
  </UApp>
</template>
