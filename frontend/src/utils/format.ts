// Shared display formatters (pure — no Vue reactivity).

export function formatDateTime(v: string | null | undefined): string {
	if (!v) return "—";
	const iso = v.includes("T") ? v : `${v.replace(" ", "T")}Z`;
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return v;
	return d.toLocaleString();
}

export function formatDateTimeDMY(v: string | null | undefined): string {
	if (!v) return "—";
	const iso = v.includes("T") ? v : `${v.replace(" ", "T")}Z`;
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return v;
	const dd = String(d.getDate()).padStart(2, "0");
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const hh = String(d.getHours()).padStart(2, "0");
	const mi = String(d.getMinutes()).padStart(2, "0");
	return `${dd}/${mm}/${d.getFullYear()} ${hh}:${mi}`;
}

export function formatSize(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatSyncInterval(v: number): string {
	if (!v) return "5 minutes";
	if (v < 60) return `${v} min`;
	if (v < 1440) return `${v / 60} h`;
	return `${v / 1440} day`;
}

// Whole-dollar USD display ("$399"); other currencies fall back to "N CODE".
export function formatUSD(price: number | null | undefined, currency?: string | null): string {
	if (price == null) return "—";
	if ((currency || "USD").toUpperCase() === "USD") {
		return new Intl.NumberFormat("en-US", {
			style: "currency",
			currency: "USD",
			minimumFractionDigits: 0,
			maximumFractionDigits: 0,
		}).format(price);
	}
	return `${price.toLocaleString("en-US")} ${(currency || "").toUpperCase()}`;
}
