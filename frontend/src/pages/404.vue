<template>
  <UError
    :error="{ statusCode: 404, statusMessage: 'Page not found', message: 'The page you are looking for does not exist.' }"
    icon="i-lucide-file-x"
  >
    <template #links>
      <UButton to="/" icon="i-lucide-home">Back to home</UButton>
    </template>
  </UError>
</template>
