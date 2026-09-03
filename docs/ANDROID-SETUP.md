# Building and running Memora on a phone

Written for someone who has never built an Android app.

## Status — 2026-09-03

Run end to end on a **Samsung Galaxy S23 FE, Android 16 (SDK 36)**, laptop on the phone's
hotspot, phone on mobile data.

**Verified on device:**

| | |
|---|---|
| Build and install | Gradle 9.5 under **JDK 25** — the bundled Android Studio JBR. No toolchain downgrade needed |
| App launch | WebView loads the bundled assets; an unpaired build opens on the pairing screen |
| QR scan | MLKit barcode scanning decodes live camera frames |
| Pairing | code claimed, token stored, laptop counter went to `1 device paired` |
| Token enforcement | search from `10.29.51.91` (non-loopback) succeeds only with the token attached |
| Two-stage retrieval | fast arm paints results, stage 1 re-ranks and shows `understood: type: image` |
| OCR retrieval | a WhatsApp image was returned by its *read* text, not its filename |
| Thumbnails | placeholder icons for files that genuinely have none — not broken images |

**Still unverified:** the device scan itself — `FileDiscoveryPlugin`, `MANAGE_EXTERNAL_STORAGE`,
MediaStore enumeration and upload. Those files keep their `UNVERIFIED ON DEVICE` headers.

### The CORS trap, and why it cost an afternoon

Scanning the QR failed with *"Could not reach your computer. Check both are on the same
hotspot."* The network was never the problem. The access log had the answer the whole time:

```
10.29.51.91 - "OPTIONS /pair/claim HTTP/1.1" 400 Bad Request
              Disallowed CORS origin
```

**A Capacitor WebView serves the bundled app from `http://localhost` with no port.**
`cors_origins` listed only `http://localhost:5173`, the Vite dev server. Posting JSON is
not a simple request, so the browser preflighted, the preflight was refused, `fetch` threw,
and a catch-all reported a network failure it had not established.

Two lessons, both now built into the code:

1. **Read the access log before touching the network.** The request had arrived every time.
2. **A browser cannot distinguish "unreachable" from "blocked by CORS"** — both throw the
   same `TypeError`, deliberately. Guessing between them in an error message is guessing.
   `PairScanScreen` now probes with a `no-cors` GET, which is never preflighted, and only
   names the network when nothing answered at all.

Two other red herrings worth recording: `ping` from phone to laptop is 100% lost while
HTTP works fine, because Windows blocks ICMP on **Public** network profiles but not the TCP
ports — do not diagnose a firewall from a failed ping. And a cable that charges may not
carry data: `Unknown USB Device (Device Descriptor Request Failed)` with `VID_0000` means
enumeration failed before Android was involved, so no phone setting can fix it.

---

## 1. On the phone, before anything else

Do this while Android Studio downloads.

1. **Settings → About phone**, and tap **Build number** seven times. It will say
   "You are now a developer".
2. **Settings → System → Developer options** (on some phones: Settings → Additional
   settings → Developer options).
3. Turn on **USB debugging**.
4. Turn on **Install via USB** if your phone has it.

## 2. Install Android Studio

Download from <https://developer.android.com/studio> and install with the defaults. On
first launch it runs a setup wizard — accept the standard settings. It downloads the SDK,
which is another few GB.

**What you actually need from it**, and the wizard installs all of it:

- Android SDK Platform (API 34 or newer)
- Android SDK Build-Tools
- Android SDK Platform-Tools — this is where `adb` comes from
- A JDK — Android Studio bundles one

**Set two environment variables** so the command line can find the SDK. In PowerShell:

```powershell
setx ANDROID_HOME "$env:LOCALAPPDATA\Android\Sdk"
setx JAVA_HOME "C:\Program Files\Android\Android Studio\jbr"
```

Close and reopen every terminal afterwards — `setx` only affects new ones. Check it took:

```bash
echo $ANDROID_HOME
```

## 3. Generate the Android project

From the repo root:

```bash
pnpm -C apps/web build
```

```bash
pnpm -C apps/web exec cap add android
```

That creates `apps/web/android/`, a real Android Studio project. It is generated — do not
hand-edit anything in it that could be regenerated, except the two things in §4.

## 4. Copy in the two files that cannot be generated

**a. The file discovery plugin.** Copy

```
apps/web/android-plugin/FileDiscoveryPlugin.java
```

to

```
apps/web/android/app/src/main/java/ai/memora/app/FileDiscoveryPlugin.java
```

Create the folders if they are missing. Capacitor auto-registers plugins in that package
from version 5 onward; if the plugin is not found at runtime, register it explicitly in
`MainActivity.java` and note that in §7.

**b. The manifest permissions.** Open

```
apps/web/android/app/src/main/AndroidManifest.xml
```

and merge in the entries from `apps/web/android-plugin/AndroidManifest.additions.xml` —
five `<uses-permission>` lines before `<application>`, and
`android:usesCleartextTraffic="true"` on the `<application>` tag itself.

