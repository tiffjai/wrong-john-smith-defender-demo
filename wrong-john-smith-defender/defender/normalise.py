"""Deterministic normalisation. Unknown stays unknown: missing input -> None, never imputed."""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})


def normalise_text(value):
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value)).casefold()
    s = re.sub(r"[^\w\s]|_", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def alias_lookup_key(value):
    n = normalise_text(value)
    return n.replace(" ", "") if n else None


def parse_dob(raw):
    """Parse a raw date-of-birth string and report its precision.

    Supported raw formats: YYYY-MM-DD, YYYY-MM, YYYY, DD/MM/YYYY (day-first, documented
    assumption), 'DD Mon YYYY', 'Mon YYYY'. Anything else is 'unparseable' and treated as
    unknown by every comparison (never guessed).
    """
    out = {"raw": raw, "value": None, "precision": "unknown", "year": None, "month": None, "day": None}
    if raw is None or str(raw).strip() == "":
        return out
    s = str(raw).strip()
    y = m = d = None
    if (g := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)):
        y, m, d = int(g[1]), int(g[2]), int(g[3])
    elif (g := re.fullmatch(r"(\d{4})-(\d{2})", s)):
        y, m = int(g[1]), int(g[2])
    elif (g := re.fullmatch(r"(\d{4})", s)):
        y = int(g[1])
    elif (g := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)):
        d, m, y = int(g[1]), int(g[2]), int(g[3])
    elif (g := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", s)):
        d, m, y = int(g[1]), _MONTHS.get(g[2].lower()), int(g[3])
    elif (g := re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{4})", s)):
        m, y = _MONTHS.get(g[1].lower()), int(g[2])
    if y is None or (m is None and d is not None) or (m is not None and not 1 <= m <= 12):
        out["precision"] = "unparseable"
        return out
    try:
        if d is not None:
            date(y, m, d)
    except ValueError:
        out["precision"] = "unparseable"
        return out
    out.update(year=y, month=m, day=d)
    if d is not None:
        out.update(precision="full", value=f"{y:04d}-{m:02d}-{d:02d}")
    elif m is not None:
        out.update(precision="year_month", value=f"{y:04d}-{m:02d}")
    else:
        out.update(precision="year", value=f"{y:04d}")
    return out
