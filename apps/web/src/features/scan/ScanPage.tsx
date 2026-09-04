import { CheckCircle2, FolderSearch, Loader2, Rocket, ShieldAlert } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ConsentScreen } from '@/features/pairing/ConsentScreen';
import { cn } from '@/lib/utils';
import { isNative, pairedServer } from '@/platform/api';

import { useDeviceScan, type ScanMode } from './useDeviceScan';

/**
 * Indexing the documents already on this phone.
 *
 * The order is deliberate: explain, then ask. `ConsentScreen` comes first because the app
 * is about to read the user's whole gallery and send it to another machine, and a
 * permission dialog with no context is denied — Android does not ask twice.
 *
 * That screen was written, marked do-not-cut, and then referenced by nothing at all. It
 * was as absent as if it had never been built. This is where it is actually reachable.
 */
export function ScanPage() {
  const paired = pairedServer();
  const scan = useDeviceScan();
  const [mode, setMode] = useState<ScanMode>('quick');

  if (!isNative()) {
    return (
      <Panel>
        <h1 className="text-xl font-semibold tracking-tight">Not available in a browser</h1>
        <p className="text-sm text-ink-muted">
          A browser cannot list the files on your device — there is no web API for it, by
          design. Open Memora on your phone to index what is already there.
        </p>
      </Panel>
    );
  }

  if (!paired) {
    return (
      <Panel>
        <h1 className="text-xl font-semibold tracking-tight">Connect your computer first</h1>
        <p className="text-sm text-ink-muted">
          Files found here are sent to your own computer to be indexed. Pair with it before
          scanning.
        </p>
      </Panel>
    );
  }

  if (scan.phase === 'idle') {
    return (
      <Panel>
        <div className="flex flex-col gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Index this phone</h1>
          <p className="text-sm text-ink-muted">
            Memora can look through the documents already on this phone — screenshots,
            PDFs, photos of paperwork — so you can find them by describing them.
          </p>
        </div>
        <Button className="min-h-12" onClick={() => scan.setPhase('consent')}>
          <FolderSearch className="size-4" aria-hidden /> Get started
        </Button>
      </Panel>
    );
  }

  if (scan.phase === 'consent') {
    return (
      <ConsentScreen
        serverUrl={paired.url}
        onAccept={() => void scan.requestPermission()}
        onCancel={() => scan.setPhase('idle')}
      />
    );
  }

  if (scan.phase === 'permission') {
    return (
      <Panel>
        <div className="flex items-start gap-3 rounded-card border border-line bg-surface p-3">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
          <span className="text-sm leading-relaxed text-ink-muted">
            Android is asking for file access on its own Settings page. Turn on{' '}
            <strong className="text-ink">Allow access to manage all files</strong>, then come
            back here — this screen updates by itself.
          </span>
        </div>
        {/* There is no callback from that Settings page. The hook re-checks on resume, so
            "denied" here means checked-and-denied, not "not answered yet". */}
        {scan.permission === 'denied' && (
          <p className="text-sm text-warn">
            Access is still off. Without it Memora cannot see the files on this phone.
          </p>
        )}
        <Button variant="subtle" onClick={() => scan.setPhase('idle')}>
          Cancel
        </Button>
      </Panel>
    );
  }

  if (scan.phase === 'choosing') {
    return (
      <Panel>
        <div className="flex flex-col gap-2">
          <h1 className="text-xl font-semibold tracking-tight">How much to index</h1>
          <p className="text-sm text-ink-muted">
            You can start small and index the rest later. Nothing is deleted either way.
          </p>
        </div>

        <ModeCard
          selected={mode === 'quick'}
          onSelect={() => setMode('quick')}
          title="Recent files"
          detail="The 500 most recent. Useful in about a minute — this is the one to pick first."
        />
        <ModeCard
          selected={mode === 'full'}
          onSelect={() => setMode('full')}
          title="Everything"
          detail="Every document on the phone. Thorough, but it can run for hours."
        />

        <Button className="min-h-12" onClick={() => void scan.start(mode)}>
          <Rocket className="size-4" aria-hidden /> Start indexing
        </Button>
      </Panel>
    );
  }

  if (scan.phase === 'scanning' || scan.phase === 'done') {
    const { total, seen, uploaded, duplicate, failed, currentName, elapsedMs } = scan.progress;
    const done = scan.phase === 'done';
    // A count, never a bare spinner. During a scan of thousands of files a spinner is
    // indistinguishable from a hang, and someone watching cannot tell it is working.
    const pct = total > 0 ? Math.min(100, Math.round((seen / total) * 100)) : 0;

    return (
      <Panel>
        <div className="flex flex-col gap-2">
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            {done ? (
              <CheckCircle2 className="size-5 text-accent" aria-hidden />
            ) : (
              <Loader2 className="size-5 animate-spin text-accent" aria-hidden />
            )}
            {done ? 'Finished' : 'Indexing…'}
          </h1>
          <p className="text-sm tabular-nums text-ink-muted">
            {total > 0 ? `${seen.toLocaleString()} of ${total.toLocaleString()} files` : `${seen.toLocaleString()} files`}
            {' · '}
            {(elapsedMs / 1000).toFixed(0)}s
          </p>
        </div>

        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>

        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <Stat label="indexed" value={uploaded} />
          {/* Already held. Counting these as new would make the total a lie. */}
          <Stat label="already known" value={duplicate} />
          <Stat label="skipped" value={failed} />
        </dl>

        {currentName && !done && (
          <p className="truncate text-xs text-ink-faint">{currentName}</p>
        )}

        {done ? (
          <Button className="min-h-12" onClick={() => scan.setPhase('idle')}>
            Done
          </Button>
        ) : (
          <Button variant="subtle" onClick={scan.cancel}>
            Stop
          </Button>
        )}
      </Panel>
    );
  }

  return (
    <Panel>
      <h1 className="text-xl font-semibold tracking-tight">The scan stopped</h1>
      <p className="text-sm text-warn">{scan.error}</p>
      <Button variant="subtle" onClick={() => scan.setPhase('idle')}>
        Back
      </Button>
    </Panel>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">{children}</div>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="order-2 text-xs text-ink-faint">{label}</dt>
      <dd className="order-1 text-base font-semibold tabular-nums text-ink">
        {value.toLocaleString()}
      </dd>
    </div>
  );
}

function ModeCard({
  selected,
  onSelect,
  title,
  detail,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  detail: string;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'flex flex-col gap-1 rounded-card border p-3 text-left transition-colors',
        selected ? 'border-accent bg-accent-soft' : 'border-line bg-surface',
      )}
    >
      <span className="text-sm font-medium text-ink">{title}</span>
      <span className="text-xs leading-relaxed text-ink-muted">{detail}</span>
    </button>
  );
}
