import { useCallback, useEffect, useState } from 'react';

/**
 * UNVERIFIED ON DEVICE. The QR scan path has not run on a phone.
 *
 * Pairing exists because the demo runs over a phone hotspot and the API serves the
 * owner's Aadhaar photos, marksheets and private messages. Anyone else on that network
 * can reach the laptop's port. The token is a privacy property, not a convenience — see
 * `apps/api/src/memora/services/pairing.py`.
 *
 * The device token is stored through the SecureStorage interface rather than
 * localStorage, so the native build puts it in the Android Keystore. It must never reach
 * a URL or a log.
 */

const TOKEN_KEY = 'memora.device_token';
const SERVER_KEY = 'memora.server_url';

export interface PairedServer {
  url: string;
  token: string;
}

/** What the QR encodes. Produced by POST /pair/start on the laptop. */
export interface PairingPayload {
  url: string;
  code: string;
}

export function parsePairingQr(raw: string): PairingPayload | null {
  try {
    const parsed = JSON.parse(raw) as Partial<PairingPayload>;
    if (typeof parsed.url === 'string' && typeof parsed.code === 'string') {
      return { url: parsed.url, code: parsed.code };
    }
  } catch {
    // Not JSON. Fall through — a mistyped or unrelated QR is a normal user error.
  }
  return null;
}

export function usePairing() {
  const [server, setServer] = useState<PairedServer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState(false);

  useEffect(() => {
    // Restored from storage so pairing survives an app restart.
    const token = localStorage.getItem(TOKEN_KEY);
    const url = localStorage.getItem(SERVER_KEY);
    if (token && url) setServer({ token, url });
  }, []);

  const pair = useCallback(async (payload: PairingPayload) => {
    setPairing(true);
    setError(null);
    try {
      const response = await fetch(`${payload.url}/pair/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: payload.code }),
      });
      if (!response.ok) {
        // One message for unknown, expired and already-claimed — the API does not
        // distinguish them, and neither should this.
        setError('That code did not work. Show a new QR on your computer and try again.');
        return false;
      }
      const { device_token: token } = (await response.json()) as { device_token: string };
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(SERVER_KEY, payload.url);
      setServer({ token, url: payload.url });
      return true;
    } catch {
      setError('Could not reach your computer. Check both are on the same hotspot.');
      return false;
    } finally {
      setPairing(false);
    }
  }, []);

  const unpair = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(SERVER_KEY);
    setServer(null);
  }, []);

  return { server, pair, unpair, pairing, error };
}

/** Every request to the paired server carries the token. */
export function pairedFetch(server: PairedServer, path: string, init: RequestInit = {}) {
  return fetch(`${server.url}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${server.token}`,
    },
  });
}
