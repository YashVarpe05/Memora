# Deploying Memora so every phone just works

Goal: a server that is always on, free, with HTTPS, and a phone app that you install once on any
phone and it connects and starts indexing by itself (no laptop, USB or QR).

## What was verified, and what was not

| Item | Status |
|---|---|
| Full production stack (`compose.production.yml`) built and run locally: migrations, HTTPS proxy, auth gates, upload, search, restart | verified on this laptop (x86), 2026-11-10 |
| Self-enrolling APK: fresh install, no pairing, lands on the Index screen, one tap, documents indexed, no files uploaded | verified on an Android emulator, debug and signed release builds, 2026-11-12 |
| Encrypted backup, verify, restore into a throwaway database | verified, 2026-11-11 |
| Running on ARM (Oracle's free VM), a real public domain, a real Let's Encrypt certificate, a phone over mobile data | **not verified**: needs your accounts |

## No server at all: local mode

An APK built **without** a server address (`pnpm build` with no `VITE_MEMORA_SERVER`) works alone. A new
phone needs no laptop, USB, QR or account: install, open, tap **Allow scanning this phone**, and allow file
access. The phone reads documents itself (Hindi and Marathi included), hides Aadhaar and PAN numbers, and keeps
the words in a private index on the phone. A background job (about every 6 hours, battery not low, app closed)
indexes new files. Search matches words and the kind of document, not meaning; nothing is uploaded and other
devices cannot search it. Verified on an Android emulator with no server running (2026-11-12).

## 1. Get a free always-on server (you do this once, about 20 minutes)

I cannot create accounts or enter payment details for you. Cheapest zero-cost path:

1. **Oracle Cloud "Always Free"** (cloud.oracle.com): create an account (a card is used for
   identity verification). Create a VM: shape **VM.Standard.A1.Flex**, 2 OCPU and 12 GB memory,
   Ubuntu 22.04 or 24.04, boot volume 50 GB, and download the SSH key. Open ports **80 and 443**
   in the VM's security list and in its firewall (`sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT`,
   same for 443, then save). Check Oracle's current Always Free terms: free-tier capacity can be
   unavailable in a region, and idle instances can be reclaimed.
2. **A free domain**: duckdns.org, sign in, create a name such as `yourname-memora`, and point
   it at the VM's public IP. You then have `yourname-memora.duckdns.org`. Caddy fetches a free
   HTTPS certificate for it automatically.

Any other always-on Linux machine you own works the same way. Do not use a free tier that sleeps
or wipes its disk: documents are stored on the server's disk.

## 2. Start the server (on the VM)

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
git clone https://github.com/YashVarpe05/Memora.git && cd Memora
python3 scripts/deploy_env.py yourname-memora.duckdns.org --semantic   # writes .env.production
docker compose -f compose.production.yml --env-file .env.production up -d --build
# once, only with --semantic: download the pinned meaning-search model (~1.1 GB) into a volume
docker compose -f compose.production.yml --env-file .env.production run --rm api python -m memora.services.embedding --warmup
docker compose -f compose.production.yml --env-file .env.production restart api worker
```

`--semantic` needs about 3 GB of RAM and builds a larger image; leave it off for word and
document-type search only. The script prints the exact command for step 3. Check
`https://yourname-memora.duckdns.org/api/health/ready` in a browser.

## 3. Build the phone app (on the computer with the Android SDK)

```bash
scripts/build_apk.sh https://yourname-memora.duckdns.org/api <ENROLLMENT_SECRET from .env.production>
```

This produces `builds/memora.apk`, signed with a key created once in `~/.memora/` (back that
folder up: without it a newer APK cannot update an older install).

## 4. Install on any phone

Copy `builds/memora.apk` to the phone (cable, Drive, or a message to yourself), open it, allow
"install unknown apps" when Android asks, open Memora. It connects on its own and opens the Index
screen. Tap **Allow online indexing & scan**, then turn on **Allow access to manage all files**
when Android shows that switch. Keep the app open and the screen on during the first scan.

## Safety you should know

- The enrollment secret is inside the APK. **Never share or publish the APK.** Anyone who has
  it can create an empty library on your server; they cannot read another device's library.
- To stop new phones joining, set `ENROLLMENT_SECRET=` empty in `.env.production` and restart
  `api`. To remove one phone, revoke its device id: `POST /pair/revoke/{id}` with your
  `OPERATOR_SECRET` in the `x-memora-operator` header.
- Reinstalling the app creates a new, empty library for that phone; the old one stays until revoked.
- Back up regularly: `MEMORA_BACKUP_PASSPHRASE=... python3 scripts/backup.py backup --production`,
  and test restoring with `restore-check`. Use full-disk encryption on the server.

## Quick remote test with no account (laptop must stay on)

Cloudflare's quick tunnel gives a temporary public HTTPS address to a server running on your
laptop, with no signup: `cloudflared tunnel --url http://localhost:8000`. It is for a demo only,
because the address changes and the laptop must be on.
