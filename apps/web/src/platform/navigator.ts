import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import type { Navigator } from '@memora/core';

/**
 * Web implementation of the core Navigator interface.
 *
 * Components dispatch route intents through this; they never touch history or
 * window.location. A Capacitor build swaps this file and nothing else.
 */
export function useNavigator(): Navigator {
  const navigate = useNavigate();
  const location = useLocation();

  return useMemo<Navigator>(
    () => ({
      navigate: (path, options) => navigate(path, { replace: options?.replace ?? false }),
      back: () => navigate(-1),
      currentPath: () => location.pathname,
    }),
    [navigate, location.pathname],
  );
}
