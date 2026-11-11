# Faster on-device OCR: stop running two recognisers per image

Status: IMPLEMENTED 2026-11-11 (approved: "the ocr one"). Option B, Devanagari only.

## Problem
`TextExtractionPlugin.recognise()` runs the ML Kit Latin recogniser and the Devanagari
recogniser on every image and every PDF page, then keeps one result. The first scan of
~1,700 files on a Galaxy S23 FE took about an hour. Separately, any image with at least 5
Devanagari characters drops the Latin result entirely, which can hurt bilingual documents
(code review finding, 2026-11-11).

## Question to answer with numbers, not a guess
Can one recogniser do both jobs? ML Kit's Devanagari model is documented to read Latin text
too. Candidates: (A) current two-pass, (B) Devanagari only, (C) Latin only, (D) Latin first and
Devanagari only when needed.

## Method
1. Debug-only plugin method `benchmark({path})` (refuses on release builds) returning each
   recogniser's text and milliseconds.
2. Ground truth on an emulator: generated images with known text (English, English plus
   numbers, Hindi, Marathi, bilingual, rotated, noisy). Metric: word-level accuracy per mode.
3. Real phone, metrics only (never print text): per file, milliseconds per recogniser, word
   count each, and word-set overlap between the two. Aggregated by script share.
4. Pick the rule that keeps accuracy within noise of the current one and cuts time, then
   implement it, rebuild, and rescan a sample to confirm.

## Not in scope
A new OCR engine, cloud OCR, layout analysis, or changing the PDF page cap.

## Gates
`pnpm typecheck && pnpm build`, API tests unchanged, Android build, on-device check.

## Results (2026-11-11)
Ground truth, 9 generated images (emulator), word accuracy:
| | Latin only | Devanagari only | old rule (both, pick one) |
|---|---|---|---|
| English x4 (bill, receipt, small print, noisy) | 1.00 | 1.00 | 1.00 |
| Hindi / Marathi x4 | 0.00 | 0.86-1.00 | 0.86-1.00 |
| bilingual card | 0.86 | 1.00 | 1.00 |
| mean | 0.54 | 0.97 | 0.97 |

Real phone (Galaxy S23 FE), 70 photos (51 jpeg, 14 heic, 5 png) + 12 PDFs, metrics only:
- Latin found text in 23 images and Devanagari in 24; text found ONLY by Latin: 0, ONLY by
  Devanagari: 1. In PDF first pages: 12 and 12, none exclusive.
- Where both read text: 2,943 vs 2,938 words in images, 2,055 vs 2,089 in PDF pages. Word-set
  overlap 0.74 (images) and 0.84 (PDFs): the engines disagree on ~20% of words, and this test
  cannot say which is right without ground truth on real photos.
- Per image: Latin 198 ms, Devanagari 195 ms, both 393 ms. PDF first page: 410, 462, 873 ms.
- 14 of 82 files contained at least 5 Devanagari characters.

## Decision
Devanagari model only, no Latin fallback (it never found text the other missed). OCR cost per
image and page drops about 50%. Single-pass extraction on the same real sample: images mean
452 ms per file including decode and hashing (median 330), PDFs mean about 5.0 s per file
(multi-page, up to 40 pages); same number of files with text as before (24 images, 12 PDFs);
known-text accuracy unchanged at 0.97. The Latin recogniser is built only for the debug
benchmark, which refuses to run on release builds.

## Risk, stated
The 20% word disagreement means English photos will read a little differently than before.
If searches that used to work start missing, compare against the old rule with the debug
`benchmark` method on those files before changing anything else.
