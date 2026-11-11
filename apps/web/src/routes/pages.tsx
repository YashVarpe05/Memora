import { Camera, Clock, FileText, Mic } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Routes } from '@memora/core';

import { Button } from '@/components/ui/button';
import { ChatView } from '@/features/chat/ChatView';
import { apiFetch, pairedServer } from '@/platform/api';
import { isLocalMode } from '@/platform/localMode';
import { localIndex } from '@/platform/localIndex.native';
import { useNavigator } from '@/platform/navigator';

export function AskPage() {
  return <ChatView />;
}

function Placeholder({
  title,
  body,
  phase,
  children,
}: {
  title: string;
  body: string;
  phase: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-ink-muted">{body}</p>
      </div>
      {children}
      <p className="text-xs text-ink-faint">Lands in {phase}.</p>
    </div>
  );
}

export function CapturePage() {
  return (
    <Placeholder
      title="Capture"
      body="Photograph a whiteboard or handwritten page, or record a voice note. Uploads queue offline and drain when you reconnect."
      phase="phase 4"
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button variant="subtle" className="flex-1" disabled>
          <Camera className="size-4" aria-hidden /> Photo
        </Button>
        <Button variant="subtle" className="flex-1" disabled>
          <Mic className="size-4" aria-hidden /> Voice note
        </Button>
      </div>
    </Placeholder>
  );
}

export function TimelinePage() {
  return (
    <Placeholder
      title="Timeline"
      body="Memories organise themselves. Nothing to file - entities, tags and dates are extracted on ingest."
      phase="phase 4"
    >
      <Clock className="size-5 text-ink-faint" aria-hidden />
    </Placeholder>
  );
}

export function SettingsPage() {
  const paired = pairedServer();
  const [documents, setDocuments] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    if (isLocalMode()) {
      void localIndex.documents().then(n => { if (live) setDocuments(n); }).catch(() => undefined);
      return () => { live = false; };
    }
    if (!paired) return;
    void apiFetch('/api/index/coverage')
      .then(async (response) => (response.ok ? await response.json() as { available_documents: number } : null))
      .then((body) => { if (live && body) setDocuments(body.available_documents); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [paired?.url]);

  const host = paired ? new URL(paired.url).host : null;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Settings</h1>

      <div className="flex flex-col gap-2 rounded-card border border-line bg-surface p-3">
        <span className="text-sm font-medium text-ink">This device</span>
        <span className="text-sm text-ink">
          {documents === null ? (paired || isLocalMode() ? 'Checking your library…' : 'Not connected.')
            : `${documents} ${documents === 1 ? 'document is' : 'documents are'} searchable here.`}
        </span>
        <span className="text-xs text-ink-muted">Each device keeps its own library. Other devices cannot search this one.</span>
        <Link to={Routes.Scan} className="mt-1 self-start text-sm font-medium text-accent underline">
          Index files again
        </Link>
      </div>

      {/* A permanent, manual way to reach pairing, for when the automatic path cannot work. */}
      <div className="flex flex-col gap-2 rounded-card border border-line bg-surface p-3">
        <span className="text-sm font-medium text-ink">Connection</span>
        <span className="text-xs text-ink-muted">
          {host ? `Connected to ${host}.` : isLocalMode() ? 'Working on this phone only. Nothing leaves it.' : 'Not connected to a Memora server.'}
        </span>
        <span className="text-xs text-ink-muted">
          Disconnecting does not erase stored documents. Reinstalling the app starts a new, empty library.
        </span>
        <Link
          to={Routes.Pair}
          className="mt-1 self-start text-sm font-medium text-accent underline"
        >
          {paired ? 'Reconnect or disconnect' : 'Connect to your server'}
        </Link>
      </div>
    </div>
  );
}

export function MemoryPage() {
  const { id } = useParams<{ id: string }>();
  const navigator = useNavigator();

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-8">
      <Button variant="ghost" size="md" className="self-start px-0" onClick={() => navigator.back()}>
        Back
      </Button>
      <div className="flex items-center gap-2">
        <FileText className="size-5 text-ink-faint" aria-hidden />
        <h1 className="text-xl font-semibold tracking-tight">Source</h1>
      </div>
      <p className="text-sm text-ink-muted">
        Memory <code className="rounded bg-surface-sunken px-1.5 py-0.5 text-xs">{id}</code> opens
        here with the cited span highlighted.
      </p>
      <p className="text-xs text-ink-faint">Lands in phase 5.</p>
    </div>
  );
}
