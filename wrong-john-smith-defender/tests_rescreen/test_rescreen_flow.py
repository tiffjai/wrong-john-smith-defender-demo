import json

import pytest

from rescreen import feeds, jobs, service, views, workflow
from rescreen.acceptance import count, ev_id, snapshot_states
from rescreen.paths import FEEDS

from rs_helpers import approve_both


def test_acceptance_run_all_checks_pass(accepted):
    rep = accepted["report"]
    assert rep["passed"], [c for c in rep["checks"] if not c["passed"]]
    assert rep["states_before_v2"]["RESCREEN-A"]["state"] == rep["states_before_v2"]["RESCREEN-B"]["state"] == "RESOLVED"
    assert rep["states_after_v2"]["RESCREEN-A"]["state"] == "RESOLVED"
    assert rep["states_after_v2"]["RESCREEN-B"]["state"] == "OPEN"
    assert rep["reopen_events"] == 1


def test_v1_alerts_and_same_pairs_scored_by_both_methods(fresh):
    rows = fresh.execute("SELECT case_id, customer_id, source_id, entry_id, state FROM alerts ORDER BY case_id").fetchall()
    assert [tuple(r) for r in rows] == [("RESCREEN-A", "SYN-CUST-A", "FICT-UK-SL", "DEMO-WL-410", "OPEN"),
                                        ("RESCREEN-B", "SYN-CUST-B", "FICT-UK-SL", "DEMO-WL-410", "OPEN")]
    for cid in ("RESCREEN-A", "RESCREEN-B"):
        cs = views.case_view(fresh, cid)["current_screening"]
        assert cs["name_only"]["decision"] and cs["splink"]["decision"] and cs["guard"]["decision"]
        assert cs["splink"]["field_contributions"]


def test_exactly_b_reopens_and_repeat_v2_is_idempotent(fresh):
    approve_both(fresh)
    first = service.load_feed(fresh, "UK", "V2")
    assert first["result"] == "ACTIVATED" and first["rescreen_job"]["counts"]["reopened"] == 1
    st = snapshot_states(fresh)
    assert st["RESCREEN-A"]["state"] == "RESOLVED" and st["RESCREEN-B"]["state"] == "OPEN"
    for _ in range(3):
        assert service.load_feed(fresh, "UK", "V2")["result"] == "NO_UPDATE"
        jobs.run_rescreen(fresh, "manual")
        jobs.daily_sweep(fresh)
    assert count(fresh, "REOPENED") == 1 and count(fresh, "REOPENED", "RESCREEN-B") == 1
    assert fresh.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 2
    assert fresh.execute("SELECT reopen_count FROM alerts WHERE case_id='RESCREEN-B'").fetchone()[0] == 1
    hist = views._decisions(fresh, "RESCREEN-B")
    assert [(d["decision"], d["validity"]) for d in hist] == [("APPROVED", "INVALIDATED")]
    assert [(d["decision"], d["validity"]) for d in views._decisions(fresh, "RESCREEN-A")] == [("APPROVED", "CURRENT")]


def test_reopen_event_payload_names_vanished_basis(fresh):
    approve_both(fresh)
    service.load_feed(fresh, "UK", "V2")
    p = json.loads(fresh.execute("SELECT payload FROM events WHERE type='REOPENED'").fetchone()[0])
    assert p["basis"]["type"] == "verified_full_dob_conflict"
    assert p["evaluation"]["status"] == "BASIS_NO_LONGER_HOLDS"
    assert p["evaluation"]["current"]["list_value"] == "1991-06-14"
    assert {(c["subject_type"], c["field"]) for c in p["changed_fields"]} == {("list_entry", "dob"), ("list_entry", "alias")}


