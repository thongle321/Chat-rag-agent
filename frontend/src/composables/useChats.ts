import { computed } from "vue";
import { createSharedComposable } from "@vueuse/core";
import { useChatStore } from "../stores/chat";

// date-fns-like helpers without adding dep — same grouping as chat-vue template
function isToday(d: Date) {
  const now = new Date();
  return d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
}
function isYesterday(d: Date) {
  const y = new Date();
  y.setDate(y.getDate() - 1);
  return d.getDate() === y.getDate() && d.getMonth() === y.getMonth() && d.getFullYear() === y.getFullYear();
}
function subDays(date: Date, days: number) {
  const d = new Date(date);
  d.setDate(d.getDate() - days);
  return d;
}
function subMonths(date: Date, months: number) {
  const d = new Date(date);
  d.setMonth(d.getMonth() - months);
  return d;
}

/**
 * Shared composable mirroring nuxt-ui-templates/chat-vue/src/composables/useChats.ts
 * Groups chats by date like template: Today / Yesterday / Last week / Last month / Month Year
 * Keeps same UI but refactors grouping logic to template's approach (date-fns style).
 */
export const useChats = createSharedComposable(() => {
  const chatStore = useChatStore();

  const groups = computed(() => {
    const today: typeof chatStore.conversations.value = [];
    const yesterday: typeof chatStore.conversations.value = [];
    const lastWeek: typeof chatStore.conversations.value = [];
    const lastMonth: typeof chatStore.conversations.value = [];
    const older: Record<string, typeof chatStore.conversations.value> = {};

    const oneWeekAgo = subDays(new Date(), 7);
    const oneMonthAgo = subMonths(new Date(), 1);

    for (const c of chatStore.conversations) {
      const d = new Date(c.createdAt);
      if (isToday(d)) today.push(c);
      else if (isYesterday(d)) yesterday.push(c);
      else if (d >= oneWeekAgo) lastWeek.push(c);
      else if (d >= oneMonthAgo) lastMonth.push(c);
      else {
        const monthYear = d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
        if (!older[monthYear]) older[monthYear] = [];
        older[monthYear].push(c);
      }
    }

    const sortedMonthYears = Object.keys(older).sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    // newest month first
    sortedMonthYears.reverse();

    const formatted: Array<{ id: string; label: string; items: typeof chatStore.conversations.value }> = [];
    if (today.length) formatted.push({ id: "today", label: "Today", items: today });
    if (yesterday.length) formatted.push({ id: "yesterday", label: "Yesterday", items: yesterday });
    if (lastWeek.length) formatted.push({ id: "last-week", label: "Last week", items: lastWeek });
    if (lastMonth.length) formatted.push({ id: "last-month", label: "Last month", items: lastMonth });
    for (const k of sortedMonthYears) {
      if (older[k]?.length) formatted.push({ id: k, label: k, items: older[k] });
    }
    // Fallback to simple grouping if no dates (keeps UI same)
    if (!formatted.length && chatStore.conversations.length) {
      return [{ id: "all", label: "Conversations", items: chatStore.conversations }];
    }
    return formatted;
  });

  return {
    groups,
    chats: computed(() => chatStore.conversations),
    fetchChats: () => chatStore.fetchSessions(),
    updateChat: (id: string, partial: { label?: string; title?: string }) => {
      if (partial.label || partial.title) chatStore.renameConversation(id, (partial.label || partial.title) as string);
    },
    removeChat: (id: string) => chatStore.deleteConversation(id),
  };
});
