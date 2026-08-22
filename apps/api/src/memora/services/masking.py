"""Identifier masking.

PRODUCT.md, architectural rule 2: Aadhaar and PAN numbers are masked before any text
leaves the machine. OCR of an identity document produces the number as plain text, and
that text is then embedded through a hosted API.

Two design decisions worth knowing before changing anything here.

**MaskedText cannot be constructed outside this module.** The embedder accepts
``MaskedText`` and nothing else, so there is no ordering of calls that reaches a hosted
API with raw extracted text. Masking is not a step in a pipeline that a later change can
reorder around - it is the only door. Same shape as ``BaseRepository``, which cannot be
built without a user_id.

**A false positive is worse than a miss.** Masking a receipt ID or a phone number
silently destroys retrievable text, and nobody notices until a search fails months later.
So Aadhaar detection validates the Verhoeff check digit rather than matching any twelve
digits in a row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

AADHAAR_TOKEN = "[AADHAAR_NUMBER]"
PAN_TOKEN = "[PAN_NUMBER]"

# Aadhaar: twelve digits, optionally grouped in fours. Never starts with 0 or 1 (UIDAI).
# The lookarounds stop a match inside a longer digit run.
_AADHAAR_RE = re.compile(r"(?<!\d)([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})(?!\d)")

# PAN: five letters, four digits, one letter. Distinctive enough that shape alone is a
# safe test - and a missed PAN leaks, so this deliberately does not also require the
# fourth character to be a valid entity-type code.
_PAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])")

# Verhoeff tables. Aadhaar carries a Verhoeff check digit; validating it is what separates
# a real Aadhaar number from any other twelve-digit string.
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(digits: str) -> bool:
    """True when `digits` carries a correct Verhoeff check digit."""
    if not digits.isdigit():
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        checksum = _D[checksum][_P[i % 8][int(digit)]]
    return checksum == 0


@dataclass(frozen=True)
class Detection:
    """What was masked and where. Deliberately never carries the value.

    CLAUDE.md: never log tokens or secrets. A Detection is safe to log; the matched
    text is not, which is why it is not stored here at all.
    """

    kind: str
    start: int
    end: int


# Module-private. MaskedText checks identity against this, so the only way to mint one
# is mask_identifiers() below - importing the key by name is a deliberate act, not an
# accident, which is the same line BaseRepository draws.
_MINT = object()


@dataclass(frozen=True)
class MaskedText:
    """Text that has been through masking. The only type the embedder accepts."""

    _key: object = field(repr=False)
    value: str
    detections: tuple[Detection, ...]

    def __post_init__(self) -> None:
        if self._key is not _MINT:
            raise TypeError(
                "MaskedText cannot be constructed directly - call mask_identifiers(). "
                "Anything reaching the embedder must have passed through masking."
            )

    def __str__(self) -> str:
        return self.value

    def __len__(self) -> int:
        return len(self.value)

    @property
    def was_masked(self) -> bool:
        return bool(self.detections)


def mask_identifiers(text: str) -> MaskedText:
    """Replace Aadhaar and PAN numbers with type tokens.

    The token is a type name rather than partial masking. `XXXX XXXX 9012` still leaks
    four digits and the format, while `[AADHAAR_NUMBER]` makes the document *more*
    findable - "aadhaar" becomes a term in the index, which is what hero query 1
    actually searches for.
    """
    detections: list[Detection] = []
    pieces: list[str] = []
    cursor = 0

    spans: list[tuple[int, int, str, str]] = []

    for match in _AADHAAR_RE.finditer(text):
        digits = "".join(match.groups())
        if verhoeff_valid(digits):
            spans.append((match.start(), match.end(), "aadhaar", AADHAAR_TOKEN))

    for match in _PAN_RE.finditer(text):
        spans.append((match.start(), match.end(), "pan", PAN_TOKEN))

    for start, end, kind, token in sorted(spans):
        if start < cursor:  # overlapping match, keep the first
            continue
        pieces.append(text[cursor:start])
        pieces.append(token)
        detections.append(Detection(kind=kind, start=start, end=end))
        cursor = end

    pieces.append(text[cursor:])
    return MaskedText(_MINT, "".join(pieces), tuple(detections))


def mask_all(texts: list[str]) -> list[MaskedText]:
    return [mask_identifiers(t) for t in texts]
