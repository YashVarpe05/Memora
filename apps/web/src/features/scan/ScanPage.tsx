import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { isNative } from '@/platform/api';
import { isLocalMode } from '@/platform/localMode';
import { useDeviceScan } from './useDeviceScan';

const LOCAL_STEPS = [
  'Reads the PDFs, photos and text on this phone, including Hindi and Marathi.',
  'Hides Aadhaar and PAN numbers before the words are saved.',
  'Keeps everything on this phone. Nothing is uploaded and no account is needed.',
  'Keeps looking for new files in the background.',
];

const STEPS = [
  'Reads the PDFs, photos and text on this device.',
  'Hides Aadhaar and PAN numbers before anything leaves it.',
  'Sends only the words, not the files. Your files stay where they are.',
];

export function ScanPage() {
  const scan = useDeviceScan();
  const scanning = scan.phase === 'scanning';
  const added = scan.progress.queued + scan.progress.known;
  const local = isLocalMode();
  const steps = local ? LOCAL_STEPS : STEPS;
  const finished = scan.phase === 'done' || scan.phase === 'attention';
  return <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
    <h1 className="text-xl font-semibold">Find the files on this device</h1>
    <p className="text-sm text-ink-muted">Search by contents, even when filenames are just numbers.
      PDFs, photos, screenshots, text and Word documents are supported, up to 25 MB each.</p>

    {!scan.consented && <section aria-label="What happens" className="rounded-card border border-line bg-surface p-4">
      <h2 className="mb-2 text-base font-semibold">{isNative() ? 'Make this phone searchable' : 'Make a folder searchable'}</h2>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
        {steps.map(step => <li key={step}>{step}</li>)}
      </ul>
      <p className="mt-2 text-xs text-ink-muted">{local ? 'Searches match the words in your documents and the kind of document. Other devices cannot search this phone.' : 'This device has its own library. Other devices cannot search it.'}</p>
    </section>}

    <div className="flex flex-wrap gap-3">
      <Button disabled={scanning} onClick={() => void scan.choose()}>
        {local ? 'Allow scanning this phone' : isNative() ? 'Allow online indexing & scan' : 'Allow online indexing & choose folder'}
      </Button>
      <Button variant="subtle" disabled={scanning} onClick={() => void scan.start()}>Rescan</Button>
      {scanning && <Button variant="subtle" onClick={scan.cancel}>Pause uploads</Button>}
    </div>

    {scanning && <div aria-hidden className="h-1.5 overflow-hidden rounded-full bg-line">
      <div className="h-full w-1/3 animate-pulse rounded-full bg-accent" />
    </div>}
    <p role="status" className="text-sm">{scan.phase}: {scan.progress.seen} checked · {scan.progress.queued} {local ? 'added to this phone' : 'sent for indexing'} · {scan.progress.known} unchanged · {scan.progress.failed} need attention</p>
    {scanning && <p className="text-xs text-ink-muted">{isNative()
      ? 'Keep Memora open and the screen on until this finishes. Your first scan can take a while for a full phone.'
      : 'Keep this page open until this finishes.'}</p>}
    {scan.phase === 'permission' && <p>Grant file access in Android settings, then return here.</p>}
    {finished && added > 0 && <p className="rounded-card bg-accent-soft p-3 text-sm">
      {scan.progress.failed ? 'Mostly done.' : 'All set.'} Your documents are searchable now; {local ? 'new files are picked up in the background.' : 'new files are picked up while the app is open.'}
    </p>}
    <Link className="text-accent underline" to="/search">Search completed documents now</Link>
    {scan.error && <p role="alert" className="text-warn">{scan.error}</p>}
    <div className="flex flex-wrap gap-3 text-sm">
      {Object.entries(scan.jobs.counts).map(([state, count]) => <span key={state}>{count} {state}</span>)}
    </div>
    {scan.issues.map((issue, i) => <p className="text-sm text-warn" key={i}>{issue}</p>)}

    <details className="rounded-card border border-line p-3 text-sm">
      <summary className="cursor-pointer font-medium">Details and options</summary>
      <div className="mt-3 flex flex-col gap-3">
        <p className="text-ink-muted">{isNative()
          ? 'This phone reads PDFs, photos and text files itself and sends only the extracted text, with Aadhaar and PAN numbers masked, to your Memora server. Word, email and calendar files cannot be read on the phone, so those are uploaded as files. Memora checks for new and changed files while the app is open and when you return.'
          : 'Selected documents are sent to your configured Memora server for storage and text recognition. Aadhaar and PAN masking applies before embedding; the original uploaded file is not masked. Supporting browsers remember the folder and check while Memora is open; others need the folder selected again for each rescan.'}</p>
        <Button variant="subtle" onClick={scan.disable}>Turn off automatic discovery</Button>
        <ul className="flex flex-col gap-2">
          {scan.jobs.jobs.map(job => <li key={job.id} className="rounded-card border border-line p-3">
            <p className="break-all font-medium">{job.filename}</p><p>{job.status}</p>
            {job.error && <p className="text-warn">{job.error}</p>}
            {job.status === 'failed' && <Button variant="subtle" onClick={() => void scan.retry(job.id)}>Retry indexing</Button>}
          </li>)}
        </ul>
        <div className="flex gap-3">
          <Button variant="subtle" disabled={scan.jobsOffset === 0}
            onClick={() => scan.setJobsOffset(n => Math.max(0, n - 100))}>Previous files</Button>
          <Button variant="subtle" disabled={scan.jobsOffset + 100 >= Object.values(scan.jobs.counts).reduce((a, b) => a + b, 0)}
            onClick={() => scan.setJobsOffset(n => n + 100)}>Next files</Button>
        </div>
      </div>
    </details>
  </div>;
}
