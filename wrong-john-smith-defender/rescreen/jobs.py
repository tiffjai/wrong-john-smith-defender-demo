"""ONE rescreen job used for validated list changes, material KYC changes, manual runs and the daily sweep.

Idempotent: alerts are unique per (customer, source, stable entry); events carry idempotency keys;
a failed job can be retried without duplicate alerts or events.
"""
from __future__ import annotations

import json

from . import basis as basis_mod
from . import kyc
from .config import load_policy, load_scoring
from .db import add_event, j, now, stable_id
from .scoring import score

TRIGGERS = ("initial_screening", "list_change", "kyc_change", "manual", "daily_sweep", "retry")


class SimulatedJobFailure(RuntimeError):
    pass


def case_id_for(customer: dict, entry_id: str) -> str:
    suffix = customer.get("case_suffix") or customer["customer_id"].split("-")[-1]
    return f"RESCREEN-{suffix}" if entry_id == "DEMO-WL-410" else f"RESCREEN-{suffix}-{entry_id}"


def active_entries(conn) -> tuple[list[dict], list[str]]:
    entries, snaps = [], []
    for row in conn.execute("SELECT a.source_id, a.jurisdiction, s.snapshot_id, s.payload FROM active_snapshots a "
                            "JOIN snapshots s ON s.snapshot_id=a.snapshot_id ORDER BY a.source_id"):
        snaps.append(row["snapshot_id"])
        for e in json.loads(row["payload"])["entries"]:
            entries.append({"data": e, "source_id": row["source_id"], "snapshot_id": row["snapshot_id"], "jurisdiction": row["jurisdiction"]})
    return entries, snaps


def _evidence_by_field(result):
    out = {}
    for side in ("customer_evidence", "entry_evidence"):
        for it in result[side]:
            out.setdefault((it["subject_type"], it["field"]), []).append({"evidence_id": it["evidence_id"], "value": it["observed_value"]})
    return out


def changed_fields(prev: dict, cur: dict) -> list[dict]:
    a, b = _evidence_by_field(prev), _evidence_by_field(cur)
    out = []
    for k in sorted(set(a) | set(b)):
        ia, ib = sorted(x["evidence_id"] for x in a.get(k, [])), sorted(x["evidence_id"] for x in b.get(k, []))
        if ia != ib:
            out.append({"subject_type": k[0], "field": k[1], "before": a.get(k, []), "after": b.get(k, []),
                        "before_snapshot_id": prev["snapshot_id"] if k[0] == "list_entry" else prev["kyc_snapshot_id"],
                        "after_snapshot_id": cur["snapshot_id"] if k[0] == "list_entry" else cur["kyc_snapshot_id"],
                        "before_kyc_version": prev["kyc_version"], "after_kyc_version": cur["kyc_version"]})
    return out


