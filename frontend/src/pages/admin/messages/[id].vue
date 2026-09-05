<script setup lang="ts">
import { Comark } from "@comark/vue";
import { useClipboard } from "@vueuse/core";
import api from "../../../api";

const route = useRoute();
const id = computed(() => route.params.id as string);
const pageId = computed(() => (route.query.page_id as string) || "");

const loading = ref(true);
const messages = ref<any[]>([]);
const error = ref("");
const accOpen = reactive<Record<string, string | undefined>>({});
const activeCite = reactive(new Map<string, number>());
const { copy, copied } = useClipboard();

function stripInlineCitations(text: string): string {
	return text.replace(/\s*\[Source:[^\]]*\]/g, "").replace(/\s*\[(\d+)\]/g, "");
}

async function loadThread() {
	loading.value = true;
	error.value = "";
	try {
		const { data: d } = await api.get(`/chat/sessions/${id.value}`);
		messages.value = d.messages || [];
	} catch (err: any) {
		try {
			const { data: d } = await api.get(`/chat/sessions/${id.value}`);
			messages.value = d.messages || [];
		} catch (e: any) {
			error.value = e?.response?.data?.detail || "Thread not found";
			messages.value = [];
		}
	} finally {
		loading.value = false;
	}
}

onMounted(loadThread);
watch(() => route.params.id, loadThread);
</script>

<template>
  <UDashboardPanel id="message-detail">
    <template #header>
      <UDashboardNavbar :title="`Conversation ${id.slice(0, 8)}…`">
        <template #leading>
          <UDashboardSidebarCollapse />
          <UButton icon="i-lucide-arrow-left" variant="ghost" color="neutral" :to="pageId ? `/admin/messages?page_id=${pageId}` : '/admin/messages'" class="ml-2" />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col h-full">
        <div v-if="loading" class="flex justify-center py-16"><ULoader /></div>
        <div v-else-if="error" class="flex flex-col items-center py-12">
          <UIcon name="i-lucide-alert-circle" class="size-12 text-error mb-3" />
          <p class="text-muted mb-4">{{ error }}</p>
          <UButton to="/admin/messages">Back to messages</UButton>
        </div>
        <div v-else-if="!messages.length" class="flex-1 flex items-center justify-center">
          <div class="text-center text-muted py-12">No messages in this conversation.</div>
        </div>
        <div v-else class="flex-1 overflow-y-auto">
          <div class="max-w-[820px] mx-auto px-3 md:px-7 py-6 pb-12">
            <div v-for="m in messages" :key="m.role + m.content.slice(0, 20)">
              <div v-if="m.role === 'user'" class="flex justify-end mb-7">
                <div class="max-w-[85%] md:max-w-[78%] px-4 py-3 rounded-2xl rounded-br-sm text-inverted text-sm leading-relaxed break-words bg-primary">
                  {{ m.content }}
                </div>
              </div>

              <div v-else class="flex gap-3.5 mb-3.5">
                <UAvatar icon="i-lucide-bot" size="md" class="bg-primary/10 text-primary shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-2 text-xs text-muted">
                    <span class="font-semibold text-default">VeilAi</span>
                    <span v-if="m.sources?.length">· {{ m.sources.length }} sources</span>
                  </div>

                  <Suspense>
                    <Comark :markdown="stripInlineCitations(m.content)" :streaming="false" caret class="text-sm text-default leading-relaxed prose prose-sm dark:prose-invert max-w-none" />
                  </Suspense>

                  <UAccordion
                    v-if="m.sources?.length"
                    v-model="accOpen[m.content.slice(0, 20)]"
                    :items="[{ label: `Sources (${m.sources.length})`, icon: 'i-lucide-book-open', value: 'sources' }]"
                    class="mt-3"
                    :ui="{ trigger: 'text-xs font-medium', body: 'text-xs' }"
                  >
                    <template #body>
                      <div class="grid md:grid-cols-2 gap-2">
                        <div
                          v-for="s in m.sources"
                          :id="`citation-${m.content.slice(0, 8)}-${s.n}`"
                          :key="s.n"
                          class="flex gap-2.5 p-2 rounded-lg border cursor-pointer transition"
                          :class="(activeCite.get(m.content.slice(0, 20)) ?? null) === s.n ? 'border-primary bg-primary/10' : 'border-default hover:bg-elevated'"
                          @click="activeCite.set(m.content.slice(0, 20), s.n)"
                        >
                          <div class="w-7 h-7 shrink-0 grid place-items-center rounded-md bg-elevated text-xs font-bold tabular-nums">{{ s.n }}</div>
                          <div class="min-w-0">
                            <div class="font-semibold text-default truncate">{{ s.title }}</div>
                            <div v-if="s.reference" class="text-muted mt-0.5 truncate">{{ s.reference }}</div>
                          </div>
                        </div>
                      </div>
                    </template>
                  </UAccordion>

                  <div class="flex items-center gap-1 mt-3">
                    <UButton
                      variant="ghost"
                      color="neutral"
                      size="xs"
                      :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
                      @click="copy(m.content)"
                    >
                      {{ copied ? 'Copied' : 'Copy' }}
                    </UButton>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex justify-center mt-8">
              <UButton variant="outline" to="/admin/messages">Back to messages</UButton>
            </div>
          </div>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
