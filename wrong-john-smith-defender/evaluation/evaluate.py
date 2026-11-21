"""Evaluation. Reads the FROZEN config, the pipeline output and the labels file.

Run:  python -m evaluation.evaluate        (writes evaluation/results.json)

This module is the only code that reads evaluation/labels.json. It never changes thresholds:
it refuses to run if the frozen config hash does not verify, and it records frozen_at and the
config hash next to the results.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from defender.pipeline import METHODS, decision_of, run_pipeline

LABELS_PATH = Path(__file__).resolve().parent / "labels.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
METHOD_NAMES = {"name_only": "Name-only (RapidFuzz)", "splink": "Splink", "splink_guard": "Splink + contradiction guard"}


def load_labels(path: Path = LABELS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pair_id(l, r):
    return f"{l}|{r}"


def evaluate(result: dict | None = None, labels: dict | None = None, ablation_result: dict | None = None) -> dict:
    result = result or run_pipeline()
    labels = labels or load_labels()
    truth = {_pair_id(x["left"], x["right"]): x for x in labels["pair_labels"]}
    cand = set(result["pairs_by_id"])
    true_matches = sorted(k for k, v in truth.items() if v["truth"] == "match")
    non_matches = sorted(k for k, v in truth.items() if v["truth"] == "non_match")
    n_cand = len(cand)

    def frac(n, d):
        return {"n": n, "d": d, "text": f"{n}/{d}", "pct": (round(100 * n / d, 1) if d else None)}

    recall_n = sum(1 for k in true_matches if k in cand)
    metrics = {"candidate_recall": frac(recall_n, len(true_matches)),
               "candidate_pairs_total": n_cand,
               "candidate_pairs_missing_a_true_match": sorted(k for k in true_matches if k not in cand)}
    by_method = {}
    for m in METHODS:
        dec = {pid: decision_of(result["pairs_by_id"][pid], m) for pid in cand}
        fp = sorted(k for k in non_matches if dec.get(k) == "LINK")
        missed = sorted(k for k in true_matches if dec.get(k) not in ("LINK", "REVIEW"))
        review = sorted(k for k, v in dec.items() if v == "REVIEW")
        tp_linked = sorted(k for k in true_matches if dec.get(k) == "LINK")
        tm_review = sorted(k for k in true_matches if dec.get(k) == "REVIEW")
        nm_review = sorted(k for k in non_matches if dec.get(k) == "REVIEW")
        by_method[m] = {
            "name": METHOD_NAMES[m],
            "false_positives": {**frac(len(fp), len(non_matches)), "pairs": fp,
                                "definition": "labelled non-match pairs auto-linked (decision LINK) / labelled non-match pairs"},
            "missed_true_matches": {**frac(len(missed), len(true_matches)), "pairs": missed,
                                    "definition": "labelled true-match pairs with neither LINK nor REVIEW (incl. pairs not in the candidate set) / labelled true-match pairs"},
            "manual_review": {**frac(len(review), n_cand), "pairs": review,
                              "definition": "candidate pairs routed to analyst review / candidate pairs"},
            "true_matches_linked": {**frac(len(tp_linked), len(true_matches)), "pairs": tp_linked},
            "true_matches_in_review": {**frac(len(tm_review), len(true_matches)), "pairs": tm_review},
            "non_matches_in_review": {**frac(len(nm_review), len(non_matches)), "pairs": nm_review},
            "decisions": dec,
        }
    metrics["by_method"] = by_method

    per_case = {}
    for case_id, c in result["cases"].items():
        per_case[case_id] = {"scenario": labels["scenarios"].get(case_id), "routes": c["routes"],
                             "pairs": len(c["pairs"]),
                             "true_matches": sum(1 for k in c["pairs"] if truth.get(k, {}).get("truth") == "match"),
                             "non_matches": sum(1 for k in c["pairs"] if truth.get(k, {}).get("truth") == "non_match")}
    metrics["per_case"] = per_case

    if ablation_result is None:
        ablation_result = run_pipeline(use_alias=False)
    ab_cand = set(ablation_result["pairs_by_id"])
    metrics["ablation_no_alias_table"] = {
        "description": "Same frozen config, alias table disabled (no alias blocking rule hits, no alias comparison level)",
        "candidate_pairs_total": len(ab_cand),
        "candidate_recall": frac(sum(1 for k in true_matches if k in ab_cand), len(true_matches)),
        "true_matches_not_candidates": sorted(k for k in true_matches if k not in ab_cand),
    }
    cfg = result["config"]
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frozen_at": cfg["frozen_at"], "config_sha256": cfg["config_sha256"],
        "thresholds": {"name_only": cfg["parameters"]["name_only"],
                       "splink": {k: cfg["parameters"]["splink"][k] for k in
                                  ("link_threshold_probability", "review_threshold_probability")}},
        "labels_sha256": __import__("hashlib").sha256(LABELS_PATH.read_bytes()).hexdigest(),
        "denominators": {"candidate_pairs": n_cand, "labelled_true_matches": len(true_matches),
                         "labelled_non_matches": len(non_matches)},
        "metrics": metrics,
    }


if __name__ == "__main__":
    res = evaluate()
    assert res["frozen_at"] <= res["evaluated_at"], "evaluation must run after the config was frozen"
    RESULTS_PATH.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = res["metrics"]
    print(f"config_sha256={res['config_sha256'][:16]}.. frozen_at={res['frozen_at']} evaluated_at={res['evaluated_at']}")
    print(f"candidate pairs={res['denominators']['candidate_pairs']}  candidate recall={m['candidate_recall']['text']}")
    for k, v in m["by_method"].items():
        print(f"{v['name']:32s} FP {v['false_positives']['text']}  missed {v['missed_true_matches']['text']}  "
              f"review {v['manual_review']['text']}")
    print("ablation (no alias table): recall", m["ablation_no_alias_table"]["candidate_recall"]["text"],
          "pairs", m["ablation_no_alias_table"]["candidate_pairs_total"])
