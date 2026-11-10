import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { isNative } from '@/platform/api';
import { useDeviceScan } from './useDeviceScan';

export function ScanPage() {
  const scan = useDeviceScan();
  return <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
    <h1 className="text-xl font-semibold">Find the files on this device</h1>
    <p className="text-sm text-ink-muted">Search by contents, even when filenames are just numbers.
      PDFs, photos, screenshots, text and Word documents are supported, up to 25 MB each.</p>
    <div className="rounded-card border border-line bg-surface p-4 text-sm">
      {isNative()
        ? 'This phone reads PDFs, photos and text files itself and sends only the extracted text, with Aadhaar and PAN numbers masked, to your Memora server. The files stay on the phone. Word, email and calendar files cannot be read on the phone, so those are uploaded as files.'
        : 'Selected documents are sent to your configured Memora server for storage and text recognition. Aadhaar and PAN masking applies before embedding; the original uploaded file is not masked.'}
      {' '}Extracted text and search queries may be sent to the embedding provider.
      This device has its own library. Other devices cannot search it.
    </div>
    <p className="text-sm text-ink-muted">{isNative()
      ? 'After permission, Memora checks for new and changed files while the app is open and when you return. Keep it open until files finish uploading; server indexing can continue afterward.'
      : 'Choose a folder to grant read access. Supporting browsers remember it and check while Memora is open. If access expires, choose it again. Other browsers require you to select the folder for each rescan.'}</p>
    <div className="flex flex-wrap gap-3">
      <Button disabled={scan.phase === 'scanning'} onClick={() => void scan.choose()}>
        {isNative() ? 'Allow online indexing & scan' : 'Allow online indexing & choose folder'}
      </Button>
      <Button variant="subtle" disabled={scan.phase === 'scanning'} onClick={() => void scan.start()}>Rescan</Button>
      {scan.phase === 'scanning' && <Button variant="subtle" onClick={scan.cancel}>Pause uploads</Button>}
      <Button variant="subtle" onClick={scan.disable}>Turn off automatic discovery</Button>
    </div>
    {scan.phase === 'permission' && <p>Grant file access in Android settings, then return here.</p>}
    <p role="status" className="text-sm">{scan.phase}: {scan.progress.seen} checked · {scan.progress.queued} sent for indexing · {scan.progress.known} unchanged · {scan.progress.failed} need attention</p>
    <Link className="text-accent underline" to="/search">Search completed documents now</Link>
    {scan.error && <p role="alert" className="text-warn">{scan.error}</p>}
    <div className="flex flex-wrap gap-3 text-sm">
      {Object.entries(scan.jobs.counts).map(([state, count]) => <span key={state}>{count} {state}</span>)}
    </div>
    {scan.issues.map((issue, i) => <p className="text-sm text-warn" key={i}>{issue}</p>)}
    <ul className="flex flex-col gap-2">
      {scan.jobs.jobs.map(job => <li key={job.id} className="rounded-card border border-line p-3 text-sm">
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
  </div>;
}
