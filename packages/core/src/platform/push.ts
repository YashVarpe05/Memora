/**
 * Push notifications — "your upload finished processing".
 * Web uses the Push API; a native build uses FCM. Unimplemented in phase 1.
 */
export interface PushProvider {
  isSupported(): Promise<boolean>;
  requestPermission(): Promise<boolean>;
  getToken(): Promise<string | null>;
  onMessage(handler: (payload: PushPayload) => void): () => void;
}

export interface PushPayload {
  title: string;
  body: string;
  data?: Record<string, string>;
}
