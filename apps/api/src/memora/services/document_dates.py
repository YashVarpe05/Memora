"""Conservative dates from document headings and explicit query months."""

import calendar
import re
from datetime import UTC, datetime

MONTHS = {
    "january": 1,
    "जनवरी": 1,
    "जानेवारी": 1,
    "february": 2,
    "फरवरी": 2,
    "फेब्रुवारी": 2,
    "march": 3,
    "मार्च": 3,
    "april": 4,
    "अप्रैल": 4,
    "एप्रिल": 4,
    "may": 5,
    "मई": 5,
    "मे": 5,
    "june": 6,
    "जून": 6,
    "july": 7,
    "जुलाई": 7,
    "जुलै": 7,
    "august": 8,
    "अगस्त": 8,
    "ऑगस्ट": 8,
    "september": 9,
    "सितंबर": 9,
    "सप्टेंबर": 9,
    "october": 10,
    "अक्टूबर": 10,
    "ऑक्टोबर": 10,
    "november": 11,
    "नवंबर": 11,
    "नोव्हेंबर": 11,
    "december": 12,
    "दिसंबर": 12,
    "डिसेंबर": 12,
}


def month_window(text: str, today: datetime) -> tuple[datetime, datetime] | None:
    lowered = text.casefold()
    for name, month in MONTHS.items():
        if re.search(r"(?<!\w)" + name + r"(?!\w)", lowered):
            year = re.search(r"\b(20\d{2})\b", lowered)
            value = int(year[1]) if year else today.year - (month > today.month)
            return (
                datetime(value, month, 1, tzinfo=UTC),
                datetime(
                    value, month, calendar.monthrange(value, month)[1], 23, 59, 59, tzinfo=UTC
                ),
            )
    return None


def document_date(text: str) -> datetime | None:
    # Require a label for ambiguous numeric dates; do not mistake an ID number or DOB
    # elsewhere on a card for the document date.
    match = re.search(
        r"(?:date|dated|दिनांक|तारीख)\s*[:\-]?\s*(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", text, re.I
    )
    if match:
        try:
            return datetime(int(match[3]), int(match[2]), int(match[1]), tzinfo=UTC)
        except ValueError:
            return None
    if re.search(r"\b20\d{2}\b", text):
        window = month_window(text, datetime.now(UTC))
        if window:
            return window[0]
    return None
