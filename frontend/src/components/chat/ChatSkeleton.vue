<template>
  <!-- Cold session still hydrating: skeleton instead of blank flash -->
  <div class="max-w-[820px] mx-auto px-3 md:px-7 py-6 flex flex-col gap-5">
    <div class="flex justify-end"><USkeleton class="h-12 w-2/3 rounded-2xl" /></div>
    <div class="flex gap-3.5">
      <USkeleton class="size-8 rounded-full shrink-0" />
      <div class="flex-1 flex flex-col gap-2"><USkeleton class="h-4 w-full" /><USkeleton class="h-4 w-5/6" /><USkeleton class="h-4 w-3/6" /></div>
    </div>
    <div class="flex justify-end"><USkeleton class="h-10 w-1/2 rounded-2xl" /></div>
  </div>
</template>
