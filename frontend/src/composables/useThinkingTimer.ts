import { onUnmounted, type Ref, ref, watch } from "vue";

// Per-message "Thought for Xs" timing: each assistant reply owns its counter,
// frozen when its stream completes so older replies keep their own time.
export function useThinkingTimer(isLoading: Ref<boolean>, liveId: () => string | null) {
	const thinkingStart = ref<number | null>(null);
	const thinkingElapsed = ref(0);
	const thinkingForId = ref<string | null>(null);
	const thinkingTimes = ref<Record<string, number>>({});
	let thinkingTimer: ReturnType<typeof setInterval> | null = null;

	function snapThinking() {
		if (thinkingStart.value) thinkingElapsed.value = (Date.now() - thinkingStart.value) / 1000;
		const live = liveId();
		if (live) thinkingForId.value = live;
		if (thinkingForId.value) thinkingTimes.value[thinkingForId.value] = thinkingElapsed.value;
	}

	function thinkSecs(msg: { id: string }): number {
		if (msg.id && thinkingForId.value === msg.id) return thinkingElapsed.value;
		return thinkingTimes.value[msg.id] ?? 0;
	}

	watch(isLoading, (loading) => {
		if (loading) {
			thinkingStart.value = Date.now();
			thinkingElapsed.value = 0;
			thinkingForId.value = liveId();
			if (thinkingTimer) clearInterval(thinkingTimer);
			thinkingTimer = setInterval(snapThinking, 100);
		} else {
			if (thinkingTimer) clearInterval(thinkingTimer);
			thinkingTimer = null;
			snapThinking();
			thinkingStart.value = null;
			thinkingForId.value = null;
		}
	});
	onUnmounted(() => {
		if (thinkingTimer) clearInterval(thinkingTimer);
	});

	return { thinkSecs, thinkingTimes };
}