> **`MANAGE_EXTERNAL_STORAGE` is restricted on the Play Store** and would block
> publication. It is used here because this is a sideloaded APK for a demo. The
> publishable alternative is the Storage Access Framework folder picker: the user chooses
> folders once, with no device-wide discovery. This belongs in the report as a
> distribution limitation.

## 5. Build and install

Plug the phone in by USB. Accept the "Allow USB debugging?" prompt on the phone — tick
"always allow from this computer".

```bash
adb devices
```

You should see your phone with `device` beside it. If it says `unauthorized`, unplug,
replug, and accept the prompt.

Then:

```bash
pnpm -C apps/web exec cap sync android
```

```bash
cd apps/web/android && ./gradlew installDebug
```

The first Gradle run downloads dependencies and takes several minutes. Memora should now be
in the app drawer.

**If Gradle fails**, open `apps/web/android` in Android Studio instead and press Run. Its
error messages are far better than Gradle's, and it offers to install anything missing.

## 6. The demo, end to end

### Network: use the phone's hotspot

**Turn on the phone's hotspot and join the laptop to it.** Do not use college wifi —
campus networks usually enable client isolation, which blocks the phone from reaching the
laptop even though both are "connected". That is untested here and likely to fail. The
hotspot is the supported path, not a fallback.

### On the laptop

```bash
docker compose up -d
```

```bash
cd apps/api && uv run uvicorn memora.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` matters. The default binds to localhost only, and the phone cannot reach
that — this is the single most likely reason a first attempt fails.

Get the pairing QR:

```bash
curl -s -X POST http://localhost:8000/pair/start
```

That returns `{"code": "...", "url": "http://192.168.x.x:8000", "expires_at": "..."}`.
The `url` should be the hotspot address, not `127.0.0.1`. **Render that JSON as a QR** —
any online QR generator, or paste it into the web UI once the pairing screen exists.

**The code expires in five minutes.** Generate a fresh one if the phone is slow to scan.

### On the phone

1. Open Memora. It asks to pair.
2. Scan the QR.
3. **A successful pair looks like:** the scan screen closes, and the search box appears
   with the server address shown somewhere on screen. Nothing else happens — there is no
   "connected!" toast.
4. **A failed pair looks like:** "Could not reach your computer" (wrong network, or the
   server bound to localhost) or "That code did not work" (expired or already used).

Confirm from the laptop:

```bash
curl -s http://localhost:8000/pair/status
```

`devices_paired` should be `1`.

### Then

5. Tap **Scan my phone**. Read the consent screen — it says files go to your computer.
6. Allow file access. Android opens a full Settings page, not a dialog. Toggle Memora on
   and press back.
7. Indexing starts, newest files first, capped at 500.
8. Search **"the whatsapp message from aradhana"** or similar.
9. Tap the result. It should open. Download should save it.
10. Search **"my passport"** → *"I don't have that."*

---

## 7. What to check on the first run — this is the real point of the exercise

Every item is an assumption I could not test. Record what actually happens.

### Permissions
- [ ] Does the `MANAGE_EXTERNAL_STORAGE` Settings page open at all?
- [ ] After toggling it on and pressing back, does the app notice? **There is no callback
      from that screen** — the code re-checks on resume, and that path is unverified.
- [ ] Does denying it leave the app in a sensible state, or stuck?

### Scanning
- [ ] **How long does a scan of your real gallery take?** Estimated as milliseconds for
      metadata, but never measured on a phone.
- [ ] Does MediaStore return **PDFs from Downloads/**, or only gallery images? The query
      uses `MediaStore.Files`, which should, but this is the assumption most likely to be
      wrong.
- [ ] Is newest-first ordering actually newest-first?
- [ ] Does the 500 cap hold, or does it try to scan everything?

### Network and transfer
- [ ] Do **thumbnails load over the LAN**, or is the phone too slow to fetch them?
- [ ] How long does uploading 500 images take over a hotspot?
- [ ] **What happens when the hotspot drops mid-scan?** There is no offline queue in this
      phase — the expected answer is that it fails and needs restarting, and confirming
      that is more useful than assuming it.
- [ ] Does the app recover after the laptop's IP changes (hotspot restart)?

### Pairing
- [ ] Does the QR scan work in normal room lighting?
- [ ] Does the token survive killing and reopening the app?
- [ ] From a **second phone on the same hotspot**, does an unpaired request get 401? This
      is the privacy property — worth testing deliberately rather than assuming.

### Build
- [ ] Did the plugin auto-register, or did `MainActivity` need editing?
- [ ] Did cleartext HTTP work, or did Android block it despite the manifest?

## 8. If it does not work

**The phone cannot reach the laptop.** Almost always one of: the server bound to localhost
instead of `0.0.0.0`; Windows Firewall blocking port 8000; or the two devices on different
networks. Test with the phone's browser at `http://192.168.x.x:8000/health` — if that
fails, nothing else will work, and it is a network problem rather than an app problem.

**Windows Firewall** will likely prompt the first time uvicorn binds. Allow it on private
networks. If you dismissed the prompt, add the rule manually.

**The app installs but shows a blank screen.** The web build is missing or stale. Re-run
`pnpm -C apps/web build` then `cap sync android`.
