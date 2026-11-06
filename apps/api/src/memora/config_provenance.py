"""Where each setting actually came from.

**A value that is set is not a value that is used.** pydantic-settings resolves in a
fixed order - process environment first, then `.env`, then the field default - so a
Windows user variable silently shadows the file. On 2026-08-26 that meant a key written
into `.env` was inert while a different one from `HKCU:\\Environment` was doing the work,
with no symptom anywhere.

For a key that is only a credential, that is confusing. For `gemini_model` it is
dangerous: the pin exists specifically to stop silent model substitution, after
`gemini-flash-lite-latest` was swapped in to dodge a quota limit and dropped Recall@1 to
0.789 - below the 0.842 achieved by using no extractor at all. A pin overridden by a shell
variable reintroduces exactly the contamination the pin prevents, and the report would
still say the model was pinned.

So the source is reported, not assumed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from memora.paths import anchored

# Settings worth reporting. Credentials and anything a measurement depends on.
WATCHED = ("gemini_api_key", "gemini_model", "database_url", "stage1_cache")

SECRET = ("gemini_api_key", "jwt_secret", "token_encryption_key")


@dataclass(frozen=True)
class Origin:
    field: str
    source: str  # "shell environment" | ".env" | "default"
    display: str
    shadowed: bool  # set in .env AND overridden by the environment


def _env_file_keys() -> set[str]:
    """Which names the .env file actually defines. Read directly, not through pydantic."""
    for candidate in (Path(".env"), anchored(".env")):
        try:
            if not candidate.is_file():
                continue
            names = set()
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if value.strip():
                    names.add(name.strip().lower())
            return names
        except OSError:
            continue
    return set()


def _mask(field: str, value: object) -> str:
    if value is None:
        return "unset"
    text = str(value)
    if field == "database_url":
        from sqlalchemy.engine import make_url

        return make_url(text).render_as_string(hide_password=True)
    if field in SECRET:
        # Enough to tell two keys apart, not enough to use. Both length and prefix,
        # because the two keys in play differ in both.
        return f"{text[:6]}... ({len(text)} chars)"
    return text


def describe(settings: object) -> list[Origin]:
    in_file = _env_file_keys()
    origins: list[Origin] = []
    for field in WATCHED:
        value = getattr(settings, field, None)
        in_shell = field.upper() in os.environ
        if in_shell:
            source = "shell environment"
        elif field in in_file:
            source = ".env"
        else:
            source = "default"
        origins.append(
            Origin(
                field=field,
                source=source,
                display=_mask(field, value),
                # The case worth shouting about: the file says one thing and is losing.
                shadowed=in_shell and field in in_file,
            )
        )
    return origins


def report(settings: object) -> list[str]:
    """Lines for the startup log. Shadowed settings are called out, not just listed."""
    lines = ["config sources:"]
    for origin in describe(settings):
        flag = "  <-- .env value is IGNORED, shell wins" if origin.shadowed else ""
        lines.append(f"  {origin.field:<22} {origin.source:<18} {origin.display}{flag}")
    return lines
