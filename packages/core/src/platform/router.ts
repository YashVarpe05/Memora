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
  /** Layer one, and the product. You describe a document, you get the document. */
  Search: '/search',
  /** Laptop shows the QR here; the phone scans it here. */
  Pair: '/pair',
  Ask: '/ask',
  Capture: '/capture',
  Timeline: '/timeline',
  Memory: (id: string) => `/memory/${id}`,
  Settings: '/settings',
} as const;
