"""Unicode lexical matching and BM25 scoring, with no model or document prompt."""

import math
import re
import unicodedata
from collections import Counter

STOP = set(
    [
        "the",
        "a",
        "an",
        "my",
        "me",
        "i",
        "find",
        "show",
        "get",
        "of",
        "in",
        "on",
        "for",
        "from",
        "and",
        "is",
        "it",
        "this",
        "that",
        "card",
        "mera",
        "meri",
        "mere",
        "mujhe",
        "ka",
        "ki",
        "ke",
        "माझे",
        "माझा",
        "मला",
        "मेरा",
        "मेरी",
        "मुझे",
    ]
)


def words(text: str) -> list[str]:
    """Keep Indic vowel signs with their letters; Python regex word matching drops them."""
    parts: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", text.casefold()):
        if unicodedata.category(char)[0] in "LNM":
            current.append(char)
        elif char not in "\u200c\u200d" and current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return parts


def tokens(text: str) -> list[str]:
    return [t for t in words(text) if len(t) > 1 and t not in STOP]


def bm25(query: str, documents: list[str]) -> list[float]:
    terms = set(tokens(query))
    bags = [Counter(tokens(doc)) for doc in documents]
    lengths = [sum(bag.values()) for bag in bags]
    average = sum(lengths) / max(1, len(lengths)) or 1
    frequencies = {term: sum(term in bag for bag in bags) for term in terms}
    scores = []
    for bag, length in zip(bags, lengths, strict=True):
        score = 0.0
        for term in terms:
            frequency = bag[term]
            if frequency:
                idf = math.log(
                    1 + (len(bags) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                score += (
                    idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
                )
        scores.append(score)
    return scores


def excerpt(text: str, query: str, limit: int = 280) -> str:
    """Plain-text evidence around a matching word, retaining original Unicode spelling.

    Keep whitespace-delimited words whole unless a single word exceeds the limit.
    Ellipses indicate omitted text; no markup is inserted into document contents.
    """
    if limit < 1:
        raise ValueError("Excerpt limit must be positive")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    spans = list(re.finditer(r"\S+", text))
    terms = set(tokens(query))
    anchor = next(
        (i for i, span in enumerate(spans) if terms.intersection(tokens(span.group()))), 0
    )
    def fits(left: int, right: int) -> bool:
        start, end = spans[left].start(), spans[right].end()
        return end - start + bool(start) + (end < len(text)) <= limit

    left = right = anchor
    while True:
        choices = []
        if left > 0 and fits(left - 1, right):
            choices.append((spans[anchor].start() - spans[left].start(), left - 1, right))
        if right + 1 < len(spans) and fits(left, right + 1):
            choices.append((spans[right].end() - spans[anchor].end(), left, right + 1))
        if not choices:
            break
        _, left, right = min(choices)
    start, end = spans[left].start(), spans[right].end()
    end = min(end, start + max(1, limit - bool(start) - (end < len(text))))
    result = ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
    return result[:limit]
