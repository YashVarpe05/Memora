import { useEffect, useState } from 'react';
import { Navigate, Outlet, Route, Routes as RouterRoutes, useLocation } from 'react-router-dom';

import { Routes } from '@memora/core';

import { AppShell } from '@/components/AppShell';
import { PairPage } from '@/features/pairing/PairPage';
import { ScanPage } from '@/features/scan/ScanPage';
import { SearchView } from '@/features/search/SearchView';
import { isNative, onPairingLost, pairedServer, verifyPairing } from '@/platform/api';
import {
  AskPage,
  CapturePage,
  MemoryPage,
  SettingsPage,
  TimelinePage,
} from '@/routes/pages';

/**
 * An unpaired phone has exactly one thing it can usefully do: pair.
 *
 * Without this the app launched on the search screen, every request resolved against the
 * WebView's own origin because there was no paired base, and the scanner sat behind a
 * route with no link to it, no tab, and no redirect. The screen existed and was
 * unreachable — which is indistinguishable, from the user's side, from not being built.
 *
 * Browser-only builds are untouched: `isNative()` is false there, so the laptop keeps
 * landing on search with no pairing step, exactly as it does today.
 */
function RequirePairing() {
  const { pathname } = useLocation();
  // Bumped when the pairing is dropped, so this re-reads storage and redirects. Without
  // it the token can be cleared underneath a screen that keeps rendering as if paired.
  const [, bump] = useState(0);

  useEffect(() => onPairingLost(() => bump((n) => n + 1)), []);

  // A token the laptop no longer accepts is worse than no token: the app looks connected,
  // offers no way to re-pair, and fails at whatever the user tries first. One cheap call
  // at launch settles it, and a 401 anywhere clears the pairing through apiFetch.
  useEffect(() => {
    if (isNative() && pairedServer()) void verifyPairing();
  }, []);

  if (isNative() && !pairedServer() && pathname !== Routes.Pair) {
    return <Navigate to={Routes.Pair} replace />;
  }
  return <Outlet />;
}

export default function App() {
  return (
    <RouterRoutes>
      <Route element={<RequirePairing />}>
        <Route element={<AppShell />}>
          {/* Search is the product: layer one, the answer is the file. */}
          <Route path={Routes.Home} element={<Navigate to={Routes.Search} replace />} />
          <Route path={Routes.Search} element={<SearchView />} />
          <Route path={Routes.Pair} element={<PairPage />} />
          <Route path={Routes.Scan} element={<ScanPage />} />
          <Route path={Routes.Ask} element={<AskPage />} />
          <Route path={Routes.Capture} element={<CapturePage />} />
          <Route path={Routes.Timeline} element={<TimelinePage />} />
          <Route path={Routes.Settings} element={<SettingsPage />} />
          <Route path="/memory/:id" element={<MemoryPage />} />
          <Route path="*" element={<Navigate to={Routes.Search} replace />} />
        </Route>
      </Route>
    </RouterRoutes>
  );
}
