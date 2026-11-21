"""Case workflow (simulated sign-in with seeded roles).

States: OPEN -> IN_REVIEW (closure proposed, pending senior approval) -> RESOLVED (approved)
        IN_REVIEW -> OPEN (returned);  OPEN/IN_REVIEW -> AWAITING_EVIDENCE | ESCALATED;  RESOLVED -> OPEN (system reopen)
An approver must hold an approval role AND differ from the proposer (no self-approval).
AI (Challenger) suggestions are stored separately from human decisions; replays are labelled.
"""
from __future__ import annotations

import json

from . import basis as basis_mod
from .config import load_policy
from .db import add_event, j, now, stable_id

PROPOSE_ROLES = {"analyst", "senior_reviewer"}
EVIDENCE_ROLES = {"analyst", "senior_reviewer", "legal_reviewer"}
ESCALATION_QUEUES = {"Sanctions", "Legal"}


class WorkflowError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def actor(conn, actor_id: str) -> dict:
    row = conn.execute("SELECT * FROM actors WHERE actor_id=?", (actor_id,)).fetchone()
    if not row:
        raise WorkflowError("UNKNOWN_ACTOR", f"{actor_id!r} is not a seeded demo actor")
    return dict(row)


def _alert(conn, case_id):
    row = conn.execute("SELECT * FROM alerts WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise WorkflowError("UNKNOWN_CASE", case_id)
    return row


def latest_result(conn, alert) -> dict:
    row = conn.execute("SELECT result FROM screening_results WHERE alert_id=? AND snapshot_id=? AND kyc_version=?",
                       (alert["alert_id"], alert["latest_snapshot_id"], alert["latest_kyc_version"])).fetchone()
    return j(row["result"])


def _action(conn, case_id, a, action, from_state, to_state, comment, payload, at):
    conn.execute("INSERT INTO case_actions(action_id,case_id,actor,role,action,from_state,to_state,comment,payload,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (stable_id("ACT-", case_id, action, a["actor_id"], at), case_id, a["actor_id"], a["role"], action,
                  from_state, to_state, comment, json.dumps(payload, ensure_ascii=False), at))


def _set_state(conn, alert, state, at, owner=None):
    conn.execute("UPDATE alerts SET state=?, updated_at=?, owner=COALESCE(?, owner) WHERE alert_id=?", (state, at, owner, alert["alert_id"]))


def propose_closure(conn, case_id, actor_id, rationale, evidence_ids, basis_type, customer_evidence_id, list_evidence_id) -> dict:
    a = actor(conn, actor_id)
    if a["role"] not in PROPOSE_ROLES:
        raise WorkflowError("ROLE_NOT_ALLOWED", f"{a['role']} cannot propose a closure")
    al = _alert(conn, case_id)
    if al["state"] not in ("OPEN", "AWAITING_EVIDENCE"):
        raise WorkflowError("BAD_STATE", f"cannot propose from state {al['state']}")
    if not rationale or not rationale.strip():
        raise WorkflowError("RATIONALE_REQUIRED", "a written rationale is required")
    r = latest_result(conn, al)
    known = {i["evidence_id"] for i in r["customer_evidence"] + r["entry_evidence"]}
    try:
        b = basis_mod.make_basis(basis_type, customer_evidence_id, list_evidence_id, r["customer_evidence"], r["entry_evidence"])
    except basis_mod.BasisError as e:
        raise WorkflowError("BASIS_INVALID", str(e)) from e
    cited = sorted(set(evidence_ids) | {customer_evidence_id, list_evidence_id})
    unknown = [e for e in cited if e not in known]
    if unknown:
        raise WorkflowError("UNKNOWN_EVIDENCE", f"evidence IDs not in this case's current evidence: {unknown}")
    at = now(conn)
    pid = stable_id("PRP-", case_id, actor_id, at)
    snaps = {"list_snapshot_id": r["snapshot_id"], "kyc_snapshot_id": r["kyc_snapshot_id"], "kyc_version": r["kyc_version"]}
    conn.execute("BEGIN")
    conn.execute("INSERT INTO proposals(proposal_id,case_id,analyst,rationale,evidence_ids,basis,snapshot_ids,status,at) VALUES(?,?,?,?,?,?,?,?,?)",
                 (pid, case_id, actor_id, rationale, json.dumps(cited), json.dumps(b, ensure_ascii=False), json.dumps(snaps), "PENDING", at))
    _set_state(conn, al, "IN_REVIEW", at, owner=actor_id)
    _action(conn, case_id, a, "PROPOSE_FALSE_POSITIVE_CLOSURE", al["state"], "IN_REVIEW", rationale,
            {"proposal_id": pid, "evidence_ids": cited, "basis": b}, at)
    add_event(conn, (pid,), "CLOSURE_PROPOSED", {"proposal_id": pid, "basis": b, "evidence_ids": cited}, al["alert_id"], case_id, actor=actor_id)
    conn.execute("COMMIT")
    return {"proposal_id": pid, "case_id": case_id, "state": "IN_REVIEW", "basis": b, "evidence_ids": cited}


def _pending_proposal(conn, case_id):
    row = conn.execute("SELECT * FROM proposals WHERE case_id=? AND status='PENDING' ORDER BY at DESC LIMIT 1", (case_id,)).fetchone()
    if not row:
        raise WorkflowError("NO_PENDING_PROPOSAL", case_id)
    return row


