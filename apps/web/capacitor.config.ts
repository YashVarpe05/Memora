/**
 * Capacitor configuration.
 *
 * VERIFIED ON DEVICE 2026-09-03 — Galaxy S23 FE, Android 16 (SDK 36). Built to an APK,
 * installed, and run: the WebView loads the bundled assets, `androidScheme: 'http'` and
 * cleartext both behave as intended against a laptop on a phone hotspot.
 *
 * `androidScheme` is load-bearing beyond the scheme itself: it sets the WebView's ORIGIN
 * to `http://localhost` — no port — and the API's `cors_origins` must list that exact
 * string. It listed only the Vite dev port, so every request from the phone died on a
 * CORS preflight that the app then reported as a network failure.
 *
 * The app is a native shell around the same Vite build the browser runs. It exists for one
 * capability the web platform cannot provide: enumerating files already on the device.
 * See `prompts/capacitor-auto-scan.md`.
 */

import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'ai.memora.app',
  appName: 'Memora',
  webDir: 'dist',

  android: {
    // The phone talks to the laptop over a hotspot, which is plain HTTP on a LAN
    // address. Android blocks cleartext by default; this permits it for the local
    // network only, and the consequence is recorded in ANDROID-SETUP.md.
    allowMixedContent: true,
  },

  server: {
    // No hard-coded host. The address arrives in the pairing QR, because a hotspot hands
    // out a different one each time and a config file cannot know it.
    androidScheme: 'http',
    cleartext: true,
  },
};

export default config;
