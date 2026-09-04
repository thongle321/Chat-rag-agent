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
