/**
 * Identifier masking on the device, before extracted text is sent anywhere.
 *
 * A port of apps/api/src/memora/services/masking.py: the same patterns and the same
 * Verhoeff check, so that both sides agree on what counts as an identifier. The server
 * masks again whatever it receives; this copy exists so a raw Aadhaar or PAN number never
 * leaves the phone at all.
 *
 * A false positive is worse than a miss: masking a receipt ID silently destroys findable
 * text. So Aadhaar needs a valid Verhoeff check digit, not just twelve digits in a row.
 */

export const AADHAAR_TOKEN = '[AADHAAR_NUMBER]';
export const PAN_TOKEN = '[PAN_NUMBER]';
export const VID_TOKEN = '[AADHAAR_VID]';

const AADHAAR = /(?<!\d)([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})(?!\d)/g;
// The 16-digit Aadhaar Virtual ID. Same Verhoeff check digit, as sensitive as the number.
const VID = /(?<!\d)([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})[ -]?(\d{4})(?!\d)/g;
const PAN = /(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])/g;

const D = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
] as const;

const P = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
] as const;

export function verhoeffValid(digits: string): boolean {
  if (!/^\d+$/.test(digits)) return false;
  let checksum = 0;
  const reversed = [...digits].reverse();
  reversed.forEach((digit, i) => {
    checksum = D[checksum]![P[i % 8]![Number(digit)]!]!;
  });
  return checksum === 0;
}

interface Span {
  start: number;
  end: number;
  token: string;
}

function findSpans(text: string): Span[] {
  const spans: Span[] = [];
  for (const match of text.matchAll(AADHAAR)) {
    if (verhoeffValid(`${match[1]}${match[2]}${match[3]}`)) {
      spans.push({ start: match.index!, end: match.index! + match[0].length, token: AADHAAR_TOKEN });
    }
  }
  for (const match of text.matchAll(VID)) {
    if (verhoeffValid(`${match[1]}${match[2]}${match[3]}${match[4]}`)) {
      spans.push({ start: match.index!, end: match.index! + match[0].length, token: VID_TOKEN });
    }
  }
  for (const match of text.matchAll(PAN)) {
    spans.push({ start: match.index!, end: match.index! + match[0].length, token: PAN_TOKEN });
  }
  return spans.sort((a, b) => a.start - b.start);
}

export function containsIdentifier(text: string): boolean {
  return findSpans(text).length > 0;
}

/** Replace Aadhaar and PAN numbers with type tokens; overlapping matches keep the first. */
export function maskIdentifiers(text: string): { text: string; masked: number } {
  const pieces: string[] = [];
  let cursor = 0;
  let masked = 0;
  for (const span of findSpans(text)) {
    if (span.start < cursor) continue;
    pieces.push(text.slice(cursor, span.start), span.token);
    cursor = span.end;
    masked++;
  }
  pieces.push(text.slice(cursor));
  return { text: pieces.join(''), masked };
}