def test_self_approval_and_roles(fresh):
    i1, i2 = ev_id(fresh, "RESCREEN-A", "customer", "national_id"), ev_id(fresh, "RESCREEN-A", "list_entry", "national_id")
    workflow.propose_closure(fresh, "RESCREEN-A", "kai.senior", "id conflict", [i1, i2], "verified_identifier_conflict", i1, i2)
    for actor_id, code in (("kai.senior", "SELF_APPROVAL_FORBIDDEN"), ("ana.analyst", "ROLE_NOT_ALLOWED"),
                           ("lee.legal", "ROLE_NOT_ALLOWED"), ("nobody", "UNKNOWN_ACTOR")):
        with pytest.raises(workflow.WorkflowError) as e:
            workflow.approve(fresh, "RESCREEN-A", actor_id)
        assert e.value.code == code
    with pytest.raises(workflow.WorkflowError) as e:
        workflow.return_proposal(fresh, "RESCREEN-A", "kai.senior", "x")
    assert e.value.code == "SELF_APPROVAL_FORBIDDEN"
    r = workflow.return_proposal(fresh, "RESCREEN-A", "rio.senior", "cite the document image too")
    assert r["state"] == "OPEN"
    assert views.reviews(fresh)["completed"][0]["decision"] == "RETURNED"


def test_basis_must_hold_and_evidence_must_belong_to_case(fresh):
    b1 = ev_id(fresh, "RESCREEN-B", "customer", "national_id")
    b2 = ev_id(fresh, "RESCREEN-B", "list_entry", "national_id")
    with pytest.raises(workflow.WorkflowError) as e:   # B's national ID is unknown -> cannot be an identifier basis
        workflow.propose_closure(fresh, "RESCREEN-B", "sam.analyst", "x", [b1, b2], "verified_identifier_conflict", b1, b2)
    assert e.value.code == "BASIS_INVALID"
    d1, d2 = ev_id(fresh, "RESCREEN-B", "customer", "dob"), ev_id(fresh, "RESCREEN-B", "list_entry", "dob")
    with pytest.raises(workflow.WorkflowError) as e:
        workflow.propose_closure(fresh, "RESCREEN-B", "sam.analyst", "x", [d1, d2, "EV-000000000000"], "verified_full_dob_conflict", d1, d2)
    assert e.value.code == "UNKNOWN_EVIDENCE"
    with pytest.raises(workflow.WorkflowError) as e:
        workflow.propose_closure(fresh, "RESCREEN-B", "sam.analyst", "  ", [d1, d2], "verified_full_dob_conflict", d1, d2)
    assert e.value.code == "RATIONALE_REQUIRED"


def test_malformed_feed_keeps_last_good(fresh, tmp_path):
    before = feeds.active(fresh, "FICT-UK-SL")["snapshot_id"]
    r = service.simulate_feed_failure(fresh)
    assert r["result"] == "FAILED_VALIDATION" and r["rescreen_job"] is None
    assert feeds.active(fresh, "FICT-UK-SL")["snapshot_id"] == before
    st = [f for f in feeds.status(fresh) if f["source_id"] == "FICT-UK-SL"][0]
    assert st["coverage"].startswith("DEGRADED") and st["last_check_result"] == "FAILED_VALIDATION"
    # entry-level rejection also blocks activation, with reconciliation counts
    bad = json.loads((FEEDS / "uk_v2.json").read_text())
    bad["entries"][1]["names"] = []
    p = tmp_path / "uk_bad_entry.json"
    p.write_text(json.dumps(bad))
    r2 = service.load_feed(fresh, "UK", path=str(p))
    assert r2["result"] == "FAILED_VALIDATION" and r2["received"] == 2 and r2["rejected"] == 1 and r2["loaded"] == 0
    # stale source
    stale = json.loads((FEEDS / "uk_v2.json").read_text())
    stale["published_at"] = "2026-10-01T00:00:00Z"
    p2 = tmp_path / "uk_stale.json"
    p2.write_text(json.dumps(stale))
    assert service.load_feed(fresh, "UK", path=str(p2))["result"] == "STALE_SOURCE"
    assert feeds.active(fresh, "FICT-UK-SL")["snapshot_id"] == before
    # a later valid V2 still activates and coverage recovers
    ok = service.load_feed(fresh, "UK", "V2")
    assert ok["result"] == "ACTIVATED" and ok["coverage"] == "OK"


