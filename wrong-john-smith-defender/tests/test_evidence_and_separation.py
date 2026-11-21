import ast
import builtins
import json
import re
from pathlib import Path

import pytest

from defender import evidence
from defender.evidence import build_packet, evidence_id, export_all, packet_json
from defender.pipeline import run_pipeline
from evaluation.evaluate import LABELS_PATH, load_labels

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_KEYS = {"truth", "label", "labels", "pair_labels", "ground_truth", "is_match", "true_match",
                  "match_label", "expected", "scenario_no", "scenarios", "gold", "non_match"}


def all_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from all_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from all_keys(v)


def all_strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from all_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from all_strings(v)
    elif isinstance(o, str):
        yield o


@pytest.mark.parametrize("case_id", ["CASE-01", "CASE-03", "CASE-08"])
def test_packet_has_required_content_and_no_labels(result, case_id):
    pk = build_packet(result, case_id)
    assert pk["case_id"] == case_id and pk["synthetic"] is True
    assert not (set(all_keys(pk)) & FORBIDDEN_KEYS), set(all_keys(pk)) & FORBIDDEN_KEYS
    text = packet_json(pk)
    labels = load_labels()
    leaked = [x for x in ([v["title"] for v in labels["scenarios"].values()] + [p["note"] for p in labels["pair_labels"]])
              if x in text]
    assert not leaked
    assert LABELS_PATH.name not in text and "evaluation" not in text.lower().replace("evaluation labels", "")
    # raw values, source details, date precision, scores, guard outcome all present
    rec = pk["records"][0]
    assert {"source_id", "source_name"} <= set(rec["source"])
    assert {"raw_value", "date_precision", "verification", "evidence_id"} <= set(rec["fields"]["dob"])
    for p in pk["candidate_pairs"]:
        assert {"name_only", "splink"} <= set(p["scores"])
        assert p["scores"]["splink"]["field_contributions"]
        assert p["guard"]["outcome"] and p["guard"]["dob_check"]["status"]
    assert pk["model"]["parameters"]["splink"]["probability_two_random_records_match"]


def test_evidence_ids_are_stable_and_resolvable(result):
    a, b = packet_json(build_packet(result, "CASE-08")), packet_json(build_packet(run_pipeline(), "CASE-08"))
    assert a == b                                   # byte-identical across independent runs
    pk = json.loads(a)
    known = {f["evidence_id"] for r in pk["records"] for f in r["fields"].values()}
    assert all(re.fullmatch(r"EV-[0-9a-f]{12}", e) for e in known)
    refs = set()
    for p in pk["candidate_pairs"]:
        for c in p["scores"]["splink"]["field_contributions"]:
            refs |= {c["left"]["evidence_id"], c["right"]["evidence_id"]}
        refs |= {p["guard"]["dob_check"]["left"]["evidence_id"], p["guard"]["dob_check"]["right"]["evidence_id"]}
    assert refs and refs <= known
    r0 = result["records_by_id"]["SYN-08-A"]
    assert evidence_id("SYN-08-A", r0["source"]["source_id"], "dob", r0["dob"]["raw"]) in known


def test_committed_exports_match_regeneration(result, tmp_path):
    paths = export_all(result, tmp_path)
    assert len(paths) == 3
    for p in paths:
        assert (ROOT / "exports" / p.name).read_text(encoding="utf-8") == p.read_text(encoding="utf-8"), p.name


def test_scoring_and_export_code_never_touch_labels(result, monkeypatch):
    # static: no import of / reference to the evaluation package or labels in defender/
    for f in (ROOT / "defender").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "evaluation" for a in node.names), f
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "evaluation", f
        assert "labels.json" not in src and "pair_labels" not in src, f
    # dynamic: running pipeline + export opens no file under evaluation/
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    real_read_text, real_read_bytes = Path.read_text, Path.read_bytes
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (opened.append(str(self)), real_read_text(self, *a, **k))[1])
    monkeypatch.setattr(Path, "read_bytes", lambda self: (opened.append(str(self)), real_read_bytes(self))[1])
    r = run_pipeline()
    for c in r["cases"]:
        packet_json(build_packet(r, c))
    assert opened and not [o for o in opened if "evaluation" in o or "labels" in o], opened
    # none of the evaluation modules were imported just by scoring + exporting
    import subprocess, sys
    code = ("import sys; from defender.pipeline import run_pipeline; from defender.evidence import build_packet; "
            "r = run_pipeline(); build_packet(r, 'CASE-01'); "
            "print(any(m == 'evaluation' or m.startswith('evaluation.') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    assert out == "False"


def test_record_data_file_has_no_labels():
    raw = (ROOT / "data" / "records.json").read_text()
    for needle in ("truth", "non_match", "decoy", "ground"):
        assert needle not in raw.lower()
