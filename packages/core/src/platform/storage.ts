/**
 * Token storage.
 *
 * CLAUDE.md: auth is Bearer-token. The access token lives in memory only; the refresh
 * token goes through this interface. Web implements it with IndexedDB, a Capacitor
 * build with the native keychain. Neither detail leaks past this boundary.
 */
export interface SecureStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
  clear(): Promise<void>;
}

export const StorageKeys = {
  RefreshToken: 'memora.refresh_token',
  ActiveUserId: 'memora.active_user_id',
} as const;

export type StorageKey = (typeof StorageKeys)[keyof typeof StorageKeys];
