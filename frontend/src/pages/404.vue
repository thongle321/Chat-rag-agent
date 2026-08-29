<template>
  <UError
    icon="i-lucide-file-x"
    :error="{ statusCode: 404, statusMessage: 'Page not found', message: 'The page you are looking for does not exist.' }"
  >
    <template #links>
      <UButton icon="i-lucide-home" to="/">Back to home</UButton>
    </template>
  </UError>
</template>
