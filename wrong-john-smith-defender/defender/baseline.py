"""RapidFuzz name-only baseline. Uses the normalised full name and nothing else."""
from __future__ import annotations

from rapidfuzz import fuzz


def score_pair(left: dict, right: dict, cfg: dict) -> dict:
    a, b = left["derived"]["name_norm"], right["derived"]["name_norm"]
    if a is None or b is None:
        return {"scorer": cfg["scorer"], "score": None, "decision": "NO_LINK",
                "note": "name unknown on at least one record; no score (not treated as a mismatch)"}
    score = float(fuzz.token_sort_ratio(a, b))
    if score >= cfg["link_threshold"]:
        decision = "LINK"
    elif score >= cfg["review_threshold"]:
        decision = "REVIEW"
    else:
        decision = "NO_LINK"
    return {"scorer": cfg["scorer"], "score": round(score, 4), "decision": decision,
            "compared": [a, b],
            "thresholds": {"link": cfg["link_threshold"], "review": cfg["review_threshold"]}}
