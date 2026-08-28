# Building and running Memora on a phone

**Nothing in this document has been verified.** No APK has been built and no phone has run
this code. Every Android file in the repo carries an "UNVERIFIED ON DEVICE" header. Treat
this as a first attempt to follow, not a procedure known to work — and expect two or three
things in §7 to be wrong.

Written for someone who has never built an Android app.

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
