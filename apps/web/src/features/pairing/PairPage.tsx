import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Routes } from '@memora/core';

import { clearPairing, isNative, pairedServer } from '@/platform/api';

import { PairQrPanel } from './PairQrPanel';
import { PairScanScreen } from './PairScanScreen';

/**
 * One route, two sides.
 *
 * A native build shows the scanner; a browser shows the QR. Nothing reaches this route on
 * the phone by itself, which is why App.tsx sends an unpaired native build here — the
 * scanner existing is not the same as the scanner being reachable, and it shipped once
 * with no way in.
 */

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
