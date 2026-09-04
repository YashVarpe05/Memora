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

/**
 * Fired when the laptop stops recognising this device's token.
 *
 * Holding a token is not the same as being paired, and the app treated them as the same
 * thing. When the API restarted its in-memory pairing store emptied; the phone still had
 * a token, `pairedServer()` still returned it, so the guard saw a paired device, `/pair`
 * was not in the nav, and there was no route back to the scanner at all. A stale pairing
 * looked exactly like a working one until every request failed.
 */
const PAIRING_LOST = 'memora:pairing-lost';

export function onPairingLost(listener: () => void): () => void {
  window.addEventListener(PAIRING_LOST, listener);
  return () => window.removeEventListener(PAIRING_LOST, listener);
}

/**
 * Every API call goes through here, so the token cannot be forgotten on one of them —
 * and a rejected token is noticed wherever it happens rather than only where someone
 * remembered to check.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const paired = pairedServer();
  const headers = new Headers(init.headers);
  if (paired) headers.set('Authorization', `Bearer ${paired.token}`);

  const response = await fetch(resolve(path), { ...init, headers });

  // 401 while holding a token means the laptop has forgotten this device. Drop the
  // pairing so the app stops pretending, and announce it so the UI can send the user
  // back to the QR instead of stranding them on a screen with no way forward.
  if (paired && response.status === 401) {
    clearPairing();
    window.dispatchEvent(new Event(PAIRING_LOST));
  }
  return response;
}

/**
 * Is the stored pairing still accepted?
 *
 * Called once at launch. Without it a phone holding a dead token sits on the search
 * screen looking normal until the user tries something, and the first thing they try
 * fails for reasons the screen does not explain.
 */
export async function verifyPairing(): Promise<boolean> {
  if (!pairedServer()) return false;
  try {
    const response = await apiFetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'ping', limit: 1, stage1: false }),
    });
    return response.status !== 401;
  } catch {
    // Unreachable is not unpaired. The laptop may simply be asleep, and throwing the
    // pairing away for a network blip would force a needless re-scan.
    return true;
  }
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