def _process(conn, r: dict, job_id: str, customer: dict) -> str:
    key = (r["customer_id"], r["source_id"], r["entry_id"])
    alert = conn.execute("SELECT * FROM alerts WHERE customer_id=? AND source_id=? AND entry_id=?", key).fetchone()
    if not alert and not r["raise_alert"]:
        return "no_hit"
    at = now(conn)
    outcome = "rescreened"
    if not alert:
        alert_id = stable_id("ALR-", *key)
        case_id = case_id_for(customer, r["entry_id"])
        priority = "high" if r["guard"]["decision"] == "REVIEW" or r["splink"]["decision"] == "LINK" else "normal"
        reason = (f"name-only {r['name_only']['decision']} ({r['name_only']['score']}), Splink {r['splink']['decision']} "
                  f"(P={r['splink']['match_probability']:.3f}), guard {r['guard']['outcome']}")
        conn.execute("""INSERT INTO alerts(alert_id,case_id,customer_id,source_id,entry_id,state,owner,priority,reason,created_at,updated_at,
                        reopen_count,latest_snapshot_id,latest_kyc_version) VALUES(?,?,?,?,?,'OPEN',NULL,?,?,?,?,0,NULL,NULL)""",
                     (alert_id, case_id, *key, priority, reason, at, at))
        add_event(conn, (alert_id,), "ALERT_CREATED", {"key": list(key), "reason": reason, "snapshot_id": r["snapshot_id"]},
                  alert_id, case_id, job_id)
        alert = conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchone()
        outcome = "alert_created"
    aid, cid = alert["alert_id"], alert["case_id"]
    stored = {k: v for k, v in r.items()}
    conn.execute("INSERT OR IGNORE INTO screening_results(alert_id,snapshot_id,kyc_version,job_id,result,at) VALUES(?,?,?,?,?,?)",
                 (aid, r["snapshot_id"], r["kyc_version"], job_id, json.dumps(stored, ensure_ascii=False), at))
    prev_key = (alert["latest_snapshot_id"], alert["latest_kyc_version"])
    if prev_key[0] and prev_key != (r["snapshot_id"], r["kyc_version"]):
        prev = j(conn.execute("SELECT result FROM screening_results WHERE alert_id=? AND snapshot_id=? AND kyc_version=?",
                              (aid, *prev_key)).fetchone()["result"])
        ch = changed_fields(prev, r)
        if ch:
            add_event(conn, (aid, *prev_key, r["snapshot_id"], r["kyc_version"]), "MATERIAL_CHANGE",
                      {"changed_fields": ch, "from": list(prev_key), "to": [r["snapshot_id"], r["kyc_version"]]}, aid, cid, job_id)
    add_event(conn, (aid, r["snapshot_id"], r["kyc_version"]), "SCREENED",
              {"snapshot_id": r["snapshot_id"], "kyc_version": r["kyc_version"], "raise_alert": r["raise_alert"],
               "name_only": r["name_only"]["decision"], "splink": r["splink"]["decision"], "guard": r["guard"]["decision"],
               "match_probability": r["splink"]["match_probability"]}, aid, cid, job_id)
    if alert["state"] == "RESOLVED":
        dec = conn.execute("SELECT * FROM decisions WHERE case_id=? AND decision='APPROVED' AND validity='CURRENT' "
                           "ORDER BY at DESC LIMIT 1", (cid,)).fetchone()
        if dec:
            ev = basis_mod.evaluate(j(dec["basis"]), r["customer_evidence"], r["entry_evidence"])
            idem = (aid, dec["decision_id"], r["snapshot_id"], r["kyc_version"])
            if ev["holds"]:
                add_event(conn, idem, "APPROVAL_BASIS_HOLDS", {"decision_id": dec["decision_id"], "evaluation": ev}, aid, cid, job_id)
                outcome = "basis_holds"
            else:
                prev = j(conn.execute("SELECT result FROM screening_results WHERE alert_id=? AND snapshot_id=? AND kyc_version=?",
                                      (aid, *prev_key)).fetchone()["result"]) if prev_key[0] else None
                payload = {"decision_id": dec["decision_id"], "basis": j(dec["basis"]), "evaluation": ev,
                           "changed_fields": changed_fields(prev, r) if prev else [],
                           "next_step": "Return to a human: request independent evidence or escalate."}
                if add_event(conn, idem, "REOPENED", payload, aid, cid, job_id):
                    prop = conn.execute("SELECT analyst FROM proposals WHERE proposal_id=?", (dec["proposal_id"],)).fetchone()
                    conn.execute("UPDATE alerts SET state='OPEN', reopen_count=reopen_count+1, priority='high', owner=?, updated_at=? WHERE alert_id=?",
                                 (prop["analyst"] if prop else None, at, aid))
                    conn.execute("UPDATE decisions SET validity='INVALIDATED', invalidated_by=? WHERE decision_id=?",
                                 (stable_id("EVT-", "REOPENED", *idem), dec["decision_id"]))
                    conn.execute("INSERT INTO case_actions(action_id,case_id,actor,role,action,from_state,to_state,comment,payload,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (stable_id("ACT-", cid, "reopen", *idem), cid, "system", "system", "REOPEN", "RESOLVED", "OPEN",
                                  f"Approval basis {ev['status']}: {ev['reason']}", json.dumps(payload, ensure_ascii=False), at))
                outcome = "reopened"
    elif not r["raise_alert"]:
        add_event(conn, (aid, r["snapshot_id"], r["kyc_version"]), "NO_LONGER_ALERTING",
                  {"note": "pair no longer meets the alert rule; state unchanged, a human must close it"}, aid, cid, job_id)
    conn.execute("UPDATE alerts SET latest_snapshot_id=?, latest_kyc_version=?, updated_at=? WHERE alert_id=?",
                 (r["snapshot_id"], r["kyc_version"], at, aid))
    return outcome


