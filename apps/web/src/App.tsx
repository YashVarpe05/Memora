import { Navigate, Outlet, Route, Routes as RouterRoutes, useLocation } from 'react-router-dom';

import { Routes } from '@memora/core';

import { AppShell } from '@/components/AppShell';
import { PairPage } from '@/features/pairing/PairPage';
import { SearchView } from '@/features/search/SearchView';
import { isNative, pairedServer } from '@/platform/api';
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
