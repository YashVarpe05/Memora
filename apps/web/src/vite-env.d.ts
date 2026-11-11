/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Zero-touch enrollment: the API base the APK joins, and the secret it joins with. */
  readonly VITE_MEMORA_SERVER?: string;
  readonly VITE_MEMORA_ENROLL_SECRET?: string;
}
