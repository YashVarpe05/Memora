import { Camera, Laptop } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/button';
import { savePairing } from '@/platform/api';

/**
 * UNVERIFIED ON DEVICE. The camera path has not run on a phone.
 *
 * The phone half of pairing: scan the QR, exchange the code for a device token, store
 * both the token and the URL the QR carried.
 *
 * The URL matters as much as the code. Without it the app has no idea where the laptop
 * is, and a relative path makes the phone call itself — which was the actual blocker.
 */

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
    // Not JSON — a mistyped or unrelated QR. A normal user error, not an exception.
  }
  return null;
}

/** Exchange the code for a device token against the URL the QR carried. */
export async function claim(payload: PairingPayload): Promise<string | null> {
  const response = await fetch(`${payload.url}/pair/claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: payload.code }),
  });
  if (!response.ok) return null;
  const { device_token: token } = (await response.json()) as { device_token: string };
  return token;
}

export function PairScanScreen({ onPaired }: { onPaired: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const scan = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const { BarcodeScanner } = await import('@capacitor-mlkit/barcode-scanning');

      const permission = await BarcodeScanner.requestPermissions();
      if (permission.camera !== 'granted' && permission.camera !== 'limited') {
        setError('Camera access is needed to scan the code.');
        return;
      }

      const { barcodes } = await BarcodeScanner.scan();
      const raw = barcodes[0]?.rawValue;
      if (!raw) {
        setError('No code was read. Try again.');
        return;
      }

      const payload = parsePairingQr(raw);
      if (!payload) {
        setError('That is not a Memora pairing code.');
        return;
      }

      const token = await claim(payload);
      if (!token) {
        // One message for unknown, expired and already-claimed: the API does not
        // distinguish them, and neither should this.
        setError('That code did not work. Show a new one on your computer.');
        return;
      }

      savePairing({ url: payload.url, token });
      onPaired();
    } catch {
      setError('Could not reach your computer. Check both are on the same hotspot.');
    } finally {
      setBusy(false);
    }
  }, [onPaired]);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Connect to your computer</h1>
        <p className="text-sm text-ink-muted">
          Memora searches documents held on your own computer. Open Memora there, and scan
          the code it shows.
        </p>
      </div>

      <div className="flex items-start gap-3 rounded-card border border-line bg-surface p-3">
        <Laptop className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
        <span className="text-sm leading-relaxed text-ink-muted">
          Both devices need to be on the same network. The simplest way is to turn on this
          phone's hotspot and connect the computer to it.
        </span>
      </div>

      {error && <p className="text-sm text-warn">{error}</p>}

      <Button onClick={() => void scan()} disabled={busy} className="min-h-12">
        <Camera className="size-4" aria-hidden /> {busy ? 'Scanning…' : 'Scan the code'}
      </Button>
    </div>
  );
}
