// Shared auth helpers: role check + login error mapping (pure — no Vue reactivity).

export function isAdminUser(u: any): boolean {
	return !!u && (u.role === "admin" || u.is_superuser);
}

function httpStatus(err: unknown): number | undefined {
	return (err as any)?.response?.status ?? (err as any)?.statusCode ?? (err as any)?.status;
}

export function userAuthError(err: unknown, storeMessage: string, isRegister: boolean): string {
	const status = httpStatus(err);
	if (status === 400) return isRegister ? "Email already registered." : "Invalid data. Check email/password.";
	if (status === 401) return "Incorrect email or password.";
	if (status === 422) return (err as any)?.response?.data?.detail?.[0]?.msg ?? "Invalid input.";
	if (status === 429) return "Too many attempts. Wait a moment.";
	if (status && status >= 500) return "Server error. Try again shortly.";
	if (storeMessage) return storeMessage;
	return "Something went wrong. Try again.";
}

export function adminAuthError(err: unknown, storeMessage: string): string {
	const status = httpStatus(err);
	if (status === 401 || status === 400) return "Incorrect email or password. Please try again.";
	if (status === 403) return "Your account does not have access. Contact an administrator.";
	if (status === 429) return "Too many attempts. Please wait a moment before trying again.";
	if (status && status >= 500) return "Something went wrong on our end. Please try again shortly.";
	// Offline / network failure (no response at all)
	if (((err as any)?.name === "FetchError" && !status) || (typeof navigator !== "undefined" && !navigator.onLine)) {
		return "Unable to reach the server. Check your internet connection and try again.";
	}
	if (storeMessage) return storeMessage;
	return "We couldn't sign you in. Please check your details and try again.";
}
