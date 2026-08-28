/**
 * Capacitor configuration.
 *
 * UNVERIFIED ON DEVICE. Written without an Android SDK or a phone available. Nothing here
 * has been built into an APK or run. See `docs/ANDROID-SETUP.md` for what to check first.
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