def test_every_trigger_uses_the_same_rescreen_function(fresh, monkeypatch):
    calls = []
    real = jobs.run_rescreen

    def spy(conn, trigger, customer_ids=None, **kw):
        calls.append(trigger)
        return real(conn, trigger, customer_ids, **kw)
    monkeypatch.setattr(jobs, "run_rescreen", spy)
    jobs.daily_sweep(fresh)
    service.load_feed(fresh, "UK", "V2")
    service.update_customer(fresh, "SYN-CUST-A", {"aliases": [{"value": "Chan W M", "type": "documented_alias"}]}, "ana.analyst")
    assert calls == ["daily_sweep", "list_change", "kyc_change"]


def test_failed_job_retry_no_duplicates(fresh):
    approve_both(fresh)
    service.load_feed(fresh, "UK", "V2")
    n_alerts = fresh.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    n_events = fresh.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    for k in (0, 1):
        f = jobs.run_rescreen(fresh, "manual", fail_after=k)
        assert f["status"] == "FAILED"
        r = jobs.retry(fresh, f["job_id"])
        assert r["status"].startswith("COMPLETED") and r["retry_of"] == f["job_id"]
    assert fresh.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == n_alerts
    assert fresh.execute("SELECT COUNT(*) FROM events").fetchone()[0] == n_events
    assert [j["status"] for j in jobs.jobs(fresh)].count("FAILED") == 2


def test_material_kyc_change_can_reopen_with_history(fresh):
    approve_both(fresh)
    non_material = service.update_customer(fresh, "SYN-CUST-A", {"address": {"value": "1 New Road, Testloon", "from": "2026-11-01", "to": None}}, "ana.analyst")
    assert non_material["material"] is False and non_material["rescreen_job"] is None
    res = service.update_customer(fresh, "SYN-CUST-A", {"national_id": {"value": "SYN-WLID-410-7731", "verification": {"status": "verified", "method": "re-check", "document_ref": "DOC-SYN-A-03"}}}, "ana.analyst")
    assert res["material"] and res["rescreen_job"]["counts"]["reopened"] == 1
    assert snapshot_states(fresh)["RESCREEN-A"]["state"] == "OPEN"
    assert views._decisions(fresh, "RESCREEN-A")[0]["validity"] == "INVALIDATED"
    assert fresh.execute("SELECT COUNT(*) FROM customer_versions WHERE customer_id='SYN-CUST-A'").fetchone()[0] == 3


def test_evidence_ids_stable_across_snapshots(fresh):
    approve_both(fresh)
    service.load_feed(fresh, "UK", "V2")
    rows = {(r["subject_type"], r["field"]): r for r in views.case_view(fresh, "RESCREEN-B")["evidence_side_by_side"]["rows"]}
    assert rows[("list_entry", "national_id")]["changed"] is False
    assert rows[("list_entry", "name")]["changed"] is False
    assert rows[("list_entry", "dob")]["changed"] is True and rows[("list_entry", "alias")]["changed"] is True
    v = list(rows[("list_entry", "dob")]["values"].values())
    assert v[0][0]["value"] == "1987-09-03" and v[1][0]["value"] == "1991-06-14" and v[0][0]["evidence_id"] != v[1][0]["evidence_id"]


def test_reviews_pending_vs_completed(fresh):
    rv = views.reviews(fresh)
    assert {p["case_id"] for p in rv["pending"]} == {"RESCREEN-A", "RESCREEN-B"} and rv["completed"] == []
    approve_both(fresh)
    rv = views.reviews(fresh)
    assert rv["pending"] == [] and len(rv["completed"]) == 2
    service.load_feed(fresh, "UK", "V2")
    rv = views.reviews(fresh)
    assert [(p["case_id"], p["reopened"]) for p in rv["pending"]] == [("RESCREEN-B", True)]
    assert sorted((c["case_id"], c["validity"]) for c in rv["completed"]) == [("RESCREEN-A", "CURRENT"), ("RESCREEN-B", "INVALIDATED")]


