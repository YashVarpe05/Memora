import { isNative } from '@/platform/api';

/**
 * The service worker belongs to the browser PWA, and must never run in the native shell.
 *
 * One `dist/` serves both: `cap sync` copies the exact build the browser loads into the
 * APK. So the registration decision has to be made at RUNTIME — a build-time flag would
 * mean two builds of the same code, and the wrong one would eventually be shipped.
 *
 * **Why it must not run natively.** The WebView loads the app from `http://localhost`,
 * where the service worker precaches the app shell and serves it first. Installing a new
 * APK replaces the files on disk but not the cache, so the phone keeps rendering the
 * previous build — indefinitely, and silently. That happened: a scan feature was provably
 * inside the APK, verified string by string, while the phone showed a version without it.
 * The bug is invisible because everything reports success; only the screen disagrees.
 *
 * Offline support is also pointless here. The PWA caches an app shell that is useless
 * without the laptop, since every document lives there. The native build needs the
 * network to do anything at all.
 */

/**
 * Remove any service worker and its caches.
 *
 * Not registering is NOT enough on a device that already registered one: an installed
 * worker survives the app being replaced, and would keep serving its cache forever. This
 * is the migration path for every phone that already has the old worker on it, and it
 * must stay in place rather than being deleted once the current devices are fixed.
 */
async function evict(): Promise<void> {
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));

    if ('caches' in window) {
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));
    }

    // A worker only stops controlling the page once it is gone AND the page reloads.
    // Without this the eviction takes effect on the next launch rather than this one,
    // which looks exactly like the fix not working.
    if (registrations.length > 0) window.location.reload();
  } catch {
    // Storage or SW access blocked. The app still works; it just keeps a stale cache.
  }
}

export function installServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;

  if (isNative()) {
    void evict();
    return;
  }

  // Registered by hand rather than by the plugin's injected script, because that script
  // is unconditional and lands in the APK's index.html too. `injectRegister: null` in
  // vite.config.ts turns it off; this is its replacement for the browser.
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => {
      // No offline support this session. Not worth surfacing to the user.
    });
  });
}
