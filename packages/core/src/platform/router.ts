/**
 * Navigation. Components dispatch route intents; they never touch history or
 * window.location directly.
 */
export interface Navigator {
  navigate(path: string, options?: { replace?: boolean }): void;
  back(): void;
  currentPath(): string;
}

export const Routes = {
  Home: '/',
  Ask: '/ask',
  Capture: '/capture',
  Timeline: '/timeline',
  Memory: (id: string) => `/memory/${id}`,
  Settings: '/settings',
} as const;
