import { useEffect, useState } from 'react';

import { authedObjectUrl, pairedServer } from './api';

/**
 * A usable `src` for a thumbnail or document, whether or not the app is paired.
 *
 * Unpaired (the browser), the relative path is returned unchanged and the element loads
 * it directly — no extra fetch, no behaviour change from today.
 *
 * Paired (the phone), the bytes are fetched with the device token and handed over as an
 * object URL, because `<img src>` and `<object data>` cannot send an Authorization header
 * and the token must never appear in a URL.
 */
export function useAuthedMedia(path: string | null): { src: string | null; failed: boolean } {
  const [src, setSrc] = useState<string | null>(() => (pairedServer() ? null : path));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!path) {
      setSrc(null);
      return;
    }
    if (!pairedServer()) {
      setSrc(path);
      setFailed(false);
      return;
    }

    let revoked = false;
    let url: string | null = null;
    setFailed(false);

    authedObjectUrl(path)
      .then((objectUrl) => {
        if (revoked) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        url = objectUrl;
        setSrc(objectUrl);
      })
      .catch(() => setFailed(true));

    return () => {
      revoked = true;
      // Without this the blob lives as long as the page and a long result list leaks
      // every thumbnail it ever rendered.
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);

  return { src, failed };
}
