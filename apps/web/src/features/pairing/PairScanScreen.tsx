import { Camera, Laptop } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/button';
import { savePairing } from '@/platform/api';

/**
 * The phone half of pairing: scan the QR, exchange the code for a device token, store both
 * the token and the URL the QR carried.
 *
 * The URL matters as much as the code. Without it the app has no idea where the laptop is,
 * and a relative path makes the phone call itself — which was the original blocker.
 *
 * Verified on device 2026-09-03 (Galaxy S23 FE, Android 16): scan, claim, and a token-
 * carrying search all succeed.
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

/**
 * Why a claim failed, to the precision the platform actually allows.
 *
 * - `refused`  — the server answered and said no. The status is the evidence.
 * - `blocked`  — the server answered a probe, so it is reachable, but the claim itself
 *                never completed. Configuration, not network.
 * - `unreachable` — nothing answered at all.
 */
export type ClaimFailure =
  | { kind: 'refused'; status: number }
  | { kind: 'blocked' }
  | { kind: 'unreachable' };

export type ClaimResult = { ok: true; token: string } | { ok: false; failure: ClaimFailure };

/**
 * Did anything at all answer at this address?
 *
 * `mode: 'no-cors'` is the whole point. A cross-origin `fetch` throws an identical
 * TypeError whether the host was unreachable or the response was withheld by CORS — the
 * browser hides the difference on purpose, so the error object cannot tell them apart. A
 * no-cors GET carries no custom headers, is therefore never preflighted, and resolves
 * (opaquely) whenever bytes came back. It throws only when nothing answered.
 *
 * So this distinguishes "the network is broken" from "the server refused to talk to this
 * origin" — which is precisely the distinction that cost an afternoon when the app
 * asserted the first and the truth was the second.
 */
async function serverAnswers(url: string): Promise<boolean> {
  try {
    await fetch(`${url}/health`, { method: 'GET', mode: 'no-cors' });
    return true;
  } catch {
    return false;
  }
}

/** Exchange the code for a device token against the URL the QR carried. */
export async function claim(payload: PairingPayload): Promise<ClaimResult> {
  let response: Response;
  try {
    response = await fetch(`${payload.url}/pair/claim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: payload.code }),
    });
  } catch {
    // Nothing here knows why yet. Ask the network a question it can answer.
    const reachable = await serverAnswers(payload.url);
    return { ok: false, failure: { kind: reachable ? 'blocked' : 'unreachable' } };
  }

  if (!response.ok) {
    return { ok: false, failure: { kind: 'refused', status: response.status } };
  }

  const { device_token: token } = (await response.json()) as { device_token: string };
  return { ok: true, token };
}

/**
 * What to tell the user, saying only what was established.
 *
 * The previous single message named a cause — "check both are on the same hotspot" — for
 * a failure whose cause it had not determined. It was wrong, confidently, and sent the
 * debugging to the network while the phone had been reaching the laptop on every attempt.
 * Each branch below reports what happened; only `unreachable` suggests the network,
 * because only there has the network actually been shown to be at fault.
 */
export function describeFailure(failure: ClaimFailure, url: string): string {
  switch (failure.kind) {
    case 'refused':
      // The API returns one status for unknown, expired and already-claimed, on purpose.
      return failure.status === 400
        ? 'Your computer rejected that code. It may have expired or already been used — show a new one.'
        : `Your computer answered with an error (${failure.status}). Nothing is wrong with the network.`;
    case 'blocked':
      return `${url} answered, so the network is fine — but it did not accept the pairing request. That is a setting on the computer, not a connection problem.`;
    case 'unreachable':
      return `Nothing answered at ${url}. Check the computer is on this phone's hotspot and Memora is running there.`;
  }
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

      const result = await claim(payload);
      if (!result.ok) {
        setError(describeFailure(result.failure, payload.url));
        return;
      }

      savePairing({ url: payload.url, token: result.token });
      onPaired();
    } catch (err) {
      // Reached only when the scanner itself failed — the camera, or a cancelled scan.
      // Network faults are handled above with evidence; this branch has none, so it must
      // not invent any.
      setError(
        err instanceof Error && err.message
          ? `The scanner stopped: ${err.message}`
          : 'The scanner stopped before reading a code.',
      );
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
