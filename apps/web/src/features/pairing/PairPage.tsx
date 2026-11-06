import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Routes } from '@memora/core';
import { Button } from '@/components/ui/button';
import { clearPairing, isNative, pairedServer, savePairing } from '@/platform/api';
import { claim, PairScanScreen } from './PairScanScreen';

export function PairPage() {
  const navigate = useNavigate();
  const [paired, setPaired] = useState(pairedServer);
  const [url, setUrl] = useState(import.meta.env.VITE_API_URL || (isNative() ? '' : `${location.origin}/api`));
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function connect(local = false) {
    setBusy(true); setError(null);
    try {
      const address = new URL(url.trim());
      const host = address.hostname;
      const localHost = ['localhost', '127.0.0.1', '[::1]'].includes(host);
      if (address.protocol !== 'https:' && !(address.protocol === 'http:' && localHost)) {
        throw new Error('Use an HTTPS server address for online processing.');
      }
      if (address.username || address.password || address.search || address.hash) throw new Error('Enter a server URL without credentials, query or fragment.');
      const base = address.href.replace(/\/$/, '');
      let invitation = code.trim();
      if (local && localHost) {
        const response = await fetch(`${base}/pair/start`, { method: 'POST' });
        if (!response.ok) throw new Error('This server requires an invitation from its operator.');
        invitation = ((await response.json()) as { code: string }).code;
      }
      const result = await claim({ url: base, code: invitation });
      if (!result.ok) throw new Error('Could not connect. Check the server address and use a fresh invitation code.');
      savePairing({ url: base, token: result.token });
      navigate(Routes.Scan, { replace: true });
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not connect.'); }
    finally { setBusy(false); }
  }
  if (paired) return <div className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
    <h1 className="text-xl font-semibold">This device is connected</h1>
    <p className="break-all text-sm">{paired.url}</p>
    <p className="text-sm text-ink-muted">This credential opens only this device’s library. Disconnecting does not erase stored documents. A new invitation creates a new library.</p>
    <Button variant="subtle" onClick={() => { clearPairing(); setPaired(null); }}>Disconnect</Button>
  </div>;
  return <div className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
    <h1 className="text-xl font-semibold">Connect this device</h1>
    <p className="text-sm text-ink-muted">{!isNative() && ['localhost', '127.0.0.1'].includes(location.hostname)
      ? 'For this local trial, connect to the development server below. Keep the server running while you test.'
      : 'Use your online Memora server and a single-use invitation from its operator. Your laptop does not need to stay on.'}</p>
    <label className="flex flex-col gap-1 text-sm">Server address
      <input className="rounded border border-line bg-surface p-3" type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://memora.example.com/api" />
    </label>
    <label className="flex flex-col gap-1 text-sm">Invitation code
      <input className="rounded border border-line bg-surface p-3" value={code} autoComplete="off" onChange={e => setCode(e.target.value)} />
    </label>
    <Button disabled={busy || !url || !code} onClick={() => void connect()}>Connect</Button>
    {!isNative() && ['localhost', '127.0.0.1'].includes(location.hostname) &&
      <Button variant="subtle" disabled={busy} onClick={() => void connect(true)}>Connect to local development server</Button>}
    {error && <p role="alert" className="text-warn">{error}</p>}
    {isNative() && <PairScanScreen onPaired={() => navigate(Routes.Scan, { replace: true })} />}
  </div>;
}