def run_rescreen(conn, trigger: str, customer_ids=None, fail_after: int | None = None, retry_of: str | None = None) -> dict:
    if trigger not in TRIGGERS:
        raise ValueError(trigger)
    scoring, policy = load_scoring(), load_policy()
    entries, snaps = active_entries(conn)
    customers = kyc.current(conn, customer_ids)
    started = now(conn)
    n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] + 1
    job_id = f"JOB-{n:04d}-{trigger}"
    scope = {"customers": [c["data"]["customer_id"] for c in customers], "kyc_versions": {c["data"]["customer_id"]: c["version"] for c in customers},
             "population": "all current customers" if customer_ids is None else "selected customers"}
    conn.execute("INSERT INTO jobs(job_id,trigger,scope,snapshot_ids,config_sha256,policy_sha256,status,started_at,retry_of) VALUES(?,?,?,?,?,?,?,?,?)",
                 (job_id, trigger, json.dumps(scope), json.dumps(snaps), scoring["config_sha256"], policy["policy_sha256"], "RUNNING", started, retry_of))
    counts = {"customers": len(customers), "entries": len(entries), "pairs_retrieved": 0, "no_hit": 0, "alert_created": 0,
              "rescreened": 0, "basis_holds": 0, "reopened": 0}
    by_cust = {c["data"]["customer_id"]: c["data"] for c in customers}
    try:
        results = score(customers, entries, scoring["parameters"]) if customers and entries else []
        counts["pairs_retrieved"] = len(results)
        counts["pairs_not_retrieved"] = len(customers) * len(entries) - len(results)
        for i, r in enumerate(results):
            if fail_after is not None and i >= fail_after:
                raise SimulatedJobFailure(f"simulated failure after {fail_after} result(s)")
            conn.execute("BEGIN")
            try:
                counts[_process(conn, r, job_id, by_cust[r["customer_id"]])] += 1
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        status = "COMPLETED_WITH_HITS" if any(counts[k] for k in ("alert_created", "rescreened", "basis_holds", "reopened")) else "COMPLETED_NO_HIT"
        fin = now(conn)
        conn.execute("UPDATE jobs SET status=?, finished_at=?, summary=? WHERE job_id=?", (status, fin, json.dumps(counts), job_id))
        for s in snaps:
            conn.execute("UPDATE active_snapshots SET rescreen_completed_at=? WHERE snapshot_id=?", (fin, s))
        err = None
    except Exception as e:  # recorded as a failed, replayable job
        status, err = "FAILED", f"{type(e).__name__}: {e}"
        conn.execute("UPDATE jobs SET status=?, finished_at=?, error=?, summary=? WHERE job_id=?",
                     (status, now(conn), err, json.dumps(counts), job_id))
    return {"job_id": job_id, "trigger": trigger, "status": status, "error": err, "snapshot_ids": snaps,
            "scope": scope, "counts": counts, "retry_of": retry_of}


def retry(conn, job_id: str) -> dict:
    row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row or row["status"] != "FAILED":
        raise ValueError(f"{job_id} is not a failed job")
    scope = json.loads(row["scope"])
    ids = None if scope["population"] == "all current customers" else scope["customers"]
    return run_rescreen(conn, "retry", ids, retry_of=job_id)


def daily_sweep(conn) -> dict:
    """Scheduler entry point (cron: `python -m rescreen sweep`). Same job logic as every other trigger."""
    return run_rescreen(conn, "daily_sweep")


def jobs(conn) -> list[dict]:
    return [dict(r) | {"scope": j(r["scope"]), "snapshot_ids": j(r["snapshot_ids"]), "summary": j(r["summary"])}
            for r in conn.execute("SELECT * FROM jobs ORDER BY started_at, job_id")]
