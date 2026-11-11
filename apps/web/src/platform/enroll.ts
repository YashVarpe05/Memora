/**
 * Zero-touch enrollment: a phone built for one owner's server joins it by itself.
 *
 * The APK is built with the server address and an enrollment secret
 * (VITE_MEMORA_SERVER, VITE_MEMORA_ENROLL_SECRET). On first launch the app trades the secret
 * for a device token and a new, empty library, with no invitation code, QR or typing. The
 * secret is inside the APK, so the APK is a personal build: whoever holds it can enroll an
 * empty library, and nobody can read another device's. See prompts/zero-touch-enrollment.md.
 */

export interface EnrollConfig {
  /** The API base, e.g. https://memora.example.com/api */
  server: string;
  secret: string;
}

export type EnrollResult =
  | { ok: true; url: string; token: string }
  | { ok: false; reason: 'blocked' | 'unreachable' | 'rejected' | 'locked' | 'disabled' };

export function enrollConfig(env: Record<string, string | undefined> = import.meta.env): EnrollConfig | null {
  const server = env.VITE_MEMORA_SERVER?.trim();
  const secret = env.VITE_MEMORA_ENROLL_SECRET?.trim();
  return server && secret ? { server, secret } : null;
}

const LOCAL = ['localhost', '127.0.0.1', '[::1]'];

export async function enrollDevice(
  config: EnrollConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<EnrollResult> {
  let base: string;
  try {
    const address = new URL(config.server);
    const local = LOCAL.includes(address.hostname);
    // The token and the extracted text travel to this server, so it must be HTTPS.
    if (address.username || address.password || address.search || address.hash
      || (address.protocol !== 'https:' && !(address.protocol === 'http:' && local))) {
      return { ok: false, reason: 'blocked' };
    }
    base = address.href.replace(/\/$/, '');
  } catch {
    return { ok: false, reason: 'blocked' };
  }
  let response: Response;
  try {
    response = await fetchImpl(`${base}/pair/enroll`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret: config.secret }),
    });
  } catch {
    return { ok: false, reason: 'unreachable' };
  }
  if (response.status === 404) return { ok: false, reason: 'disabled' };
  if (response.status === 429) return { ok: false, reason: 'locked' };
  if (!response.ok) return { ok: false, reason: 'rejected' };
  const body = await response.json().catch(() => null) as { device_token?: string } | null;
  return body?.device_token ? { ok: true, url: base, token: body.device_token } : { ok: false, reason: 'rejected' };
}

/** Why the last automatic attempt failed, so the manual connect page can say so. */
export let lastEnrollFailure: string | null = null;
export function recordEnrollFailure(reason: string | null): void {
  lastEnrollFailure = reason;
}
