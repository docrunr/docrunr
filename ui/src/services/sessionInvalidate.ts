/** Bridges 401 responses from worker API calls back into auth context (no React imports). */

type Handler = () => void;

let handler: Handler | null = null;

export function registerSessionUnauthorizedHandler(fn: Handler | null): void {
  handler = fn;
}

export function notifySessionUnauthorized(): void {
  handler?.();
}
