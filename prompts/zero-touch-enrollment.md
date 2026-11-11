# Zero-touch enrollment: install the APK on a new phone and it just works

Status: APPROVED by the user on 2026-11-11 ("when I install this apk on another new device I
don't need to connect to my laptop via USB or anything, it directly starts indexing").

## Goal
Install the APK on any phone, open it, and with no laptop, no USB, no QR and no typing the phone
connects to the owner's hosted server and offers to index. Two taps remain on purpose, because
they are consent and an Android rule, not setup: "Allow indexing" and Android's "all files
access" switch.

## How
1. The server gets one new optional secret, `ENROLLMENT_SECRET` (long, random). Unset = the
   feature is off.
2. `POST /pair/enroll {secret}` returns a fresh device token and creates a NEW library for that
   device (per-device libraries stay as decided). A wrong secret is a generic 401. After 10 wrong
   guesses the endpoint locks for 10 minutes. Comparison is constant time.
3. The APK is built with `VITE_MEMORA_SERVER` and `VITE_MEMORA_ENROLL_SECRET`. On first launch,
   when the phone is not yet paired, the app calls `/pair/enroll`, saves the token the same way
   a scanned invitation does, and opens the Index screen with the consent button.
4. The manual routes (QR invitation, typed code) are unchanged and remain the fallback.

## Threat model, stated plainly
The secret sits inside the APK, so ANYONE who has the APK can enroll a device and get an empty
library of their own on this server. They cannot read anyone else's library (each device token
opens only its own, enforced by row-level security). So:
- Do not share or publish the APK. It is a personal build.
- To stop new enrollments, change or unset `ENROLLMENT_SECRET`. To remove a device, revoke it
  (`/pair/revoke/{id}`). Existing devices keep working until revoked.
- A reinstall creates a new library; the old one stays until revoked.
- Hosted servers must be HTTPS; the app refuses plain HTTP except for localhost.

## Not in scope
Accounts and sign-in, sharing one library across devices, an app store release, or hiding the
secret from someone who has the APK.

## Gates
API tests (enroll on/off, wrong secret, lockout, token works, one library per enrollment), web
unit test for the client helper, typecheck, build, API contract unchanged except the new route,
then a fresh install on the phone with no manual pairing.
