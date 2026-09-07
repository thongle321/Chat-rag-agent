import { ref } from "vue";
import api, { getErrorMessage } from "../api/index.ts";

export const syncIntervalOptions = [
	{ label: "Every 1 minute", value: 1 },
	{ label: "Every 5 minutes", value: 5 },
	{ label: "Every 10 minutes", value: 10 },
	{ label: "Every 15 minutes (default)", value: 15 },
	{ label: "Every 30 minutes", value: 30 },
	{ label: "Every 1 hour", value: 60 },
	{ label: "Every 6 hours", value: 360 },
	{ label: "Every day", value: 1440 },
];

export interface ChannelHealth {
	ok: boolean;
	label?: string;
	error?: string;
}

// Shared list / health / sync / disconnect state machine for channel tabs
// (Facebook Messenger, Zalo Bot). Connect/update payloads differ per provider
// and stay with the provider forms; everything after save funnels through here.
export function useChannelCrud(basePath: string, healthName: (data: any) => string) {
	const toast = useToast();
	const items = ref<any[]>([]);
	const loading = ref(true);
	// Per-channel busy flag for Test/Sync buttons (only one runs at a time).
	const busyId = ref<string | null>(null);
	const disconnectTarget = ref<any | null>(null);
	const disconnectOpen = ref(false);
	const disconnecting = ref(false);

	async function load() {
		loading.value = true;
		try {
			const { data } = await api.get(basePath);
			items.value = Array.isArray(data) ? data : [];
		} catch {
			items.value = [];
		} finally {
			loading.value = false;
		}
	}

	async function checkHealth(ch: any): Promise<ChannelHealth> {
		busyId.value = ch.id;
		try {
			const { data } = await api.get(`${basePath}/${ch.id}/health`);
			const ok = !!data.ok;
			toast.add({
				color: ok ? "success" : "error",
				description: ok ? healthName(data) || "Reachable" : data.error,
				title: ok ? "Connection OK" : "Connection failed",
			});
			await load();
			return { ok, label: healthName(data), error: data.error };
		} catch (err: unknown) {
			toast.add({ color: "error", description: getErrorMessage(err), title: "Connection failed" });
			return { ok: false, error: getErrorMessage(err) };
		} finally {
			busyId.value = null;
		}
	}

	async function syncNow(ch: any, syncSuffix = "sync") {
		busyId.value = ch.id;
		try {
			const { data } = await api.post(`${basePath}/${ch.id}/${syncSuffix}`);
			toast.add({
				color: data.status === "success" ? "success" : "error",
				title: data.status === "success" ? "Synced" : "Sync error",
			});
			await load();
		} catch (err: unknown) {
			toast.add({ color: "error", description: getErrorMessage(err), title: "Sync failed" });
		} finally {
			busyId.value = null;
		}
	}

	function confirmDisconnect(ch: any) {
		disconnectTarget.value = ch;
		disconnectOpen.value = true;
	}

	async function handleDisconnect() {
		if (!disconnectTarget.value) return;
		disconnecting.value = true;
		try {
			await api.delete(`${basePath}/${disconnectTarget.value.id}`);
			await load();
			disconnectOpen.value = false;
			disconnectTarget.value = null;
			toast.add({ color: "success", title: "Disconnected" });
		} catch (err: unknown) {
			toast.add({ color: "error", description: getErrorMessage(err), title: "Disconnect failed" });
		} finally {
			disconnecting.value = false;
		}
	}

	return {
		busyId,
		checkHealth,
		confirmDisconnect,
		disconnectOpen,
		disconnectTarget,
		disconnecting,
		handleDisconnect,
		items,
		load,
		loading,
		syncNow,
	};
}
