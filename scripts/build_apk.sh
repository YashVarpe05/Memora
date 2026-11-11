#!/usr/bin/env bash
# Build a signed, release-mode Memora APK that enrolls itself on first launch.
#
#   scripts/build_apk.sh https://memora.example.com/api  <enrollment-secret>
#
# The secret is compiled INTO the APK (see prompts/zero-touch-enrollment.md): keep the APK
# personal, never publish it. Output: builds/memora.apk. A signing key is created once at
# ~/.memora/release.keystore (password in ~/.memora/release.pass, mode 600) and reused, so a
# newer APK installs over an older one. Needs the Android SDK (ANDROID_HOME or ~/Android/Sdk).
set -euo pipefail

SERVER="${1:?usage: build_apk.sh <https://host/api> <enrollment-secret>}"
SECRET="${2:?usage: build_apk.sh <https://host/api> <enrollment-secret>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
KEYDIR="$HOME/.memora"
BUILD_TOOLS="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"

case "$SERVER" in
  https://*|http://127.0.0.1*|http://localhost*|http://10.0.2.2*) ;;
  *) echo "The server address must be https:// (plain http only for localhost)." >&2; exit 2 ;;
esac

mkdir -p "$KEYDIR" "$ROOT/builds"
chmod 700 "$KEYDIR"
if [ ! -f "$KEYDIR/release.keystore" ]; then
  (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$KEYDIR/release.pass")
  keytool -genkeypair -v -keystore "$KEYDIR/release.keystore" -alias memora -keyalg RSA -keysize 3072 \
    -validity 9125 -storepass "$(cat "$KEYDIR/release.pass")" -keypass "$(cat "$KEYDIR/release.pass")" \
    -dname "CN=Memora personal build" >/dev/null 2>&1
  echo "Created a signing key in $KEYDIR (back it up: without it new APKs cannot update old installs)."
fi

cd "$ROOT/apps/web"
VITE_MEMORA_SERVER="$SERVER" VITE_MEMORA_ENROLL_SECRET="$SECRET" pnpm build
pnpm exec cap sync android
(cd android && ANDROID_HOME="$SDK" sh gradlew assembleRelease --console=plain)

UNSIGNED="$(ls android/app/build/outputs/apk/release/*.apk | head -1)"
ALIGNED="$ROOT/builds/memora-aligned.apk"
"$BUILD_TOOLS/zipalign" -f -p 4 "$UNSIGNED" "$ALIGNED"
"$BUILD_TOOLS/apksigner" sign --ks "$KEYDIR/release.keystore" --ks-key-alias memora \
  --ks-pass "file:$KEYDIR/release.pass" \
  --out "$ROOT/builds/memora.apk" "$ALIGNED"
rm -f "$ALIGNED" "$ROOT/builds/memora.apk.idsig"
"$BUILD_TOOLS/apksigner" verify --print-certs "$ROOT/builds/memora.apk" | head -2
echo "Built $ROOT/builds/memora.apk ($(du -h "$ROOT/builds/memora.apk" | cut -f1)) for $SERVER"