def _review(conn, case_id, actor_id, comment, decision):
    a = actor(conn, actor_id)
    pol = load_policy()["policy"]
    if a["role"] not in pol["approval_roles"]:
        raise WorkflowError("ROLE_NOT_ALLOWED", f"{a['role']} cannot {decision.lower()} a closure (needs {pol['approval_roles']})")
    p = _pending_proposal(conn, case_id)
    if p["analyst"] == actor_id and not pol["self_approval_allowed"]:
        raise WorkflowError("SELF_APPROVAL_FORBIDDEN", f"{actor_id} proposed this closure and cannot review it")
    al = _alert(conn, case_id)
    at = now(conn)
    did = stable_id("DEC-", case_id, p["proposal_id"], actor_id, decision, at)
    new_state = "RESOLVED" if decision == "APPROVED" else "OPEN"
    conn.execute("BEGIN")
    conn.execute("INSERT INTO decisions(decision_id,case_id,proposal_id,actor,role,decision,comment,evidence_ids,basis,snapshot_ids,at,validity,invalidated_by) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                 (did, case_id, p["proposal_id"], actor_id, a["role"], decision, comment, p["evidence_ids"], p["basis"], p["snapshot_ids"], at,
                  "CURRENT" if decision == "APPROVED" else "N/A"))
    conn.execute("UPDATE proposals SET status=? WHERE proposal_id=?", (decision, p["proposal_id"]))
    _set_state(conn, al, new_state, at, owner=None if decision == "APPROVED" else p["analyst"])
    _action(conn, case_id, a, decision, al["state"], new_state, comment, {"decision_id": did, "proposal_id": p["proposal_id"]}, at)
    add_event(conn, (did,), f"CLOSURE_{decision}", {"decision_id": did, "proposal_id": p["proposal_id"], "proposer": p["analyst"],
                                                    "reviewer": actor_id, "basis": j(p["basis"]), "evidence_ids": j(p["evidence_ids"])},
              al["alert_id"], case_id, actor=actor_id)
    conn.execute("COMMIT")
    return {"decision_id": did, "case_id": case_id, "decision": decision, "state": new_state, "proposer": p["analyst"], "reviewer": actor_id}


def approve(conn, case_id, actor_id, comment="") -> dict:
    return _review(conn, case_id, actor_id, comment, "APPROVED")


def return_proposal(conn, case_id, actor_id, comment) -> dict:
    return _review(conn, case_id, actor_id, comment, "RETURNED")


def _simple(conn, case_id, actor_id, roles, allowed_from, to_state, action, comment, payload=None):
    a = actor(conn, actor_id)
    if a["role"] not in roles:
        raise WorkflowError("ROLE_NOT_ALLOWED", f"{a['role']} cannot {action}")
    al = _alert(conn, case_id)
    if al["state"] not in allowed_from:
        raise WorkflowError("BAD_STATE", f"cannot {action} from {al['state']}")
    at = now(conn)
    conn.execute("BEGIN")
    _set_state(conn, al, to_state, at, owner=actor_id)
    _action(conn, case_id, a, action, al["state"], to_state, comment, payload or {}, at)
    add_event(conn, (case_id, action, at), action, {"comment": comment, **(payload or {})}, al["alert_id"], case_id, actor=actor_id)
    conn.execute("COMMIT")
    return {"case_id": case_id, "state": to_state, "action": action}


def request_evidence(conn, case_id, actor_id, comment) -> dict:
    return _simple(conn, case_id, actor_id, EVIDENCE_ROLES, ("OPEN", "ESCALATED"), "AWAITING_EVIDENCE", "REQUEST_EVIDENCE", comment)


def escalate(conn, case_id, actor_id, queue, comment) -> dict:
    if queue not in ESCALATION_QUEUES:
        raise WorkflowError("BAD_QUEUE", f"queue must be one of {sorted(ESCALATION_QUEUES)}")
    return _simple(conn, case_id, actor_id, EVIDENCE_ROLES, ("OPEN", "AWAITING_EVIDENCE"), "ESCALATED", "ESCALATE", comment, {"queue": queue})


def record_ai_suggestion(conn, case_id, payload: dict, origin: str) -> dict:
    """origin: 'replay' (saved sample, labelled) or 'live'. Stored apart from human decisions."""
    _alert(conn, case_id)
    at = now(conn)
    sid = stable_id("AIS-", case_id, origin, json.dumps(payload, sort_keys=True))
    conn.execute("INSERT OR IGNORE INTO ai_suggestions(suggestion_id,case_id,origin,is_replay,payload,at) VALUES(?,?,?,?,?,?)",
                 (sid, case_id, origin, 1 if origin == "replay" else 0, json.dumps(payload, ensure_ascii=False), at))
    return {"suggestion_id": sid, "origin": origin, "is_replay": origin == "replay"}


def respond_to_ai(conn, case_id, suggestion_id, actor_id, action, text) -> dict:
    if action not in ("ACCEPT", "AMEND", "REJECT"):
        raise WorkflowError("BAD_ACTION", action)
    a = actor(conn, actor_id)
    if not conn.execute("SELECT 1 FROM ai_suggestions WHERE suggestion_id=? AND case_id=?", (suggestion_id, case_id)).fetchone():
        raise WorkflowError("UNKNOWN_SUGGESTION", suggestion_id)
    at = now(conn)
    rid = stable_id("AIR-", case_id, suggestion_id, actor_id, at)
    conn.execute("INSERT INTO ai_responses(response_id,case_id,suggestion_id,actor,action,text,at) VALUES(?,?,?,?,?,?,?)",
                 (rid, case_id, suggestion_id, actor_id, action, text, at))
    _action(conn, case_id, a, f"AI_SUGGESTION_{action}", None, None, text, {"suggestion_id": suggestion_id}, at)
    return {"response_id": rid, "action": action}
