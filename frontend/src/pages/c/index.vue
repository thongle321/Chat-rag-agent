<script setup lang="ts">
import { useRouter } from "vue-router";

// /c without an id is not a session — bounce to the blank composer.
const router = useRouter();
router.replace("/");
</script>

<template>
  <div />
</template>
