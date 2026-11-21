"""Read models / JSON contract for the Next.js dashboard (and our Streamlit check view).

Exports are label-free: nothing here imports evaluation/ or rescreen_qa/.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import feeds
from .db import j
from .jobs import jobs as list_jobs
from .paths import EXPORT_DIR, REPLAYS
from .service import SOURCES, policies
from .workflow import latest_result

CONTRACT_VERSION = "rescreen-contract/1.0"
OPEN_STATES = ("OPEN", "IN_REVIEW", "AWAITING_EVIDENCE", "ESCALATED")


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def _decisions(conn, case_id):
    out = []
    for d in _rows(conn, "SELECT * FROM decisions WHERE case_id=? ORDER BY at", (case_id,)):
        p = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (d["proposal_id"],)).fetchone()
        out.append({"decision_id": d["decision_id"], "decision": d["decision"], "validity": d["validity"],
                    "invalidated_by_event": d["invalidated_by"], "decided_at": d["at"],
                    "reviewer": d["actor"], "reviewer_role": d["role"], "reviewer_comment": d["comment"],
                    "proposal_id": d["proposal_id"], "proposer": p["analyst"], "proposed_at": p["at"],
                    "rationale": p["rationale"], "evidence_ids_used": j(d["evidence_ids"]), "basis": j(d["basis"]),
                    "snapshots_at_decision": j(d["snapshot_ids"])})
    return out


def disposition(alert, decisions) -> str:
    cur = [d for d in decisions if d["decision"] == "APPROVED" and d["validity"] == "CURRENT"]
    if alert["state"] == "RESOLVED" and cur:
        return "FALSE_POSITIVE_CLOSED_APPROVED"
    if alert["state"] == "OPEN" and alert["reopen_count"]:
        return "REOPENED_NEEDS_HUMAN_REVIEW"
    return {"OPEN": "OPEN_UNREVIEWED", "IN_REVIEW": "CLOSURE_PENDING_SENIOR_APPROVAL",
            "AWAITING_EVIDENCE": "AWAITING_EVIDENCE", "ESCALATED": "ESCALATED"}.get(alert["state"], alert["state"])


def _pair_summary(r):
    return {"snapshot_id": r["snapshot_id"], "kyc_snapshot_id": r["kyc_snapshot_id"], "kyc_version": r["kyc_version"],
            "retrieval": r["retrieval"], "alias_match": r["alias_match"],
            "name_only": {"score": r["name_only"]["score"], "decision": r["name_only"]["decision"], "thresholds": r["name_only"].get("thresholds")},
            "splink": {"match_probability": r["splink"]["match_probability"], "match_weight": r["splink"]["match_weight"],
                       "decision": r["splink"]["decision"],
                       "field_contributions": [{k: c[k] for k in ("field", "level_key", "level_description", "m_probability", "u_probability", "bayes_factor", "match_weight")}
                                               for c in r["splink"]["contributions"]]},
            "guard": {"decision": r["guard"]["decision"], "outcome": r["guard"]["outcome"], "reasons": r["guard"]["reasons"],
                      "dob_check_status": r["guard"]["dob_check"]["status"]},
            "raise_alert": r["raise_alert"], "evidence_classification": r["evidence_classification"]}


def _evidence_view(items):
    return [{k: it.get(k) for k in ("evidence_id", "subject_type", "subject_id", "field", "observed_value", "normalised_value",
                                    "precision", "status", "verification", "source_id", "source_snapshot_id", "scheme", "name_type",
                                    "script", "address_from", "address_to", "description")} for it in items]


def side_by_side(results):
    """Evidence per field across every snapshot/KYC version this alert was screened on (e.g. V1 | V2)."""
    cols = [f"{r['snapshot_id']}|kyc_v{r['kyc_version']}" for r in results]
    fields = {}
    for col, r in zip(cols, results):
        for it in r["customer_evidence"] + r["entry_evidence"]:
            fields.setdefault((it["subject_type"], it["field"]), {}).setdefault(col, []).append(
                {"evidence_id": it["evidence_id"], "value": it["observed_value"], "precision": it["precision"],
                 "verification": it["verification"]["status"], "source_id": it["source_id"], "source_snapshot_id": it["source_snapshot_id"]})
    rows = []
    for (st, f), per in sorted(fields.items()):
        ids = [sorted(x["evidence_id"] for x in per.get(c, [])) for c in cols]
        rows.append({"subject_type": st, "field": f, "values": {c: per.get(c, []) for c in cols},
                     "changed": any(x != ids[0] for x in ids)})
    return {"columns": cols, "rows": rows}


def challenger_status(case_id):
    f = REPLAYS / f"{case_id}.json"
    replay = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return {"live": {"available": False, "reason": "offline demo: no live Grok/Challenger connection is used at runtime"},
            "replay": replay, "workflow_blocked": False}


def case_view(conn, case_id) -> dict:
    al = conn.execute("SELECT * FROM alerts WHERE case_id=?", (case_id,)).fetchone()
    if not al:
        raise KeyError(case_id)
    results = [j(r["result"]) for r in conn.execute(
        "SELECT result FROM screening_results WHERE alert_id=? ORDER BY at", (al["alert_id"],))]
    cur = latest_result(conn, al)
    decs = _decisions(conn, case_id)
    cust = j(conn.execute("SELECT data FROM customers WHERE customer_id=?", (al["customer_id"],)).fetchone()["data"])
    events = [dict(e) | {"payload": j(e["payload"])} for e in conn.execute(
        "SELECT event_id,seq,type,payload,job_id,actor,at FROM events WHERE case_id=? ORDER BY seq", (case_id,))]
    return {
        "contract_version": CONTRACT_VERSION, "synthetic": True,
        "case": {"case_id": case_id, "alert_id": al["alert_id"], "customer_id": al["customer_id"],
                 "alert_key": {"customer_id": al["customer_id"], "source_id": al["source_id"], "entry_id": al["entry_id"]},
                 "booking_entity": cust.get("booking_entity"), "state": al["state"], "disposition": disposition(al, decs),
                 "owner": al["owner"], "priority": al["priority"], "reason": al["reason"], "created_at": al["created_at"],
                 "updated_at": al["updated_at"], "reopen_count": al["reopen_count"]},
        "names": {"customer": {"names": cust["names"], "original_script_name": cust.get("original_script_name"), "documented_aliases": cust.get("aliases", [])},
                  "list_entry": {"names": [i for i in _evidence_view(cur["entry_evidence"]) if i["field"] in ("name", "original_script_name")],
                                 "aliases": [i for i in _evidence_view(cur["entry_evidence"]) if i["field"] == "alias"]}},
        "current_screening": _pair_summary(cur),
        "screening_history": [_pair_summary(r) for r in results],
        "evidence_side_by_side": side_by_side(results),
        "current_evidence": _evidence_view(cur["customer_evidence"] + cur["entry_evidence"]),
        "earlier_rationale_and_decisions": decs,
        "pending_proposal": next((dict(p) | {"evidence_ids": j(p["evidence_ids"]), "basis": j(p["basis"])} for p in conn.execute(
            "SELECT * FROM proposals WHERE case_id=? AND status='PENDING'", (case_id,))), None),
        "human_actions": [dict(a) | {"payload": j(a["payload"])} for a in conn.execute(
            "SELECT * FROM case_actions WHERE case_id=? ORDER BY at", (case_id,))],
        "ai": {"challenger": challenger_status(case_id),
               "suggestions_recorded": [dict(s) | {"payload": j(s["payload"]), "is_replay": bool(s["is_replay"])} for s in conn.execute(
                   "SELECT * FROM ai_suggestions WHERE case_id=? ORDER BY at", (case_id,))],
               "human_responses": _rows(conn, "SELECT * FROM ai_responses WHERE case_id=? ORDER BY at", (case_id,))},
        "events": events,
        "allowed_actions": allowed_actions(al["state"]),
    }


def allowed_actions(state):
    return {"OPEN": ["propose_closure", "request_evidence", "escalate"], "IN_REVIEW": ["approve", "return"],
            "AWAITING_EVIDENCE": ["propose_closure", "escalate"], "ESCALATED": ["request_evidence"], "RESOLVED": []}[state]


def reviews(conn) -> dict:
    pending, completed = [], []
    for al in conn.execute("SELECT * FROM alerts ORDER BY case_id"):
        if al["state"] in OPEN_STATES:
            decs = _decisions(conn, al["case_id"])
            pending.append({"case_id": al["case_id"], "state": al["state"], "disposition": disposition(al, decs),
                            "queue": "senior_approval" if al["state"] == "IN_REVIEW" else ("escalated" if al["state"] == "ESCALATED" else "analyst"),
                            "owner": al["owner"], "priority": al["priority"], "reopened": al["reopen_count"] > 0,
                            "age_from": al["created_at"], "updated_at": al["updated_at"], "reason": al["reason"]})
    for d in _rows(conn, "SELECT case_id FROM decisions GROUP BY case_id ORDER BY case_id"):
        for x in _decisions(conn, d["case_id"]):
            completed.append({"case_id": d["case_id"], **x})
    completed.sort(key=lambda x: x["decided_at"])
    return {"contract_version": CONTRACT_VERSION, "pending": pending, "completed": completed,
            "counts": {"pending": len(pending), "completed": len(completed)}}


def evidence_packet(conn, case_id) -> dict:
    """BRD packet fields; label-free, no disposition."""
    al = conn.execute("SELECT * FROM alerts WHERE case_id=?", (case_id,)).fetchone()
    r = latest_result(conn, al)
    items = _evidence_view(r["customer_evidence"] + r["entry_evidence"])
    cls = r["evidence_classification"]
    return {
        "contract_version": CONTRACT_VERSION, "packet_type": "rescreen-evidence-packet", "synthetic": True,
        "case_id": case_id, "customer_id": al["customer_id"],
        "booking_entity": next(i["observed_value"] for i in items if i["field"] == "booking_entity" and i["subject_type"] == "customer"),
        "source_snapshot_ids": {"list": r["snapshot_id"], "kyc": r["kyc_snapshot_id"], "kyc_version": r["kyc_version"]},
        "candidate_edges": [{"edge_id": f"{al['customer_id']}->{al['source_id']}/{al['entry_id']}", "from": al["customer_id"],
                             "to": f"{al['source_id']}/{al['entry_id']}", **{k: v for k, v in _pair_summary(r).items()
                                                                          if k not in ("snapshot_id", "kyc_snapshot_id", "kyc_version")}}],
        "evidence_items": items,
        "identified_conflicts": [c for c in cls if c["classification"] == "conflicting"],
        "missing_fields": [c for c in cls if c["classification"] == "missing"]
                          + [{"dimension": i["field"], "subject_type": i["subject_type"], "evidence_ids": [i["evidence_id"]]}
                             for i in items if i["status"] != "known" and i["field"] not in ("dob", "national_id", "nationality")],
    }


def challenger_handoff(conn, case_id) -> dict:
    """ONLY changed fields, the approval basis and evidence IDs (no labels, no state, no verdict)."""
    al = conn.execute("SELECT * FROM alerts WHERE case_id=?", (case_id,)).fetchone()
    decs = [d for d in _decisions(conn, case_id) if d["decision"] == "APPROVED"]
    changed = []
    am = latest_result(conn, al)["alias_match"]
    for e in conn.execute("SELECT payload FROM events WHERE case_id=? AND type='MATERIAL_CHANGE' ORDER BY seq", (case_id,)):
        for c in j(e["payload"])["changed_fields"]:
            row = {"subject_type": c["subject_type"], "field": c["field"],
                   "before": c["before"], "after": c["after"],
                   "before_snapshot_id": c["before_snapshot_id"], "after_snapshot_id": c["after_snapshot_id"]}
            if c["field"] == "alias" and am and set(am["evidence_ids"]) & {x["evidence_id"] for x in c["after"]}:
                row["now_matches_evidence_ids"] = [i for i in am["evidence_ids"] if i not in {x["evidence_id"] for x in c["after"]}]
            changed.append(row)
    basis = [{"decision_id": d["decision_id"], "type": d["basis"]["type"], "statement": d["basis"]["statement"],
              "cited_evidence_ids": [d["basis"]["customer_evidence_id"], d["basis"]["list_evidence_id"]],
              "evidence_ids_used": d["evidence_ids_used"], "snapshots_at_decision": d["snapshots_at_decision"]} for d in decs]
    ids = sorted({x["evidence_id"] for c in changed for x in c["before"] + c["after"]}
                 | {i for c in changed for i in c.get("now_matches_evidence_ids", [])}
                 | {i for b in basis for i in b["cited_evidence_ids"] + b["evidence_ids_used"]})
    return {"contract_version": CONTRACT_VERSION, "packet_type": "challenger-handoff", "synthetic": True, "case_id": case_id,
            "changed_fields": changed, "approval_basis": basis, "evidence_ids": ids,
            "requested_output": {"fields": ["case_id", "evidence_ids", "contradictions", "missing_evidence", "suggested_next_check"],
                                 "instruction": "Explain what changed and the next verification. Cite evidence IDs. Leave the disposition to the analyst and designated reviewer."}}


def jurisdiction_view(conn, case_id, primary="UK") -> dict:
    pol = policies()
    if primary not in pol["overlays"]:
        raise ValueError(primary)
    al = conn.execute("SELECT * FROM alerts WHERE case_id=?", (case_id,)).fetchone()
    facts = pol["case_facts"].get(al["customer_id"], {})
    fstat = {f["jurisdiction"]: f for f in feeds.status(conn)}
    last_job = next((jb for jb in reversed(list_jobs(conn)) if jb["status"].startswith("COMPLETED")
                     and al["customer_id"] in jb["scope"]["customers"]), None)
    rows, hits = [], {}
    for jur in pol["overlays"][primary]["order"]:
        src = SOURCES[jur]
        fs = fstat.get(jur)
        hit = conn.execute("SELECT * FROM alerts WHERE customer_id=? AND source_id=?", (al["customer_id"], src)).fetchone()
        if fs is None or fs["active_snapshot_id"] is None:
            check = "NOT_CHECKED_NO_VALID_SNAPSHOT"
        elif hit:
            check = "HIT"
        elif last_job and fs["active_snapshot_id"] in last_job["snapshot_ids"]:
            check = "NO_HIT_COMPLETE"
        else:
            check = "PENDING"
        measures, identity = [], None
        if hit:
            r = latest_result(conn, hit)
            measures = [{"measure_id": i["observed_value"], "description": i.get("description"), "evidence_id": i["evidence_id"]}
                        for i in r["entry_evidence"] if i["field"] == "measure"]
            identity = {c["dimension"]: c["classification"] for c in r["evidence_classification"]}
            hits[jur] = f"{src}/{hit['entry_id']}"
        nexus = (facts.get("nexus") or {}).get(jur)
        rows.append({"jurisdiction": jur, "source_id": src, "snapshot_id": fs["active_snapshot_id"] if fs else None,
                     "coverage": fs["coverage"] if fs else "NO_COVERAGE", "check_status": check, "measures": measures,
                     "identity_evidence": identity, "factual_nexus": nexus,
                     "applicability": "in scope (factual nexus recorded)" if nexus else "no factual nexus recorded",
                     "previous_finding": disposition(hit, _decisions(conn, hit["case_id"])) if hit else None,
                     "local_overlay": pol["overlays"][jur]["rule"]})
    for row in rows:
        if row["check_status"] == "NO_HIT_COMPLETE" and hits:
            row["list_difference"] = f"LIST_DIFFERENCE: hit on {', '.join(hits.values())}; completed search of {row['source_id']} found none (coverage difference, not a conflict)"
        else:
            row["list_difference"] = None
    link = facts.get("cn_measure_link")
    cn_nexus = (facts.get("nexus") or {}).get("CN")
    specific = bool(link and link.get("targets_foreign_listing") in hits.values())
    potential = {"specific_measure": link["measure_id"] if specific else None, "factual_nexus": cn_nexus,
                 "status": "POTENTIAL_CONFLICT_ROUTE_TO_LEGAL" if (specific and cn_nexus) else "NOT_ESTABLISHED",
                 "rule": "Potential conflict requires a specific measure AND a factual nexus.",
                 "route_to": "Legal" if (specific and cn_nexus) else None}
    return {"contract_version": CONTRACT_VERSION, "synthetic": True, "fictional_measures_notice": pol["_notice"],
            "case_id": case_id, "primary_view": primary, "ordering": pol["overlays"][primary]["order"],
            "default_queue": pol["overlays"][primary]["default_queue"], "booking_entity": facts.get("booking_entity"),
            "rows": rows, "potential_conflict": potential}


def export_all(conn, out_dir: Path = EXPORT_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def w(name, obj):
        p = out_dir / name
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(p)
    w("feeds_status.json", {"contract_version": CONTRACT_VERSION, "feeds": feeds.status(conn)})
    w("jobs.json", {"contract_version": CONTRACT_VERSION, "jobs": list_jobs(conn)})
    w("reviews.json", reviews(conn))
    for (case_id,) in conn.execute("SELECT case_id FROM alerts ORDER BY case_id").fetchall():
        w(f"case_view_{case_id}.json", case_view(conn, case_id))
        w(f"evidence_packet_{case_id}.json", evidence_packet(conn, case_id))
        w(f"challenger_handoff_{case_id}.json", challenger_handoff(conn, case_id))
        for prim in ("UK", "US", "CN"):
            w(f"jurisdictions_{case_id}_{prim}.json", jurisdiction_view(conn, case_id, prim))
    return written