def test_grok_unavailable_path(fresh, monkeypatch, tmp_path):
    monkeypatch.setattr(views, "REPLAYS", tmp_path)  # no replay files at all
    cv = views.case_view(fresh, "RESCREEN-B")
    assert cv["ai"]["challenger"]["live"]["available"] is False and cv["ai"]["challenger"]["replay"] is None
    assert cv["ai"]["challenger"]["workflow_blocked"] is False
    d1, d2 = ev_id(fresh, "RESCREEN-B", "customer", "dob"), ev_id(fresh, "RESCREEN-B", "list_entry", "dob")
    workflow.propose_closure(fresh, "RESCREEN-B", "sam.analyst", "dob conflict", [d1, d2], "verified_full_dob_conflict", d1, d2)
    assert workflow.approve(fresh, "RESCREEN-B", "kai.senior")["state"] == "RESOLVED"


def test_replay_fixture_is_labelled_and_cites_real_ids(accepted):
    cv = json.loads((accepted["out"] / "case_view_RESCREEN-B.json").read_text())
    rp = cv["ai"]["challenger"]["replay"]
    assert rp["replay"] is True and "REPLAY" in rp["replay_label"] and "NOT produced by a live Grok" in rp["replay_label"]
    known = {e["evidence_id"] for e in cv["current_evidence"]} | {x["evidence_id"] for r in cv["evidence_side_by_side"]["rows"] for v in r["values"].values() for x in v}
    assert set(rp["evidence_ids"]) <= known
    rec = cv["ai"]["suggestions_recorded"][0]
    assert rec["is_replay"] and rec["origin"] == "replay"
    assert cv["ai"]["human_responses"][0]["action"] == "AMEND"   # human response stored separately


def test_jurisdiction_view(accepted):
    out = accepted["out"]
    uk = json.loads((out / "jurisdictions_RESCREEN-B_UK.json").read_text())
    cn = json.loads((out / "jurisdictions_RESCREEN-B_CN.json").read_text())
    assert uk["ordering"] == ["UK", "US", "CN"] and cn["ordering"] == ["CN", "UK", "US"]
    assert uk["default_queue"] != cn["default_queue"]
    rows = {r["jurisdiction"]: r for r in uk["rows"]}
    assert rows["UK"]["check_status"] == "HIT" and rows["UK"]["measures"][0]["measure_id"] == "UK-FM-12"
    assert rows["US"]["check_status"] == "NO_HIT_COMPLETE" and rows["US"]["list_difference"].startswith("LIST_DIFFERENCE")
    assert uk["potential_conflict"]["status"] == "POTENTIAL_CONFLICT_ROUTE_TO_LEGAL" and uk["potential_conflict"]["specific_measure"] == "CN-FM-07"
    a = json.loads((out / "jurisdictions_RESCREEN-A_UK.json").read_text())
    assert a["potential_conflict"]["status"] == "NOT_ESTABLISHED"   # no factual nexus for A


def test_placeholder_dob_is_unknown():
    from rescreen.evidence import customer_items
    c = {"customer_id": "X", "names": [{"value": "Y Z", "type": "primary"}], "aliases": [],
         "dob": {"value": "1900-01-01", "verification": {"status": "unverified", "method": None, "document_ref": None}},
         "national_id": {"value": None, "verification": {"status": "unknown", "method": None, "document_ref": None}},
         "booking_entity": "FICT-BANK-UK"}
    d = [i for i in customer_items(c, "SYN-KYC", "K", 1) if i["field"] == "dob"][0]
    assert d["status"] == "placeholder" and d["precision"] == "unknown" and d["normalised_value"] is None
