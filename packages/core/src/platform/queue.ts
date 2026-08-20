/**
 * Offline upload queue.
 *
 * Capture happens on a phone, often on bad campus wifi. A capture must survive being
 * taken offline: it is queued locally and drained when connectivity returns.
 */
export type QueueItemStatus = 'pending' | 'uploading' | 'failed' | 'done';

export interface QueuedUpload {
  id: string;
  kind: 'image' | 'audio' | 'file';
  mimeType: string;
  filename: string;
  sizeBytes: number;
  createdAt: number;
  status: QueueItemStatus;
  attempts: number;
  lastError?: string;
}

export interface OfflineQueue {
  enqueue(item: Omit<QueuedUpload, 'id' | 'status' | 'attempts' | 'createdAt'>, data: Uint8Array): Promise<QueuedUpload>;
  list(): Promise<QueuedUpload[]>;
  read(id: string): Promise<Uint8Array | null>;
  markStatus(id: string, status: QueueItemStatus, error?: string): Promise<void>;
  remove(id: string): Promise<void>;
  pendingCount(): Promise<number>;
}
