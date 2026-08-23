"""WhatsApp export (.txt) — conversation windows.

One message per chunk embeds badly: "ok" and "sent it" carry no retrievable meaning on
their own. A window reads like a conversation and is what someone actually remembers.

Windows break on a 30 minute gap or 20 messages, whichever comes first - a gap is a
topic boundary far more often than a message count is.

The line format varies by app version and phone locale, so two patterns are recognised
and a file matching neither is rejected. A silently unparsed export becomes one enormous
chunk that matches nothing, which is worse than a refused upload because nobody notices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

WINDOW_GAP = timedelta(minutes=30)
WINDOW_MESSAGES = 20

# [12/07/2026, 01:24:47] Name: text        (iOS, and Android in some locales)
_BRACKETED = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:[APap][Mm])?\]\s*"
    r"([^:]{1,60}):\s?(.*)$"
)
# 12/07/2026, 01:24 - Name: text          (Android)
_DASHED = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:[APap][Mm])?\s*-\s*"
    r"([^:]{1,60}):\s?(.*)$"
)

_SYSTEM_MARKERS = (
    "end-to-end encrypted",
    "Messages and calls are end-to-end",
    "created group",
    "changed the subject",
    "joined using this group",
)


class UnparseableChatExport(ValueError):
    """The file is not a recognised WhatsApp export."""


@dataclass(frozen=True)
class Message:
    sent_at: datetime | None
    sender: str
    text: str


@dataclass(frozen=True)
class Conversation:
    messages: list[Message]
    participants: list[str] = field(default_factory=list)

    @property
    def starts_at(self) -> datetime | None:
        return next((m.sent_at for m in self.messages if m.sent_at), None)

    @property
    def ends_at(self) -> datetime | None:
        return next((m.sent_at for m in reversed(self.messages) if m.sent_at), None)

    def render(self) -> str:
        return "\n".join(f"{m.sender}: {m.text}" for m in self.messages if m.text)


def _parse_timestamp(day: str, clock: str) -> datetime | None:
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M"):
        try:
            return datetime.strptime(f"{day} {clock}", pattern)
        except ValueError:
            continue
    return None


def _match(line: str) -> tuple[datetime | None, str, str] | None:
    for pattern in (_BRACKETED, _DASHED):
        found = pattern.match(line)
        if found:
            day, clock, sender, text = found.groups()
            return _parse_timestamp(day, clock), sender.strip(), text
    return None


def looks_like_chat(sample: str) -> bool:
    """Cheap sniff for dispatch. Parsing is what decides definitively."""
    return any(_match(line.strip()) for line in sample.splitlines()[:200] if line.strip())


def parse_chat(text: str) -> list[Message]:
    """Messages in order. Continuation lines attach to the previous message."""
    messages: list[Message] = []
    matched_any = False

    for raw in text.splitlines():
        line = raw.strip("﻿").rstrip()
        if not line:
            continue

        found = _match(line)
        if found is None:
            if messages:
                previous = messages[-1]
                messages[-1] = Message(
                    previous.sent_at, previous.sender, f"{previous.text}\n{line}".strip()
                )
            continue

        matched_any = True
        sent_at, sender, body = found
        if any(marker in body for marker in _SYSTEM_MARKERS):
            continue
        messages.append(Message(sent_at, sender, body))

    if not matched_any:
        raise UnparseableChatExport(
            "No WhatsApp message lines recognised. Expected "
            "'[DD/MM/YYYY, HH:MM:SS] Name: text' or 'DD/MM/YYYY, HH:MM - Name: text'."
        )
    return messages


def group_conversations(messages: list[Message]) -> list[Conversation]:
    """Break on a 30 minute gap or 20 messages, whichever comes first."""
    conversations: list[Conversation] = []
    current: list[Message] = []

    def flush() -> None:
        if current:
            seen: list[str] = []
            for message in current:
                if message.sender not in seen:
                    seen.append(message.sender)
            conversations.append(Conversation(messages=list(current), participants=seen))

    for message in messages:
        if current:
            previous = current[-1]
            gapped = (
                message.sent_at
                and previous.sent_at
                and message.sent_at - previous.sent_at > WINDOW_GAP
            )
            if gapped or len(current) >= WINDOW_MESSAGES:
                flush()
                current = []
        current.append(message)

    flush()
    return conversations
