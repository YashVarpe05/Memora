package ai.memora.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

/**
 * Registers the app's own Capacitor plugins.
 *
 * **FileDiscoveryPlugin does not register itself.** Capacitor discovers npm-installed
 * plugins through `capacitor.plugins.json`, which `cap sync` generates from the
 * dependency list — a plugin living in this source tree is not an npm package and can
 * never appear there. The `@CapacitorPlugin` annotation alone does nothing.
 *
 * Without this line every FileDiscovery call rejects with "not implemented". That failure
 * is quiet on the JavaScript side: the scan screen showed "waiting for file access"
 * forever while `appops` reported the permission as `allow`, so the symptom pointed at
 * Android's permission model and the cause was six lines of missing Java. The Settings
 * page had never been opened at all.
 *
 * registerPlugin MUST be called before super.onCreate — the bridge is built there, and a
 * plugin registered afterwards is registered too late to be found.
 */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(FileDiscoveryPlugin.class);
        registerPlugin(TextExtractionPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
