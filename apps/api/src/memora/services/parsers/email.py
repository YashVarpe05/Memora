"""RFC822 (.eml) — headers as metadata, body chunked as prose.

An email body is prose, so the existing token window is right for it. What a token window
cannot do is make the headers searchable separately: "the PDF a professor sent" filters on
sender, and a sender buried inside chunk text is a semantic match rather than a filter.

Attachments are deliberately not handled here. Hero query 2 needs the *attachment*
findable, not the body mentioning it, which means an attachment becomes its own Memory
linked to the email - a phase of its own, recorded in the roadmap rather than half-done.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    sender: str
    recipients: list[str]
    sent_at: datetime | None
    body: str
    attachment_names: list[str]


def is_email(data: bytes) -> bool:
    """Sniff for RFC822 headers rather than trusting the extension."""
    head = data[:2048].lower()
    return b"\nfrom:" in head or head.startswith(b"from:") or b"\nmessage-id:" in head


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = _HTML_TAG.sub(" ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(entity, char)
    return _WS.sub(" ", text)


def parse_email(data: bytes) -> ParsedEmail:
    message = BytesParser(policy=policy.default).parsebytes(data)

    sent_at: datetime | None = None
    raw_date = message.get("Date")
    if raw_date:
        try:
            sent_at = parsedate_to_datetime(raw_date)
            if sent_at and sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            sent_at = None

    # text/plain in preference to HTML: the plain part is what the sender wrote, and
    # stripping tags off HTML always loses something.
    body = ""
    part = message.get_body(preferencelist=("plain", "html"))
    if part is not None:
        content = part.get_content()
        body = content if part.get_content_subtype() == "plain" else _strip_html(content)

    attachments = [
        part.get_filename()
        for part in message.iter_attachments()
        if part.get_filename()
    ]

    recipients = [
        value
        for header in ("To", "Cc")
        for value in (message.get(header) or "").split(",")
        if value.strip()
    ]

    return ParsedEmail(
        subject=(message.get("Subject") or "").strip() or "(no subject)",
        sender=(message.get("From") or "").strip(),
        recipients=[r.strip() for r in recipients],
        sent_at=sent_at,
        body=body.strip(),
        attachment_names=attachments,
    )
