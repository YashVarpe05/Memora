import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Routes } from '@memora/core';

import { clearPairing, pairedServer } from '@/platform/api';

import { PairQrPanel } from './PairQrPanel';
import { PairScanScreen } from './PairScanScreen';

/**
 * One route, two sides.
 *
 * A native build shows the scanner; a browser shows the QR. The check is capability-based
 * rather than a platform sniff: if this build can talk to Capacitor, it is the phone.
 */
function isNative(): boolean {
  return Boolean((window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor
    ?.isNativePlatform?.());
}

export function PairPage() {
  const navigate = useNavigate();
  const [paired, setPaired] = useState(() => pairedServer());

  if (isNative() && !paired) {
    return <PairScanScreen onPaired={() => navigate(Routes.Search, { replace: true })} />;
  }

  if (paired) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-8">
        <h1 className="text-xl font-semibold tracking-tight">Connected</h1>
        <p className="text-sm text-ink-muted">
          Paired with <code className="rounded bg-surface-sunken px-1.5 py-0.5 text-xs">
            {paired.url}
          </code>
        </p>
        <button
          type="button"
          className="self-start text-sm text-warn underline"
          onClick={() => {
            clearPairing();
            setPaired(null);
          }}
        >
          Disconnect
        </button>
      </div>
    );
  }

  return <PairQrPanel />;
}
