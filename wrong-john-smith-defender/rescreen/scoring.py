"""Customer x list-entry scoring that REUSES the milestone-1 scorer unchanged:
defender.pipeline.candidate_pairs (blocking), defender.baseline (RapidFuzz name-only),
defender.splink_model.score_pairs (Splink 4 / DuckDB, fixed m/u), defender.guard (DOB contradiction).

Each customer/entry combination is a screening group (used as Splink's case_id), so blocking
only ever pairs a customer with a list entry, never customer-customer or entry-entry.
"""
from __future__ import annotations

from defender import baseline, guard, splink_model
from defender.normalise import alias_lookup_key, normalise_text, parse_dob
from defender.pipeline import candidate_pairs

from .evidence import PLACEHOLDER_DOBS, by_field, classify_pair, customer_items, entry_items


def _variants(names_and_aliases):
    return {alias_lookup_key(v): (field, v) for field, v in names_and_aliases if v}


def _record(rid, group, tag, primary, family, dob_raw, dob_status, nationality):
    dob = parse_dob(None if dob_raw in PLACEHOLDER_DOBS else dob_raw)
    return {"record_id": rid, "case_id": group, "tag": tag,
            "dob": {"raw": dob_raw, "verification": {"status": dob_status}},
            "derived": {"name_norm": normalise_text(primary), "family_key": normalise_text(family),
                        "alias_group": None, "dob": dob, "country_norm": normalise_text(nationality), "city_norm": None}}


def alias_match(c: dict, e: dict, c_items, e_items):
    """Documented alias match: a customer name/alias equals a list name/alias/original-script form,
    other than primary == primary (that is an exact name match, not an alias)."""
    cp, ep = alias_lookup_key(c["names"][0]["value"]), alias_lookup_key(e["names"][0]["value"])
    cv = _variants([("name", n["value"]) for n in c["names"]] + [("alias", a["value"]) for a in c.get("aliases", [])]
                   + [("original_script_name", c.get("original_script_name"))])
    ev = _variants([("name" if n["type"] != "original_script" else "original_script_name", n["value"]) for n in e["names"]]
                   + [("alias", a["value"]) for a in e.get("aliases", [])])
    common = sorted(k for k in set(cv) & set(ev) if not (k == cp and k == ep))
    if not common or cp == ep:
        return None
    k = common[0]
    cfield, cval = cv[k]
    efield, evals = ev[k]
    cid = next(i["evidence_id"] for i in c_items if i["field"] == cfield and i["observed_value"] == cval)
    eid = next(i["evidence_id"] for i in e_items if i["field"] == efield and i["observed_value"] == evals)
    return {"form": cval, "customer_field": cfield, "entry_field": efield, "evidence_ids": [cid, eid], "key": k}


def score(customers: list[dict], entries: list[dict], params: dict) -> list[dict]:
    """customers: [{'data', 'source_id', 'kyc_snapshot_id', 'version'}]; entries: [{'data', 'source_id', 'snapshot_id', 'jurisdiction'}].
    Returns one result per RETRIEVED customer/entry pair (pairs blocking never produced are absent)."""
    records, groups = [], {}
    for c in customers:
        cd = c["data"]
        c_items = customer_items(cd, c["source_id"], c["kyc_snapshot_id"], c["version"])
        for e in entries:
            ed = e["data"]
            e_items = entry_items(ed, e["source_id"], e["snapshot_id"])
            group = f"{cd['customer_id']}|{e['source_id']}|{ed['entry_id']}"
            cr = _record(f"C:{group}", group, "C", cd["names"][0]["value"], cd["names"][0].get("family"),
                         cd["dob"]["value"], cd["dob"]["verification"]["status"], cd.get("nationality"))
            er = _record(f"W:{group}", group, "W", ed["names"][0]["value"], ed["names"][0].get("family"),
                         ed["dob"]["value"], by_field(e_items)["dob"][0]["verification"]["status"], ed.get("nationality"))
            am = alias_match(cd, ed, c_items, e_items)
            if am:
                cr["derived"]["alias_group"] = er["derived"]["alias_group"] = "DOCALIAS:" + am["key"]
            records += [cr, er]
            groups[group] = {"customer": c, "entry": e, "c_items": c_items, "e_items": e_items, "alias": am,
                             "records": {cr["record_id"]: cr, er["record_id"]: er}}
    pairs = candidate_pairs(records, params["splink"]["blocking_rules"])
    sp = splink_model.score_pairs(records, params["splink"]) if pairs else {"pairs": {}}
    if set(sp["pairs"]) != {(p["left"], p["right"]) for p in pairs}:
        raise RuntimeError("candidate pairs differ between generator and Splink blocking")
    out = []
    for p in pairs:
        g = groups[p["case_id"]]
        recs = g["records"]
        p["name_only"] = baseline.score_pair(recs[p["left"]], recs[p["right"]], params["name_only"])
        s = sp["pairs"][(p["left"], p["right"])]
        s["decision"] = splink_model.decide(s["match_probability"], params["splink"])
        p["splink"] = s
        gr = guard.apply_guard(recs, [p], params["guard"])
        p["guarded"] = gr["pairs"][p["pair_id"]]
        cd, ed = g["customer"]["data"], g["entry"]["data"]
        raise_alert = (p["name_only"]["decision"] != "NO_LINK" or s["decision"] != "NO_LINK"
                       or p["guarded"]["decision"] != "NO_LINK")
        out.append({
            "customer_id": cd["customer_id"], "source_id": g["entry"]["source_id"], "entry_id": ed["entry_id"],
            "jurisdiction": g["entry"]["jurisdiction"], "snapshot_id": g["entry"]["snapshot_id"],
            "kyc_snapshot_id": g["customer"]["kyc_snapshot_id"], "kyc_version": g["customer"]["version"],
            "retrieval": {"blocking_rules": p["blocking_rules"]},
            "alias_match": g["alias"],
            "name_only": p["name_only"],
            "splink": {k: s[k] for k in ("match_weight", "match_probability", "prior_match_weight", "decision", "contributions")},
            "guard": {k: p["guarded"][k] for k in ("decision", "outcome", "reasons", "dob_check", "changed_by_guard")},
            "raise_alert": raise_alert,
            "evidence_classification": classify_pair(g["c_items"], g["e_items"], s["contributions"], g["alias"]),
            "customer_evidence": g["c_items"], "entry_evidence": g["e_items"],
        })
    out.sort(key=lambda r: (r["customer_id"], r["source_id"], r["entry_id"]))
    return out
