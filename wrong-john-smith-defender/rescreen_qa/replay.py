"""QA replay: compare a proposed matcher setting with the frozen baseline on a FIXED snapshot.

For every labelled true link that the baseline catches (LINK or REVIEW) but the proposal misses,
report the stage where it disappears:
  retrieval - blocking/candidate generation never produced the pair
  scoring   - the pair was retrieved but its score fell below the review threshold
Demo policy: any newly missed critical true link -> proposal HELD for review.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from defender.config import canonical_json, freeze, sha256_text
from defender.paths import DRAFT_CONFIG_PATH, FROZEN_CONFIG_PATH
from defender.pipeline import run_pipeline
from evaluation.evaluate import load_labels as load_m1_labels
from rescreen.config import load_scoring
from rescreen.paths import FEEDS, KYC_V1
from rescreen.scoring import score

LABELS = Path(__file__).resolve().parent / "labels.json"

PROPOSALS = {
    "P1-raise-thresholds": {
        "description": "Proposed by screening admin: raise Splink thresholds (link 0.80->0.95, review 0.30->0.90) to cut review volume.",
        "change": lambda p: (p["splink"].__setitem__("link_threshold_probability", 0.95),
                             p["splink"].__setitem__("review_threshold_probability", 0.90)),
    },
    "P2-drop-alias-blocking": {
        "description": "Contrast case: drop the documented-alias blocking rule (retrieval change, thresholds unchanged).",
        "change": lambda p: p["splink"].__setitem__("blocking_rules", [b for b in p["splink"]["blocking_rules"] if b["key"] != "same_alias_group"]),
    },
}


def version_id(params):
    return "CFG-" + sha256_text(canonical_json(params))[:12]


def _m1_decisions(params) -> dict:
    """Milestone-1 dataset under `params` (frozen into a temp file so the normal integrity checks still run)."""
    with tempfile.TemporaryDirectory() as td:
        draft = Path(td) / "draft.json"
        draft.write_text(json.dumps(params), encoding="utf-8")
        frozen = Path(td) / "frozen.json"
        freeze(draft, frozen)
        res = run_pipeline(config_path=frozen)
    return {pid: {"retrieved": True, "decision": p["guarded"]["decision"], "probability": p["splink"]["match_probability"]}
            for pid, p in res["pairs_by_id"].items()}


def _rescreen_decisions(params) -> dict:
    kyc = json.loads(KYC_V1.read_text(encoding="utf-8"))
    feed = json.loads((FEEDS / "uk_v2.json").read_text(encoding="utf-8"))
    cs = [{"data": c, "source_id": kyc["source_id"], "kyc_snapshot_id": kyc["kyc_snapshot_id"], "version": 1} for c in kyc["customers"]]
    es = [{"data": e, "source_id": feed["source_id"], "snapshot_id": f"fixed:{feed['version']}", "jurisdiction": feed["jurisdiction"]} for e in feed["entries"]]
    return {f"{r['customer_id']}|{r['source_id']}|{r['entry_id']}": {"retrieved": True, "decision": r["guard"]["decision"],
                                                                     "probability": r["splink"]["match_probability"]}
            for r in score(cs, es, params)}


def labelled_pairs():
    m1 = load_m1_labels()
    q = json.loads(LABELS.read_text(encoding="utf-8"))
    crit = set(q["milestone_critical_true_links"])
    out = [{"pair": f"{x['left']}|{x['right']}", "truth": x["truth"], "critical": f"{x['left']}|{x['right']}" in crit, "dataset": "milestone1"}
           for x in m1["pair_labels"]]
    out += [{"pair": x["pair"], "truth": x["truth"], "critical": x["critical"], "dataset": "rescreen_v2"} for x in q["pair_labels"]]
    return out


def evaluate_config(params) -> dict:
    dec = {**_m1_decisions(params), **_rescreen_decisions(params)}
    labs = labelled_pairs()
    tm = [l for l in labs if l["truth"] == "match"]
    nm = [l for l in labs if l["truth"] == "non_match"]
    rows = []
    for l in labs:
        d = dec.get(l["pair"], {"retrieved": False, "decision": None, "probability": None})
        rows.append({**l, **d})
    caught = lambda r: r["decision"] in ("LINK", "REVIEW")
    frac = lambda n, d: {"n": n, "d": d, "text": f"{n}/{d}"}
    return {"version_id": version_id(params), "rows": rows, "metrics": {
        "candidate_recall": frac(sum(r["retrieved"] for r in rows if r["truth"] == "match"), len(tm)),
        "missed_true_matches": frac(sum(not caught(r) for r in rows if r["truth"] == "match"), len(tm)),
        "false_positives": frac(sum(r["decision"] == "LINK" for r in rows if r["truth"] == "non_match"), len(nm)),
        "review_volume": frac(sum(r["decision"] == "REVIEW" for r in rows if r["retrieved"]), sum(r["retrieved"] for r in rows)),
    }}


def replay(proposal_key: str, reviewer: str = "rio.senior") -> dict:
    base_params = load_scoring()["parameters"]
    draft = json.loads(DRAFT_CONFIG_PATH.read_text(encoding="utf-8"))
    prop_params = copy.deepcopy({k: v for k, v in draft.items() if not k.startswith("_")})
    assert canonical_json(prop_params) == canonical_json(base_params), "draft and frozen baseline differ"
    PROPOSALS[proposal_key]["change"](prop_params)
    base, prop = evaluate_config(base_params), evaluate_config(prop_params)
    bmap = {r["pair"]: r for r in base["rows"]}
    lost = []
    for r in prop["rows"]:
        b = bmap[r["pair"]]
        if r["truth"] == "match" and b["decision"] in ("LINK", "REVIEW") and r["decision"] not in ("LINK", "REVIEW"):
            stage = "retrieval" if not r["retrieved"] else "scoring"
            detail = ("blocking never generated this pair under the proposed rules" if stage == "retrieval" else
                      f"retrieved, but P(match)={r['probability']:.4f} < proposed review threshold "
                      f"{prop_params['splink']['review_threshold_probability']}")
            lost.append({"pair": r["pair"], "dataset": r["dataset"], "critical": r["critical"], "stage": stage, "detail": detail,
                         "baseline": {"retrieved": b["retrieved"], "decision": b["decision"], "probability": b["probability"]},
                         "proposed": {"retrieved": r["retrieved"], "decision": r["decision"], "probability": r["probability"]}})
    held = any(x["critical"] for x in lost)
    return {"proposal": proposal_key, "description": PROPOSALS[proposal_key]["description"],
            "baseline_version": base["version_id"], "proposal_version": prop["version_id"],
            "changed_parameters": _diff(base_params, prop_params),
            "baseline_metrics": base["metrics"], "proposal_metrics": prop["metrics"],
            "lost_true_links": lost, "policy_outcome": "HELD_FOR_REVIEW" if held else "ELIGIBLE_FOR_APPROVAL",
            "policy": "A proposed setting that turns any labelled critical true link into a miss is held for review.",
            "reviewer_action": {"reviewer": reviewer, "action": "HOLD" if held else "PENDING_REVIEW"},
            "rows": {"baseline": base["rows"], "proposal": prop["rows"]}}


def _diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif canonical_json(a) != canonical_json(b):
        out.append({"parameter": path, "baseline": a, "proposed": b})
    return out


def record(conn, result: dict, at: str):
    conn.execute("INSERT OR REPLACE INTO qa_runs(qa_run_id,proposal_version,baseline_version,result,reviewer,reviewer_action,at) VALUES(?,?,?,?,?,?,?)",
                 ("QA-" + result["proposal_version"], result["proposal_version"], result["baseline_version"],
                  json.dumps(result, ensure_ascii=False), result["reviewer_action"]["reviewer"], result["reviewer_action"]["action"], at))
