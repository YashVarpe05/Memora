/**
 * Where the API is, resolved at runtime.
 *
 * **No build-time constant and no `.env` value**, because a phone hotspot hands out a
 * different address every session — anything baked in is stale by the next demo. The
 * address arrives in the pairing QR and is stored beside the device token.
 *
 * **The browser path is unchanged.** With no pairing stored, `base()` returns `''`, so
 * every call stays a relative `/api/...` that Vite's dev proxy rewrites exactly as before.
 * Loopback is already exempt from pairing on the server, so the laptop demo needs no
 * token and behaves identically. That is deliberate: the phone build must not be enabled
 * by breaking the one that works.
 *
 * This was the blocker. In a Capacitor WebView there is no dev proxy, so `/api/search`
 * resolved against the app's own origin and the phone called itself — a search that
 * failed with nothing to act on.
 */

const TOKEN_KEY = 'memora.device_token';
const SERVER_KEY = 'memora.server_url';

export interface Paired {
  url: string;
  token: string;
}

/**
 * Is this the phone build?
 *
 * Capability-based rather than a user-agent sniff: if this build can reach Capacitor, it
 * is running inside the native shell. Lives here because two callers need it and a second
 * private copy would be free to drift from the first.
 */
export function isNative(): boolean {
  return Boolean(
    (window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor
      ?.isNativePlatform?.(),
  );
}

export function pairedServer(): Paired | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const url = localStorage.getItem(SERVER_KEY);
    return token && url ? { token, url } : null;
  } catch {
    // Private mode, or storage blocked. Fall back to the relative path.
    return null;
  }
}

export function savePairing(paired: Paired): void {
  localStorage.setItem(TOKEN_KEY, paired.token);
  localStorage.setItem(SERVER_KEY, paired.url);
}

export function clearPairing(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(SERVER_KEY);
}

/**
 * The prefix for an API path.
 *
 * Empty in the browser — `/api/search` stays relative and the proxy handles it. On a
 * paired device it is the laptop's LAN address, and `/api` is dropped because the server
 * mounts its routers at the root; the `/api` prefix is a dev-proxy convention only.
 */
export function base(): string {
  const paired = pairedServer();
  return paired ? paired.url : '';
}

function resolve(path: string): string {
  const paired = pairedServer();
  if (!paired) return path;
  return `${paired.url}${path.replace(/^\/api/, '')}`;
}

/** Every API call goes through here, so the token cannot be forgotten on one of them. */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const paired = pairedServer();
  const headers = new Headers(init.headers);
  if (paired) headers.set('Authorization', `Bearer ${paired.token}`);
  return fetch(resolve(path), { ...init, headers });
}

/**
 * A blob URL for a media path, fetched with the token attached.
 *
 * `<img src>` and `<object data>` cannot carry an Authorization header, and putting the
 * token in a query string would write it into every access log — the one thing the
 * pairing design says must never happen. So the bytes are fetched properly and handed to
 * the element as an object URL.
 *
 * Callers must revoke the returned URL when done, or the blob leaks for the page's life.
 */
export async function authedObjectUrl(path: string): Promise<string> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`${response.status} for ${path}`);
  return URL.createObjectURL(await response.blob());
}
