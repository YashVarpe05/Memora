import { isNative, pairedServer } from './api';

/**
 * Local mode: the phone indexes and searches by itself, with no server and no setup.
 *
 * It is the default for an APK built without a server address. A build that carries a server
 * address keeps the connected behaviour (zero-touch enrollment), and a phone that has been
 * paired by hand stays connected.
 */
export function isLocalMode(): boolean {
  return isNative() && !import.meta.env.VITE_MEMORA_SERVER?.trim() && !pairedServer();
}

const CONSENT = 'memora.local-consent';

export function localConsent(): boolean {
  try { return localStorage.getItem(CONSENT) === 'yes'; } catch { return false; }
}

export function setLocalConsent(on: boolean): void {
  try { if (on) localStorage.setItem(CONSENT, 'yes'); else localStorage.removeItem(CONSENT); } catch { /* storage blocked */ }
}
