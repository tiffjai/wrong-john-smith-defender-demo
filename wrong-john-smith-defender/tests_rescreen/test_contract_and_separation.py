import ast
import glob
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import jsonschema
import pytest

from rescreen import acceptance
from rescreen.paths import SCHEMA_DIR

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FOR = {"case_view_*.json": "case_view", "evidence_packet_*.json": "evidence_packet", "challenger_handoff_*.json": "challenger_handoff",
              "reviews.json": "reviews", "jurisdictions_*.json": "jurisdictions", "feeds_status.json": "feeds_status"}
FORBIDDEN_KEYS = {"truth", "label", "labels", "pair_labels", "ground_truth", "is_match", "critical", "milestone_critical_true_links"}


def keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from keys(v)


def test_exports_validate_against_schemas(accepted):
    n = 0
    for pat, name in SCHEMA_FOR.items():
        schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())
        for f in glob.glob(str(accepted["out"] / pat)):
            jsonschema.Draft202012Validator(schema).validate(json.loads(Path(f).read_text()))
            n += 1
    assert n == 2 + 2 + 2 + 1 + 6 + 1


def test_qa_replay_findings_and_schema(tmp_path):
    from rescreen_qa.replay import PROPOSALS, replay
    res = {k: replay(k) for k in PROPOSALS}
    p1, p2 = res["P1-raise-thresholds"], res["P2-drop-alias-blocking"]
    assert [(x["pair"], x["stage"]) for x in p1["lost_true_links"]] == [("SYN-08-A|SYN-08-B", "scoring")]
    assert [(x["pair"], x["stage"]) for x in p2["lost_true_links"]] == [("SYN-03-A|SYN-03-B", "retrieval")]
    assert p1["policy_outcome"] == p2["policy_outcome"] == "HELD_FOR_REVIEW"
    assert p1["baseline_metrics"]["missed_true_matches"]["text"] == "0/3" and p1["proposal_metrics"]["missed_true_matches"]["text"] == "1/3"
    assert p1["baseline_version"] != p1["proposal_version"]
    schema = json.loads((SCHEMA_DIR / "qa_replay.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate({"contract_version": "rescreen-contract/1.0", "replays": list(res.values())})


def test_no_label_leak_in_exports(accepted):
    q = json.loads((ROOT / "rescreen_qa" / "labels.json").read_text())
    m1 = json.loads((ROOT / "evaluation" / "labels.json").read_text())
    notes = [x["note"] for x in q["pair_labels"]] + [x["note"] for x in m1["pair_labels"]]
    for f in accepted["out"].glob("*.json"):
        if f.name == "acceptance_report.json":
            continue
        obj = json.loads(f.read_text())
        assert not (set(keys(obj)) & FORBIDDEN_KEYS), (f.name, set(keys(obj)) & FORBIDDEN_KEYS)
        text = f.read_text()
        assert not [n for n in notes if n in text], f.name
        assert "non_match" not in text


def test_handoff_contains_only_changes_basis_ids(accepted):
    h = json.loads((accepted["out"] / "challenger_handoff_RESCREEN-B.json").read_text())
    assert set(h) == {"contract_version", "packet_type", "synthetic", "case_id", "changed_fields", "approval_basis", "evidence_ids", "requested_output"}
    text = json.dumps(h)
    for verdict in ("REOPENED", "RESOLVED", "INVALIDATED", "FALSE_POSITIVE", "AWAITING_EVIDENCE", "HOLDS"):
        assert verdict not in text
    assert not ({"state", "disposition", "validity", "evaluation"} & set(keys(h)))


def test_rescreen_package_never_imports_labels():
    for f in (ROOT / "rescreen").glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(m.split(".")[0] in ("evaluation", "rescreen_qa") for m in mods), f
        assert "labels.json" not in f.read_text(), f
    code = ("import sys; from rescreen import acceptance; import tempfile, pathlib; d=tempfile.mkdtemp(); "
            "acceptance.run(d+'/a.sqlite', pathlib.Path(d)/'o', verbose=False); "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('evaluation','rescreen_qa')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    assert out == "[]"


def test_acceptance_runs_offline_and_is_deterministic(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    r1 = acceptance.run(str(tmp_path / "a.sqlite"), tmp_path / "o1", verbose=False)
    r2 = acceptance.run(str(tmp_path / "b.sqlite"), tmp_path / "o2", verbose=False)
    assert r1["passed"] and r2["passed"]
    for f in (tmp_path / "o1").glob("*.json"):
        assert f.read_text() == (tmp_path / "o2" / f.name).read_text(), f.name


def test_http_api_end_to_end(tmp_path):
    from http.server import ThreadingHTTPServer

    from rescreen import service
    from rescreen.api import App, make_handler
    service.reset(tmp_path / "api.sqlite")["conn"].close()
    app = App(tmp_path / "api.sqlite")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    def call(method, path, body=None, actor=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body or {}).encode() if method == "POST" else None,
                                     headers={"Content-Type": "application/json", **({"X-Demo-Actor": actor} if actor else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert call("GET", "/api/health")[1]["status"] == "ok"
        cv = call("GET", "/api/cases/RESCREEN-B")[1]
        ev = {(i["subject_type"], i["field"]): i["evidence_id"] for i in cv["current_evidence"]}
        body = {"rationale": "dob conflict", "evidence_ids": [], "basis_type": "verified_full_dob_conflict",
                "customer_evidence_id": ev[("customer", "dob")], "list_evidence_id": ev[("list_entry", "dob")]}
        assert call("POST", "/api/cases/RESCREEN-B/propose", body, "kai.senior")[0] == 200
        code, err = call("POST", "/api/cases/RESCREEN-B/approve", {}, "kai.senior")
        assert code == 403 and err["error"] == "SELF_APPROVAL_FORBIDDEN"
        assert call("POST", "/api/cases/RESCREEN-B/approve", {"comment": "ok"}, "rio.senior")[1]["state"] == "RESOLVED"
        assert call("POST", "/api/feeds/load", {"jurisdiction": "UK", "version": "V2"})[1]["rescreen_job"]["counts"]["reopened"] == 1
        assert call("POST", "/api/feeds/load", {"jurisdiction": "UK", "version": "V2"})[1]["result"] == "NO_UPDATE"
        assert call("POST", "/api/jobs/sweep")[1]["status"].startswith("COMPLETED")
        rv = call("GET", "/api/reviews")[1]
        assert [p["case_id"] for p in rv["pending"]] == ["RESCREEN-A", "RESCREEN-B"]   # A was never closed in this flow
        assert call("GET", "/api/cases/RESCREEN-B/jurisdictions?primary=CN")[1]["ordering"][0] == "CN"
        assert call("POST", "/api/feeds/simulate-failure")[1]["result"] == "FAILED_VALIDATION"
        assert call("GET", "/api/cases/NOPE")[0] == 404
    finally:
        srv.shutdown()
