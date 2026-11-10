import { registerPlugin } from '@capacitor/core';

import type { ExtractedText, TextExtractor } from '@memora/core';

interface TextExtractionNative {
  extract(options: { path: string; mimeType: string }): Promise<ExtractedText>;
}

const Native = registerPlugin<TextExtractionNative>('TextExtraction');

/**
 * On-device OCR through ML Kit. The native side rejects with an "unsupported: ..." message
 * for a type it cannot read; that becomes `null`, and every other failure is a real error.
 */
export class AndroidTextExtractor implements TextExtractor {
  async extract(path: string, mimeType: string): Promise<ExtractedText | null> {
    try {
      return await Native.extract({ path, mimeType });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.startsWith('unsupported:')) return null;
      throw error;
    }
  }
}
