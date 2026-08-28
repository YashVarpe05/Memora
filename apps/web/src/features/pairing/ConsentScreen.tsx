import { FolderSearch, Laptop, ShieldCheck } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';

/**
 * UNVERIFIED ON DEVICE. Not rendered on a phone.
 *
 * **This screen is marked do-not-cut in the plan**, and the reason is not politeness. It
 * is where the personal-server architecture is stated honestly to the person whose
 * documents are about to be read.
 *
 * `PRODUCT.md` says the phone build's claim is "nothing leaves devices the user owns" —
 * NOT "nothing leaves the device", which was true only while everything ran on one
 * machine. A phone cannot run Postgres or a 3B model, so files go to the user's own
 * computer. That is a materially different sentence and the user is the person entitled
 * to hear it before granting storage access, not after.
 *
 * It also asks at the right moment: on the scan the user starts, never on first launch.
 * A permission dialog with no context is denied, and Android does not ask twice.
 */
export function ConsentScreen({
  serverUrl,
  onAccept,
  onCancel,
}: {
  serverUrl: string;
  onAccept: () => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Let Memora read your files</h1>
        <p className="text-sm text-ink-muted">
          To find a document by describing it, Memora first has to know what you have.
        </p>
      </div>

      <ul className="flex flex-col gap-4">
        <Point Icon={FolderSearch} title="What is read">
          Photos, screenshots and PDFs on this phone. Memora reads them to extract text and
          build a search index. It does not read messages, contacts, or anything else.
        </Point>

        {/*
          The honest sentence. Do not soften it to "processed privately" or "stays on your
          device" - the files genuinely travel to another machine, and saying so here is
          the difference between a claim and a claim the user can check.
        */}
        <Point Icon={Laptop} title="Where files go">
          To <strong>your own computer</strong> at{' '}
          <code className="rounded bg-surface-sunken px-1 py-0.5 text-xs">{serverUrl}</code> —
          the one showing the QR code. Files travel over your hotspot between two devices you
          own. They are never uploaded to the internet and never reach anyone else.
        </Point>

        <Point Icon={ShieldCheck} title="What never leaves">
          Aadhaar and PAN numbers are masked out before anything is stored or indexed.
          Search happens entirely on your computer — no document, image, or search of yours
          is sent to any company.
        </Point>
      </ul>

      <div className="flex flex-col gap-2 pt-2">
        <Button
          onClick={() => {
            setBusy(true);
            onAccept();
          }}
          disabled={busy}
          className="min-h-12"
        >
          {busy ? 'Opening settings…' : 'Choose files to scan'}
        </Button>
        <Button variant="ghost" onClick={onCancel} className="min-h-11">
          Not now
        </Button>
      </div>

      <p className="text-xs text-ink-faint">
        Android will ask you to allow file access on the next screen. You can turn it off
        again at any time in Settings.
      </p>
    </div>
  );
}

function Point({
  Icon,
  title,
  children,
}: {
  Icon: typeof Laptop;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-3">
      <Icon className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-ink">{title}</span>
        <span className="text-sm leading-relaxed text-ink-muted">{children}</span>
      </div>
    </li>
  );
}
