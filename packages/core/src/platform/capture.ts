/**
 * Capture — camera and microphone.
 *
 * The mobile half of the product: photographing whiteboards and handwritten notes
 * (GOLD q007) and recording voice notes. Web implements this with getUserMedia and
 * MediaRecorder; a native build would swap in the platform camera.
 */
export type CaptureKind = 'image' | 'audio';

export interface CapturedMedia {
  kind: CaptureKind;
  /** Raw bytes. Deliberately not a File or Blob — those are DOM types. */
  data: Uint8Array;
  mimeType: string;
  /** Epoch milliseconds. Capture time, not upload time — the timeline depends on it. */
  capturedAt: number;
  filename?: string;
  durationMs?: number;
}

export interface CaptureProvider {
  isSupported(kind: CaptureKind): Promise<boolean>;
  requestPermission(kind: CaptureKind): Promise<boolean>;
  capturePhoto(): Promise<CapturedMedia | null>;
  startAudioRecording(): Promise<void>;
  stopAudioRecording(): Promise<CapturedMedia | null>;
}
