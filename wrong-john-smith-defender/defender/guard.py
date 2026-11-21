"""Deterministic contradiction guard.

Rule (frozen): both records carry a date of birth that is
  * FULL precision (year, month and day known), AND
  * VERIFIED (verification.status == 'verified'), AND
  * the two dates differ.
Then the pair is a contradiction and is routed to analyst review.

Never a contradiction: partial-precision dates, unverified dates, unknown dates, unparseable dates.
Unknown fields stay unknown: they are reported as 'not_assessable', never imputed or counted as a mismatch.
The guard never *lowers* or hides a pair: it only escalates LINK/REVIEW pairs to REVIEW.
"""
from __future__ import annotations


def dob_check(left: dict, right: dict) -> dict:
    ld, rd = left["derived"]["dob"], right["derived"]["dob"]
    lv, rv = left["dob"]["verification"]["status"], right["dob"]["verification"]["status"]
    base = {
        "check": "verified_full_dob_contradiction",
        "left": {"record_id": left["record_id"], "raw": ld["raw"], "value": ld["value"], "precision": ld["precision"], "verification": lv},
        "right": {"record_id": right["record_id"], "raw": rd["raw"], "value": rd["value"], "precision": rd["precision"], "verification": rv},
    }
    reasons = []
    for side, d, v in (("left", ld, lv), ("right", rd, rv)):
        if d["precision"] == "unknown":
            reasons.append(f"{side} date of birth is unknown (kept unknown)")
        elif d["precision"] == "unparseable":
            reasons.append(f"{side} date of birth could not be parsed (treated as unknown)")
        elif d["precision"] != "full":
            reasons.append(f"{side} date of birth has {d['precision']} precision, not full")
        if v != "verified":
            reasons.append(f"{side} date of birth is {v}, not verified")
    if reasons:
        return {**base, "status": "not_assessable", "reasons": reasons}
    if ld["value"] != rd["value"]:
        return {**base, "status": "contradiction",
                "reasons": [f"verified full dates of birth differ: {ld['value']} vs {rd['value']}"]}
    return {**base, "status": "consistent", "reasons": ["verified full dates of birth are identical"]}


class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def apply_guard(records_by_id: dict, pairs: list[dict], guard_cfg: dict) -> dict:
    """pairs: list of dicts with left, right, splink.decision. Returns per-pair guard outcomes + components."""
    apply_to = set(guard_cfg["apply_to_decisions"])
    checks = {p["pair_id"]: dob_check(records_by_id[p["left"]], records_by_id[p["right"]]) for p in pairs}

    uf = _UF(list(records_by_id))
    if guard_cfg.get("chain_check", True):
        for p in pairs:
            if p["splink"]["decision"] == "LINK":
                uf.union(p["left"], p["right"])
    comps: dict[str, list[str]] = {}
    for rid in records_by_id:
        comps.setdefault(uf.find(rid), []).append(rid)
    pmap = {p["pair_id"]: p for p in pairs}
    components = []
    for members in comps.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        contradicting = sorted(pid for pid, c in checks.items() if c["status"] == "contradiction"
                               and pmap[pid]["left"] in members and pmap[pid]["right"] in members)
        components.append({"records": members, "contradicting_pairs": contradicting,
                           "has_contradiction": bool(contradicting)})

    outcomes = {}
    for p in pairs:
        pid, sd = p["pair_id"], p["splink"]["decision"]
        chk = checks[pid]
        comp = next((c for c in components if p["left"] in c["records"] and p["right"] in c["records"]), None)
        direct = chk["status"] == "contradiction"
        chain = bool(comp and comp["has_contradiction"])
        reasons = []
        if chain or (direct and sd in apply_to):
            decision = "REVIEW"
            outcome = ("ROUTED_TO_REVIEW_DIRECT_CONTRADICTION" if direct
                       else "ROUTED_TO_REVIEW_CHAIN_CONTRADICTION")
            if direct:
                reasons.append("direct: " + chk["reasons"][0])
            if chain:
                reasons.append("chain: linked records " + ", ".join(comp["records"]) +
                               " contain a verified full-DOB contradiction in pair(s) " +
                               ", ".join(comp["contradicting_pairs"]))
        elif direct:
            decision, outcome = sd, "CONTRADICTION_NOTED_NOT_SURFACED"
            reasons.append("direct: " + chk["reasons"][0] +
                           f"; pair decision is {sd} and it is in no linked chain, so nothing to escalate")
        else:
            decision, outcome = sd, "PASS_NO_CONTRADICTION"
            reasons.append("no verified full-DOB contradiction applies to this pair" +
                           (f" (DOB check not assessable: {'; '.join(chk['reasons'])})"
                            if chk["status"] == "not_assessable" else ""))
        outcomes[pid] = {"decision": decision, "outcome": outcome, "reasons": reasons,
                         "dob_check": chk, "component": comp["records"] if comp else None,
                         "changed_by_guard": decision != sd}
    return {"pairs": outcomes, "components": components}
