import { AlertTriangle } from 'lucide-react';

/**
 * Shown when the API reports that query understanding is unavailable.
 *
 * The failure being guarded against is specific: when the daily model quota runs out,
 * stage 1 silently falls back to plain similarity search. Results get measurably worse
 * — Recall@1 drops from 0.947 to 0.842 on our gold set — and without this banner
 * nothing tells anyone why. That is the worst thing that can happen during a demo,
 * because it looks like the system is simply bad rather than temporarily degraded.
 */
export function DegradedBanner({ message }: { message: string | null | undefined }) {
  if (!message) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-card bg-warn-soft px-3 py-2 text-xs text-warn"
    >
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}
