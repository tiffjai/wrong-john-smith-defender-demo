"""Load synthetic records and the alias table; derive normalised matching columns."""
from __future__ import annotations

import json
from pathlib import Path

from .normalise import alias_lookup_key, normalise_text, parse_dob
from .paths import ALIAS_PATH, RECORDS_PATH


def load_alias_table(path: Path = ALIAS_PATH) -> dict:
    """Return {'groups': {alias_group: entry}, 'lookup': {lookup_key: alias_group}}."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    groups, lookup = {}, {}
    for entry in raw["aliases"]:
        if not entry.get("source_id"):
            raise ValueError(f"alias entry {entry.get('alias_group')} has no source_id; undocumented aliases are not allowed")
        groups[entry["alias_group"]] = entry
        for f in entry["forms"]:
            lookup[alias_lookup_key(f["form"])] = entry["alias_group"]
    return {"groups": groups, "lookup": lookup}


def load_records(path: Path = RECORDS_PATH, alias: dict | None = None, use_alias: bool = True) -> list[dict]:
    """Load raw records and attach a 'derived' block. Raw values are kept untouched."""
    alias = alias if alias is not None else load_alias_table()
    recs = json.loads(Path(path).read_text(encoding="utf-8"))["records"]
    out = []
    for r in recs:
        if not r.get("synthetic"):
            raise ValueError(f"{r['record_id']} is not marked synthetic")
        dob = parse_dob(r["dob"]["raw"])
        name_norm = normalise_text(r["name"]["raw"])
        group = alias["lookup"].get(alias_lookup_key(r["name"]["raw"])) if use_alias else None
        d = dict(r)
        d["derived"] = {
            "name_norm": name_norm,
            "family_key": normalise_text(r["name"].get("family")),
            "alias_group": group,
            "dob": dob,
            "country_norm": normalise_text(r["country"]["raw"]),
            "city_norm": normalise_text(r["city"]["raw"]),
        }
        out.append(d)
    return out


def by_case(records: list[dict]) -> dict[str, list[dict]]:
    cases: dict[str, list[dict]] = {}
    for r in records:
        cases.setdefault(r["case_id"], []).append(r)
    return cases
