import { useCallback, useEffect, useState } from 'react';
import { isNative, pairedServer, savePairing } from './api';
import { enrollConfig, enrollDevice, recordEnrollFailure } from './enroll';

type Status = 'idle' | 'working' | 'enrolled' | 'failed';

/**
 * Enroll once, on a native build that carries a server and a secret and is not yet paired.
 * `justEnrolled` is true for one render so the caller can route to the Index screen.
 */
export function useAutoEnroll() {
  const eligible = () => isNative() && !pairedServer() && enrollConfig() !== null;
  const [status, setStatus] = useState<Status>(() => (eligible() ? 'working' : 'idle'));
  const [justEnrolled, setJustEnrolled] = useState(false);

  useEffect(() => {
    const config = enrollConfig();
    if (status !== 'working' || !config) return;
    let cancelled = false;
    void enrollDevice(config).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        savePairing({ url: result.url, token: result.token });
        recordEnrollFailure(null);
        setStatus('enrolled');
        setJustEnrolled(true);
      } else {
        recordEnrollFailure(result.reason);
        setStatus('failed');
      }
    });
    return () => { cancelled = true; };
  }, [status]);

  const acknowledge = useCallback(() => setJustEnrolled(false), []);
  return { status, justEnrolled, acknowledge };
}
