"""Feed validation, snapshotting and activation with last-good fallback.

Check results (distinct states, BR-05):
  ACTIVATED          valid new snapshot became active (caller queues rescreen)
  NO_UPDATE          same fingerprint as the active snapshot (nothing queued)
  FAILED_VALIDATION  malformed file or any rejected entry; last-good stays active, coverage DEGRADED
  STALE_SOURCE       published_at not newer than the active snapshot; last-good stays active, coverage DEGRADED
Activation is strict: one rejected entry blocks activation (a silently dropped entry is a coverage gap).
"""
from __future__ import annotations

import json
from pathlib import Path

from defender.config import canonical_json, sha256_text
from defender.normalise import parse_dob

from .db import j, now

REQUIRED_TOP = ("source_id", "jurisdiction", "version", "published_at", "entries")


def validate(raw_text: str, expected_source: str | None = None) -> dict:
    errors, rejected, entries_ok = [], [], []
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"malformed JSON: {e.msg} at line {e.lineno}"], "payload": None,
                "received": None, "loaded": 0, "rejected": None, "rejected_entries": []}
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["top level is not an object"], "payload": None, "received": None,
                "loaded": 0, "rejected": None, "rejected_entries": []}
    for k in REQUIRED_TOP:
        if k not in payload:
            errors.append(f"missing top-level field {k!r}")
    if expected_source and payload.get("source_id") != expected_source:
        errors.append(f"source_id {payload.get('source_id')!r} != expected {expected_source!r}")
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    if not entries:
        errors.append("no entries")
    seen = set()
    for i, e in enumerate(entries):
        why = []
        eid = e.get("entry_id") if isinstance(e, dict) else None
        if not eid:
            why.append("missing entry_id")
        elif eid in seen:
            why.append("duplicate entry_id")
        seen.add(eid)
        names = e.get("names") if isinstance(e, dict) else None
        if not names or not any(n.get("type") == "primary" and n.get("value") for n in names):
            why.append("no primary name")
        dob = (e.get("dob") or {}).get("value") if isinstance(e, dict) else None
        if dob is not None and parse_dob(dob)["precision"] == "unparseable":
            why.append(f"unparseable DOB {dob!r}")
        if not isinstance(e, dict) or "national_id" not in e:
            why.append("missing national_id block (use null value for unknown)")
        if why:
            rejected.append({"index": i, "entry_id": eid, "reasons": why})
        else:
            entries_ok.append(eid)
    if rejected:
        errors.append(f"{len(rejected)} entr{'y' if len(rejected) == 1 else 'ies'} rejected")
    return {"valid": not errors, "errors": errors, "payload": payload, "received": len(entries),
            "loaded": len(entries_ok) if not errors else 0, "rejected": len(rejected), "rejected_entries": rejected}


def fingerprint(payload: dict) -> str:
    return sha256_text(canonical_json(payload))


def _entry_map(payload):
    return {e["entry_id"]: e for e in payload["entries"]}


def diff(old: dict | None, new: dict) -> dict:
    if old is None:
        return {"added": sorted(_entry_map(new)), "amended": [], "removed": []}
    o, n = _entry_map(old), _entry_map(new)
    amended = []
    for k in sorted(set(o) & set(n)):
        changed = sorted(f for f in set(o[k]) | set(n[k]) if canonical_json(o[k].get(f)) != canonical_json(n[k].get(f)))
        if changed:
            amended.append({"entry_id": k, "changed_fields": changed})
    return {"added": sorted(set(n) - set(o)), "amended": amended, "removed": sorted(set(o) - set(n))}


def active(conn, source_id: str):
    row = conn.execute("SELECT * FROM active_snapshots WHERE source_id=?", (source_id,)).fetchone()
    if not row or not row["snapshot_id"]:
        return None
    return conn.execute("SELECT * FROM snapshots WHERE snapshot_id=?", (row["snapshot_id"],)).fetchone()


