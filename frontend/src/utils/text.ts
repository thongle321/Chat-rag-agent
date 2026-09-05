// Pure text helpers for rendered chat messages (no Vue reactivity — plain utils).
export function stripInlineCitations(text: string): string {
	return text
		.replace(/\s*\[Source:[^\]]*\]/g, "")
		.replace(/\s*\[P(\d+)\]/g, "")
		.replace(/\s*\[(\d+)\]/g, "");
}
