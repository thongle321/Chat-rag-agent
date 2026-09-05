// Single source of truth for route access: deny-list, not allow-list.
// Only /admin and /admin/... is gated (/admin/login itself is public);
// everything else (/, /c/:id, /uc/:id, /login, /administrator, 404s,
// future public pages) is public and needs no edits here.
// Consumed by main.ts router guard, the axios interceptor, and streamChat.

// Backend contract — 403 detail strings from app/services/user_manager.py
// (require_admin / require_user). Update these if the backend rewords them.
export const ADMIN_ONLY_DETAIL = "Admin only";
export const ADMIN_NO_CHAT_DETAIL = "Admin cannot access";

export function isAdminPath(path: string): boolean {
	return path === "/admin" || path.startsWith("/admin/");
}

export function isPublicPath(path: string): boolean {
	if (isAdminPath(path)) return path.startsWith("/admin/login");
	return true;
}

// Returns where to send the user after an HTTP error, or null to stay.
// Never points at the current page (no redirect loops).
export function redirectForStatus(status: number | undefined, detail: string, path: string): string | null {
	if (status === 401) {
		if (isPublicPath(path)) return null;
		const target = isAdminPath(path) ? "/admin/login" : "/login";
		return path === target ? null : target;
	}
	if (status === 403) {
		if (detail.includes(ADMIN_NO_CHAT_DETAIL)) {
			// Admin tried to use user chat — keep token (still admin)
			return isAdminPath(path) ? null : "/admin/";
		}
		if (detail.includes(ADMIN_ONLY_DETAIL)) {
			// Non-admin hit an admin API
			return path.startsWith("/login") ? null : "/login";
		}
	}
	return null;
}
