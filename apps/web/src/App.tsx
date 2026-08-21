import { Navigate, Route, Routes as RouterRoutes } from 'react-router-dom';

import { Routes } from '@memora/core';

import { AppShell } from '@/components/AppShell';
import {
  AskPage,
  CapturePage,
  MemoryPage,
  SettingsPage,
  TimelinePage,
} from '@/routes/pages';

export default function App() {
  return (
    <RouterRoutes>
      <Route element={<AppShell />}>
        <Route path={Routes.Home} element={<Navigate to={Routes.Ask} replace />} />
        <Route path={Routes.Ask} element={<AskPage />} />
        <Route path={Routes.Capture} element={<CapturePage />} />
        <Route path={Routes.Timeline} element={<TimelinePage />} />
        <Route path={Routes.Settings} element={<SettingsPage />} />
        <Route path="/memory/:id" element={<MemoryPage />} />
        <Route path="*" element={<Navigate to={Routes.Ask} replace />} />
      </Route>
    </RouterRoutes>
  );
}
