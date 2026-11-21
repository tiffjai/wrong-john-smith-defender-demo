"""End-to-end acceptance run (offline, no Grok): V1 proposal -> independent senior approval -> V2 -> exactly B reopens.

Usage: python -m rescreen acceptance [--db PATH] [--out DIR]
Exit code 0 only if every check passes. Writes exports + acceptance_report.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import jobs, service, views, workflow
from .paths import EXPORT_DIR, REPLAYS


def ev_id(conn, case_id, subject_type, field, value=None):
    cv = views.case_view(conn, case_id)
    for i in cv["current_evidence"]:
        if i["subject_type"] == subject_type and i["field"] == field and (value is None or i["observed_value"] == value):
            return i["evidence_id"]
    raise KeyError((case_id, subject_type, field, value))


def snapshot_states(conn):
    out = {}
    for r in conn.execute("SELECT case_id,state,reopen_count FROM alerts ORDER BY case_id"):
        decs = views._decisions(conn, r["case_id"])
        out[r["case_id"]] = {"state": r["state"], "reopen_count": r["reopen_count"],
                             "disposition": views.disposition(conn.execute("SELECT * FROM alerts WHERE case_id=?", (r["case_id"],)).fetchone(), decs),
                             "approvals": [(d["decision_id"], d["validity"]) for d in decs if d["decision"] == "APPROVED"]}
    return out


def count(conn, type_, case_id=None):
    if case_id:
        return conn.execute("SELECT COUNT(*) FROM events WHERE type=? AND case_id=?", (type_, case_id)).fetchone()[0]
    return conn.execute("SELECT COUNT(*) FROM events WHERE type=?", (type_,)).fetchone()[0]


def run(db_path="rescreen_state/acceptance.sqlite", out_dir: Path = EXPORT_DIR, verbose=True) -> dict:
    log, checks = [], []

    def say(msg):
        log.append(msg)
        if verbose:
            print(msg)

    def check(name, ok, observed):
        checks.append({"check": name, "passed": bool(ok), "observed": observed})
        say(f"  [{'PASS' if ok else 'FAIL'}] {name} -> {observed}")

    s = service.reset(db_path)
    conn = s["conn"]
    say(f"STEP 1 reset: KYC {s['kyc']['kyc_snapshot_id']} imported={s['kyc']['imported']} rejected={s['kyc']['rejected']} active={s['kyc']['active']}; "
        + "; ".join(f"{f['jurisdiction']} {f['result']} {f['snapshot_id']}" for f in s["feed_loads"]) + f"; job {s['job']['job_id']} {s['job']['status']}")
    st = snapshot_states(conn)
    check("V1 screening raises alerts for both customers against DEMO-WL-410", set(st) == {"RESCREEN-A", "RESCREEN-B"}
          and all(v["state"] == "OPEN" for v in st.values()), {k: v["state"] for k, v in st.items()})

    say("STEP 2 V1 analyst proposals and independent senior approvals")
    a_id, wl_id = ev_id(conn, "RESCREEN-A", "customer", "national_id"), ev_id(conn, "RESCREEN-A", "list_entry", "national_id")
    a_dob, wl_dob_a = ev_id(conn, "RESCREEN-A", "customer", "dob"), ev_id(conn, "RESCREEN-A", "list_entry", "dob")
    pa = workflow.propose_closure(conn, "RESCREEN-A", "ana.analyst",
                                  "Different person: A's verified identity card number differs from the listed national ID (independent of name and DOB).",
                                  [a_id, wl_id, a_dob, wl_dob_a], "verified_identifier_conflict", a_id, wl_id)
    say(f"  ana.analyst proposed {pa['proposal_id']} basis: {pa['basis']['statement']}")
    try:
        workflow.approve(conn, "RESCREEN-A", "ana.analyst")
        check("analyst cannot approve (role)", False, "approved!")
    except workflow.WorkflowError as e:
        check("analyst cannot approve (role)", e.code == "ROLE_NOT_ALLOWED", e.code)
    da = workflow.approve(conn, "RESCREEN-A", "rio.senior", "Identifier conflict verified on both sides.")
    say(f"  rio.senior approved {da['decision_id']}")
    b_dob, wl_dob_v1 = ev_id(conn, "RESCREEN-B", "customer", "dob"), ev_id(conn, "RESCREEN-B", "list_entry", "dob")
    pb = workflow.propose_closure(conn, "RESCREEN-B", "sam.analyst",
                                  "Different person: B's verified passport DOB 1991-06-14 conflicts with the listed full DOB 1987-09-03.",
                                  [b_dob, wl_dob_v1], "verified_full_dob_conflict", b_dob, wl_dob_v1)
    say(f"  sam.analyst proposed {pb['proposal_id']} basis: {pb['basis']['statement']}")
    try:
        workflow.approve(conn, "RESCREEN-B", "sam.analyst")
        check("analyst cannot approve own proposal", False, "approved!")
    except workflow.WorkflowError as e:
        check("analyst cannot approve own proposal", e.code in ("ROLE_NOT_ALLOWED", "SELF_APPROVAL_FORBIDDEN"), e.code)
    db_ = workflow.approve(conn, "RESCREEN-B", "kai.senior", "DOB conflict verified on both sides.")
    say(f"  kai.senior approved {db_['decision_id']}")
    before = snapshot_states(conn)
    check("before V2: both cases RESOLVED with a current approval",
          all(v["state"] == "RESOLVED" and v["approvals"] and v["approvals"][-1][1] == "CURRENT" for v in before.values()), before)

    say("STEP 3 load V2 (validated, activated, rescreen job queued)")
    v2 = service.load_feed(conn, "UK", "V2")
    say(f"  feed {v2['result']} {v2['snapshot_id']} diff={v2.get('diff')} job={v2['rescreen_job']['job_id']} {v2['rescreen_job']['status']} counts={v2['rescreen_job']['counts']}")
    after = snapshot_states(conn)
    check("V2 activated and rescreen ran", v2["result"] == "ACTIVATED" and v2["rescreen_job"]["status"].startswith("COMPLETED"), v2["rescreen_job"]["counts"])
    check("A keeps its approval (identifier basis HOLDS)", after["RESCREEN-A"]["state"] == "RESOLVED" and after["RESCREEN-A"]["approvals"][-1][1] == "CURRENT"
          and count(conn, "APPROVAL_BASIS_HOLDS", "RESCREEN-A") == 1, after["RESCREEN-A"])
    check("B reopens (DOB conflict cited in approval disappeared)", after["RESCREEN-B"]["state"] == "OPEN" and after["RESCREEN-B"]["reopen_count"] == 1
          and after["RESCREEN-B"]["approvals"][-1][1] == "INVALIDATED", after["RESCREEN-B"])
    check("exactly one REOPENED event overall (B only)", count(conn, "REOPENED") == 1 and count(conn, "REOPENED", "RESCREEN-B") == 1, count(conn, "REOPENED"))
    reopen = json.loads(conn.execute("SELECT payload FROM events WHERE type='REOPENED'").fetchone()["payload"])
    say(f"  reopen evaluation: {reopen['evaluation']['status']} - {reopen['evaluation']['reason']}; changed fields: "
        + ", ".join(f"{c['subject_type']}.{c['field']}" for c in reopen["changed_fields"]))
    check("both approval histories retained", len([d for d in views._decisions(conn, "RESCREEN-A") if d["decision"] == "APPROVED"]) == 1
          and len([d for d in views._decisions(conn, "RESCREEN-B") if d["decision"] == "APPROVED"]) == 1, "A:1 approval (CURRENT), B:1 approval (INVALIDATED)")
    cvb = views.case_view(conn, "RESCREEN-B")
    check("B back with a human (owner = original proposer, analyst queue, allowed actions)",
          cvb["case"]["owner"] == "sam.analyst" and "request_evidence" in cvb["allowed_actions"] and "escalate" in cvb["allowed_actions"],
          {"owner": cvb["case"]["owner"], "allowed_actions": cvb["allowed_actions"]})
    check("B V2 now matches via documented alias and exact DOB", cvb["current_screening"]["alias_match"] is not None
          and cvb["current_screening"]["splink"]["decision"] == "LINK",
          {"alias": (cvb["current_screening"]["alias_match"] or {}).get("form"), "P": cvb["current_screening"]["splink"]["match_probability"]})

    say("STEP 4 repeat V2 load, manual rescreen and daily sweep (idempotency)")
    v2b = service.load_feed(conn, "UK", "V2")
    sweep = jobs.daily_sweep(conn)
    manual = jobs.run_rescreen(conn, "manual")
    check("repeat V2 load is NO_UPDATE (no job queued)", v2b["result"] == "NO_UPDATE" and v2b["rescreen_job"] is None, v2b["result"])
    check("still exactly one REOPENED event after repeat load + sweep + manual rescreen", count(conn, "REOPENED") == 1,
          {"REOPENED": count(conn, "REOPENED"), "sweep": sweep["status"], "manual": manual["status"]})
    check("still exactly one alert per customer/source/entry", conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 2,
          conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])

    say("STEP 5 simulated feed failure (malformed V3)")
    bad = service.simulate_feed_failure(conn)
    check("malformed V3 rejected, last-good V2 stays active, coverage DEGRADED", bad["result"] == "FAILED_VALIDATION"
          and bad["active_snapshot_id"] == v2["snapshot_id"] and bad["coverage"].startswith("DEGRADED"),
          {"result": bad["result"], "errors": bad["errors"], "active": bad["active_snapshot_id"], "coverage": bad["coverage"]})
    sweep2 = jobs.daily_sweep(conn)
    check("sweep still runs on last-good snapshot", sweep2["status"].startswith("COMPLETED") and v2["snapshot_id"] in sweep2["snapshot_ids"], sweep2["snapshot_ids"])

    say("STEP 6 failed job + retry (no duplicates)")
    ev_before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    failed = jobs.run_rescreen(conn, "manual", fail_after=1)
    retried = jobs.retry(conn, failed["job_id"])
    ev_after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    check("failed job recorded and retry completes without duplicate alerts/events",
          failed["status"] == "FAILED" and retried["status"].startswith("COMPLETED") and ev_after == ev_before
          and conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 2,
          {"failed": failed["job_id"], "error": failed["error"], "retry": retried["job_id"], "events_before": ev_before, "events_after": ev_after})

    say("STEP 7 material KYC change on A (same job logic, trigger kyc_change)")
    ku = service.update_customer(conn, "SYN-CUST-A", {"aliases": [{"value": "Chan W. M.", "type": "documented_alias", "scheme": "initials", "document_ref": "DOC-SYN-A-02"}]}, "ana.analyst")
    check("KYC alias update is material, triggers rescreen of A only; A approval still holds",
          ku["material"] and ku["rescreen_job"]["trigger"] == "kyc_change" and ku["rescreen_job"]["scope"]["customers"] == ["SYN-CUST-A"]
          and snapshot_states(conn)["RESCREEN-A"]["state"] == "RESOLVED",
          {"version": ku["version"], "job": ku["rescreen_job"]["job_id"], "A_state": snapshot_states(conn)["RESCREEN-A"]["state"]})

    say("STEP 8 Grok/Challenger unavailable path + labelled replay")
    ch = cvb["ai"]["challenger"]
    check("case view usable with live Challenger unavailable", ch["live"]["available"] is False and ch["workflow_blocked"] is False, ch["live"])
    if ch["replay"]:
        sug = workflow.record_ai_suggestion(conn, "RESCREEN-B", ch["replay"], "replay")
        workflow.respond_to_ai(conn, "RESCREEN-B", sug["suggestion_id"], "sam.analyst", "AMEND",
                               "Agree an independent identifier is needed; also confirm the V2 alias source before deciding.")
        check("replay is labelled and stored apart from the human response", ch["replay"].get("replay") is True and sug["is_replay"], sug)
    try:
        workflow.propose_closure(conn, "RESCREEN-B", "sam.analyst", "retry old basis", [b_dob, wl_dob_v1],
                                 "verified_full_dob_conflict", b_dob, wl_dob_v1)
        check("B cannot be re-closed on the vanished DOB basis", False, "accepted!")
    except workflow.WorkflowError as e:
        check("B cannot be re-closed on the vanished DOB basis", e.code == "BASIS_INVALID", str(e))
    rq = workflow.request_evidence(conn, "RESCREEN-B", "sam.analyst", "Request an independent verified identifier for B.")
    check("B can go to AWAITING_EVIDENCE without Grok", rq["state"] == "AWAITING_EVIDENCE", rq)

    rv = views.reviews(conn)
    check("Reviews: pending = [RESCREEN-B]; completed = 2 approvals (A current, B invalidated)",
          [p["case_id"] for p in rv["pending"]] == ["RESCREEN-B"] and len(rv["completed"]) == 2,
          {"pending": [(p["case_id"], p["state"]) for p in rv["pending"]], "completed": [(c["case_id"], c["decision"], c["validity"]) for c in rv["completed"]]})

    say("STEP 9 senior self-approval guard (scratch database, so the main demo state is untouched)")
    s2 = service.reset(str(Path(db_path).with_suffix(".selfapproval.sqlite")))
    c2 = s2["conn"]
    i1, i2 = ev_id(c2, "RESCREEN-A", "customer", "national_id"), ev_id(c2, "RESCREEN-A", "list_entry", "national_id")
    workflow.propose_closure(c2, "RESCREEN-A", "kai.senior", "identifier conflict", [i1, i2], "verified_identifier_conflict", i1, i2)
    try:
        workflow.approve(c2, "RESCREEN-A", "kai.senior")
        check("senior cannot approve own proposal (self-approval)", False, "approved!")
    except workflow.WorkflowError as e:
        check("senior cannot approve own proposal (self-approval)", e.code == "SELF_APPROVAL_FORBIDDEN", e.code)
    c2.close()

    files = views.export_all(conn, out_dir)
    report = {"passed": all(c["passed"] for c in checks), "checks": checks, "states_before_v2": before, "states_after_v2": after,
              "final_states": snapshot_states(conn), "reopen_events": count(conn, "REOPENED"),
              "exports": [p.name for p in files], "log": log}
    (Path(out_dir) / "acceptance_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"RESULT: {sum(c['passed'] for c in checks)}/{len(checks)} checks passed; exports in {out_dir}")
    return report
