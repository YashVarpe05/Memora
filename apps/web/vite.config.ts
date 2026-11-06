import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // No injected <script src="/registerSW.js">. That tag is unconditional, and
      // `cap sync` copies this same index.html into the APK - so the native build
      // registered a service worker that then served a stale bundle after every
      // reinstall. src/platform/serviceWorker.ts registers it for browsers only.
      injectRegister: null,
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Memora AI',
        short_name: 'Memora',
        description: 'Ask your memory a human question. Get an answer with proof.',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // Never cache API responses — memories are per-user and must not be
        // served from a shared cache.
        navigateFallbackDenylist: [/^\/api/, /^\/health/],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
      '@memora/core': path.resolve(import.meta.dirname, '../../packages/core/src'),
    },
  },
  server: {
    // No `host`. Deliberate: the dev server must stay on loopback.
    //
    // Exposing it (`vite --host`) would let a phone on the hotspot load the UI and reach
    // the API through this proxy - and because the proxy makes that call from the laptop,
    // every request would arrive at the API as 127.0.0.1 and be waved through as the
    // owner sitting at the machine. That launders an unpaired device into an exempt one
    // and defeats pairing completely, without touching a line of API code. The phone gets
    // in through the Capacitor app and a device token, never through this port.
    port: 5173,
    watch: { ignored: ['**/android/**', '**/test-results/**', '**/playwright-report/**'] },
    proxy: {
      // The API mounts its routers at the root, so the /api prefix is a dev-server
      // convention only and has to be stripped. Without the rewrite every call 404s.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
    },
  },
});