def load_feed(conn, path: Path, expected_source: str | None = None, jurisdiction: str | None = None) -> dict:
    path = Path(path)
    at = now(conn)
    raw = path.read_text(encoding="utf-8")
    v = validate(raw, expected_source)
    source_id = (v["payload"] or {}).get("source_id") or expected_source
    jur = (v["payload"] or {}).get("jurisdiction") or jurisdiction
    cur = active(conn, source_id) if source_id else None

    def record_check(result, snapshot_id, detail):
        conn.execute("INSERT INTO feed_checks(source_id,attempted,result,snapshot_id,detail,at) VALUES(?,?,?,?,?,?)",
                     (source_id, path.name, result, snapshot_id, json.dumps(detail, ensure_ascii=False), at))
        coverage = "OK" if result in ("ACTIVATED", "NO_UPDATE") else (
            f"DEGRADED: serving last-good {cur['snapshot_id']}" if cur else "NO_COVERAGE: no validated snapshot")
        if result == "ACTIVATED":
            conn.execute("""INSERT INTO active_snapshots(source_id,jurisdiction,snapshot_id,activated_at,last_check_at,last_check_result,last_success_at,coverage)
                            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET snapshot_id=excluded.snapshot_id,
                            activated_at=excluded.activated_at,last_check_at=excluded.last_check_at,last_check_result=excluded.last_check_result,
                            last_success_at=excluded.last_success_at,coverage=excluded.coverage,rescreen_completed_at=NULL""",
                         (source_id, jur, snapshot_id, at, at, result, at, coverage))
        else:
            conn.execute("""INSERT INTO active_snapshots(source_id,jurisdiction,snapshot_id,last_check_at,last_check_result,last_success_at,coverage)
                            VALUES(?,?,NULL,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_check_at=excluded.last_check_at,
                            last_check_result=excluded.last_check_result, coverage=excluded.coverage,
                            last_success_at=CASE WHEN excluded.last_check_result='NO_UPDATE' THEN excluded.last_check_at ELSE active_snapshots.last_success_at END""",
                         (source_id, jur, at, result, at if result == "NO_UPDATE" else None, coverage))
        return {"result": result, "source_id": source_id, "jurisdiction": jur, "file": path.name,
                "snapshot_id": snapshot_id, "active_snapshot_id": (snapshot_id if result == "ACTIVATED" else (cur["snapshot_id"] if cur else None)),
                "coverage": coverage, **detail}

    conn.execute("BEGIN")
    try:
        if not v["valid"]:
            out = record_check("FAILED_VALIDATION", None, {"errors": v["errors"], "received": v["received"],
                                                           "loaded": 0, "rejected": v["rejected"], "rejected_entries": v["rejected_entries"]})
        else:
            payload = v["payload"]
            fp = fingerprint(payload)
            if cur and cur["fingerprint"] == fp:
                out = record_check("NO_UPDATE", cur["snapshot_id"], {"received": v["received"], "loaded": 0, "rejected": 0,
                                                                     "note": "identical to active snapshot; nothing queued"})
            elif cur and payload["published_at"] <= cur["published_at"]:
                out = record_check("STALE_SOURCE", None, {"errors": [f"published_at {payload['published_at']} is not newer than active {cur['published_at']}"],
                                                          "received": v["received"], "loaded": 0, "rejected": 0})
            else:
                sid = f"SNAP-{payload['source_id']}-{payload['version']}-{fp[:8]}"
                d = diff(j(cur["payload"]) if cur else None, payload)
                conn.execute("""INSERT OR IGNORE INTO snapshots(snapshot_id,source_id,jurisdiction,version,fingerprint,published_at,received_at,status,
                                entries_received,entries_loaded,entries_rejected,validation,diff,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (sid, payload["source_id"], payload["jurisdiction"], payload["version"], fp, payload["published_at"], at, "ACTIVE",
                              v["received"], v["loaded"], 0, json.dumps({"valid": True}), json.dumps(d), json.dumps(payload, ensure_ascii=False)))
                if cur:
                    conn.execute("UPDATE snapshots SET status='SUPERSEDED' WHERE snapshot_id=?", (cur["snapshot_id"],))
                out = record_check("ACTIVATED", sid, {"received": v["received"], "loaded": v["loaded"], "rejected": 0,
                                                      "fingerprint": fp, "previous_snapshot_id": cur["snapshot_id"] if cur else None, "diff": d})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return out


def status(conn) -> list[dict]:
    out = []
    for row in conn.execute("SELECT * FROM active_snapshots ORDER BY jurisdiction"):
        snap = conn.execute("SELECT * FROM snapshots WHERE snapshot_id=?", (row["snapshot_id"],)).fetchone() if row["snapshot_id"] else None
        checks = [dict(r) | {"detail": j(r["detail"])} for r in conn.execute(
            "SELECT check_id,attempted,result,snapshot_id,detail,at FROM feed_checks WHERE source_id=? ORDER BY check_id", (row["source_id"],))]
        out.append({
            "source_id": row["source_id"], "jurisdiction": row["jurisdiction"], "active_snapshot_id": row["snapshot_id"],
            "version": snap["version"] if snap else None, "fingerprint": snap["fingerprint"] if snap else None,
            "published_at": snap["published_at"] if snap else None, "activated_at": row["activated_at"],
            "last_check_at": row["last_check_at"], "last_check_result": row["last_check_result"],
            "last_successful_check_at": row["last_success_at"], "coverage": row["coverage"],
            "rescreen_completed_at": row["rescreen_completed_at"],
            "reconciliation": {"received": snap["entries_received"], "loaded": snap["entries_loaded"], "rejected": snap["entries_rejected"]} if snap else None,
            "diff_vs_previous": j(snap["diff"]) if snap else None,
            "checks": checks,
        })
    return out
