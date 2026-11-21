"""Analyst review decisions, stored in a local JSON file (never in evidence packets)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import REVIEWS_PATH

OPTIONS = ["Undecided", "Confirm match", "Not a match", "Escalate"]


def load(path: Path | None = None) -> dict:
    path = Path(path or REVIEWS_PATH)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save(pair_id: str, case_id: str, decision: str, note: str, analyst: str = "analyst",
         path: Path | None = None) -> dict:
    if decision not in OPTIONS:
        raise ValueError(decision)
    path = Path(path or REVIEWS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load(path)
    data[pair_id] = {"case_id": case_id, "decision": decision, "note": note, "analyst": analyst,
                     "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data[pair_id]
