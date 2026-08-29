import { RefreshCw, Smartphone } from 'lucide-react';
import QRCode from 'qrcode';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { apiFetch } from '@/platform/api';

/**
 * The QR the laptop shows and the phone scans.
 *
 * **The QR carries the URL as well as the code**, because a hotspot hands out a different
 * address every session — a `.env` value or a build-time constant is stale by the next
 * demo. The address the server discovers from its own routing table is the only one that
 * can be right, so it travels with the code.
 *
 * Rendered on the laptop only. Loopback is exempt from pairing on the server, so this
 * screen reaches `/pair/start` without a token — which is also why the endpoint sits
 * outside the paired routers.
 */

interface Pairing {
  code: string;
  url: string;
  expires_at: string;
}

export function PairQrPanel() {
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState(0);

  const start = useCallback(async () => {
    setError(null);
    try {
      const response = await apiFetch('/api/pair/start', { method: 'POST' });
      if (!response.ok) throw new Error(String(response.status));
      const body = (await response.json()) as Pairing;
      setPairing(body);
      // The phone parses this JSON. Keep the shape in step with parsePairingQr.
      setDataUrl(
        await QRCode.toDataURL(JSON.stringify({ url: body.url, code: body.code }), {
          width: 320,
          margin: 1,
        }),
      );
    } catch {
      setError('Could not reach the API. Is it running with --host 0.0.0.0?');
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  useEffect(() => {
    const check = () =>
      apiFetch('/api/pair/status')
        .then((r) => (r.ok ? r.json() : null))
        .then((body) => setDevices(body?.devices_paired ?? 0))
        .catch(() => {});
    check();
    const timer = setInterval(check, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-5 px-4 py-8">
      <div className="flex flex-col items-center gap-1 text-center">
        <h1 className="text-xl font-semibold tracking-tight">Pair your phone</h1>
        <p className="text-sm text-ink-muted">
          Open Memora on your phone and scan this code. Both devices must be on the same
          hotspot.
        </p>
      </div>

      {error && <p className="text-sm text-warn">{error}</p>}

      {dataUrl && (
        <img
          src={dataUrl}
          alt="Pairing QR code"
          className="rounded-card border border-line bg-white p-3"
          width={320}
          height={320}
        />
      )}

      {pairing && (
        <div className="flex flex-col items-center gap-1 text-center">
          <code className="rounded bg-surface-sunken px-2 py-1 text-xs">{pairing.url}</code>
          {/* The code expires in five minutes: it is on a screen in a room, and it
              should stop working before the room empties. */}
          <span className="text-xs text-ink-faint">
            Expires at {new Date(pairing.expires_at).toLocaleTimeString()}
          </span>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button variant="subtle" onClick={() => void start()}>
          <RefreshCw className="size-4" aria-hidden /> New code
        </Button>
      </div>

      <p className="flex items-center gap-2 text-sm text-ink-muted">
        <Smartphone className="size-4" aria-hidden />
        {devices === 0
          ? 'No phone paired yet.'
          : `${devices} device${devices === 1 ? '' : 's'} paired.`}
      </p>
    </div>
  );
}
