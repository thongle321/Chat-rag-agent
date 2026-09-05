<script setup lang="ts">
import { Comark } from "@comark/vue";
import { useClipboard } from "@vueuse/core";
import type { ChatMessage } from "../../stores/chat";
import { stripInlineCitations } from "../../utils/text";
import Indicator from "./Indicator.vue";
import ProductCard from "./ProductCard.vue";
import SourceLink from "./SourceLink.vue";

const props = defineProps<{
	msg: ChatMessage;
	/** Live counter while streaming; final frozen time once done (null = untimed reply). */
	thoughtSecs: number | null;
}>();
const emit = defineEmits<{ followup: [text: string] }>();

const { copy, copied } = useClipboard();
const sourcesOpen = ref<string | undefined>();
const activeCite = ref<number | null>(null);
</script>

<template>
  <div class="flex gap-3.5 mb-3.5">
    <UAvatar icon="i-lucide-bot" size="md" class="bg-primary/10 text-primary shrink-0" />
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-2 text-xs text-muted">
        <span class="font-semibold text-default">VeilAi</span>
        <span v-if="msg.sources?.length && !msg.streaming">· {{ msg.sources.length }} sources</span>
      </div>

      <template v-if="msg.streaming && !msg.text">
        <Indicator :label="`Thinking… ${(thoughtSecs ?? 0).toFixed(1)}s`" />
      </template>
      <template v-else>
        <div v-if="msg.streaming" class="text-xs text-muted mb-1">Thinking {{ (thoughtSecs ?? 0).toFixed(1) }}s…</div>
        <div v-else-if="thoughtSecs != null" class="text-xs text-muted mb-1">Thought for {{ thoughtSecs.toFixed(1) }}s</div>
        <Suspense>
          <Comark :markdown="stripInlineCitations(msg.text)" :streaming="!!msg.streaming" caret class="text-sm text-default leading-relaxed prose prose-sm dark:prose-invert max-w-none" />
        </Suspense>

        <template v-if="!msg.streaming">
          <UAccordion
            v-if="msg.sources?.length"
            v-model="sourcesOpen"
            :items="[{ label: `Sources (${msg.sources.length})`, icon: 'i-lucide-book-open', value: 'sources' }]"
            class="mt-3"
            :ui="{ trigger: 'text-xs font-medium', body: 'text-xs' }"
          >
            <template #body>
              <div class="grid md:grid-cols-2 gap-2">
                <SourceLink
                  v-for="s in msg.sources"
                  :id="`citation-${msg.id}-${s.n}`"
                  :key="s.n"
                  :n="s.n"
                  :title="s.title"
                  :reference="s.reference"
                  :active="activeCite === s.n"
                  @click="activeCite = s.n"
                />
              </div>
            </template>
          </UAccordion>

          <div v-if="msg.products?.length" class="mt-3">
            <div class="grid sm:grid-cols-2 gap-2">
              <ProductCard v-for="p in msg.products" :key="p.id" :product="p" />
            </div>
          </div>

          <div v-if="msg.followups?.length" class="flex flex-wrap gap-1.5 mt-3">
            <UButton v-for="f in msg.followups" :key="f" size="xs" color="neutral" variant="soft" icon="i-lucide-message-circle-question" @click="emit('followup', f)">{{ f }}</UButton>
          </div>

          <div class="flex items-center gap-1 mt-3">
            <UButton variant="ghost" color="neutral" size="xs" :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'" @click="copy(msg.text)">
              {{ copied ? "Copied" : "Copy" }}
            </UButton>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
