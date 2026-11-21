"""Evidence items with stable IDs for customers (KYC) and list entries (feed snapshots).

evidence_id = defender.evidence.evidence_id(subject_id, source_id, field, observed_value):
the same observed value from the same source keeps the same ID across snapshots; a changed
value gets a new ID. The snapshot in which an item was observed is carried separately.
"""
from __future__ import annotations

from defender.evidence import evidence_id
from defender.normalise import normalise_text, parse_dob

PLACEHOLDER_DOBS = {"1900-01-01", "1901-01-01", "0000-00-00", "01/01/1900"}
LIST_VERIFICATION = {"listed_by_authority": ("verified", "published by the (fictional) listing authority")}


def _dob_item(subject_type, subject_id, source_id, snapshot_id, raw, verification, provenance):
    if raw in PLACEHOLDER_DOBS:
        d = {"value": None, "precision": "unknown", "year": None, "month": None, "day": None}
        status = "placeholder"
    else:
        d = parse_dob(raw)
        status = "known" if d["precision"] in ("full", "year_month", "year") else "unknown"
    return {
        "evidence_id": evidence_id(subject_id, source_id, "dob", raw),
        "subject_type": subject_type, "subject_id": subject_id, "field": "dob",
        "observed_value": raw, "normalised_value": d["value"], "precision": d["precision"],
        "parsed": {"year": d["year"], "month": d["month"], "day": d["day"]},
        "status": status, "verification": verification,
        "source_id": source_id, "source_snapshot_id": snapshot_id, "provenance": provenance,
    }


def _item(subject_type, subject_id, source_id, snapshot_id, field, raw, verification=None, provenance=None, extra=None):
    it = {
        "evidence_id": evidence_id(subject_id, source_id, field, raw),
        "subject_type": subject_type, "subject_id": subject_id, "field": field,
        "observed_value": raw,
        "normalised_value": normalise_text(raw) if isinstance(raw, str) else raw,
        "precision": "exact" if raw not in (None, "") else "unknown",
        "status": "known" if raw not in (None, "") else "unknown",
        "verification": verification or {"status": "unknown" if raw in (None, "") else "unverified", "method": None, "document_ref": None},
        "source_id": source_id, "source_snapshot_id": snapshot_id, "provenance": provenance,
    }
    if extra:
        it.update(extra)
    return it


def customer_items(c: dict, source_id: str, kyc_snapshot_id: str, kyc_version: int) -> list[dict]:
    sid, cid = source_id, c["customer_id"]
    prov = {"system": "synthetic KYC", "kyc_snapshot_id": kyc_snapshot_id, "customer_version": kyc_version}
    items = []
    for n in c["names"]:
        items.append(_item("customer", cid, sid, kyc_snapshot_id, "name", n["value"],
                           provenance=prov, extra={"name_type": n["type"], "script": n.get("script")}))
    items.append(_item("customer", cid, sid, kyc_snapshot_id, "original_script_name", c.get("original_script_name"), provenance=prov))
    for a in c.get("aliases", []):
        items.append(_item("customer", cid, sid, kyc_snapshot_id, "alias", a["value"],
                           verification={"status": "documented", "method": a.get("type"), "document_ref": a.get("document_ref")},
                           provenance=prov, extra={"scheme": a.get("scheme")}))
    items.append(_dob_item("customer", cid, sid, kyc_snapshot_id, c["dob"]["value"], c["dob"]["verification"], prov))
    items.append(_item("customer", cid, sid, kyc_snapshot_id, "national_id", c["national_id"]["value"],
                       verification=c["national_id"]["verification"], provenance=prov))
    items.append(_item("customer", cid, sid, kyc_snapshot_id, "nationality", c.get("nationality"), provenance=prov))
    addr = c.get("address") or {}
    items.append(_item("customer", cid, sid, kyc_snapshot_id, "address", addr.get("value"), provenance=prov,
                       extra={"address_from": addr.get("from"), "address_to": addr.get("to")}))
    items.append(_item("customer", cid, sid, kyc_snapshot_id, "booking_entity", c.get("booking_entity"), provenance=prov))
    return items


def entry_items(e: dict, source_id: str, snapshot_id: str) -> list[dict]:
    eid = e["entry_id"]
    prov = {"system": "list feed", "snapshot_id": snapshot_id}

    def ver(v):
        st, method = LIST_VERIFICATION.get(v, ("unknown" if v in (None, "unknown") else "unverified", v))
        return {"status": st, "method": method, "document_ref": None}

    items = []
    for n in e["names"]:
        field = "original_script_name" if n["type"] == "original_script" else "name"
        items.append(_item("list_entry", eid, source_id, snapshot_id, field, n["value"],
                           verification=ver("listed_by_authority"), provenance=prov,
                           extra={"name_type": n["type"], "script": n.get("script")}))
    for a in e.get("aliases", []):
        items.append(_item("list_entry", eid, source_id, snapshot_id, "alias", a["value"],
                           verification=ver("listed_by_authority"), provenance=prov, extra={"scheme": a.get("scheme")}))
    items.append(_dob_item("list_entry", eid, source_id, snapshot_id, e["dob"]["value"], ver(e["dob"].get("verification")), prov))
    items.append(_item("list_entry", eid, source_id, snapshot_id, "national_id", e["national_id"]["value"],
                       verification=ver(e["national_id"].get("verification")) if e["national_id"]["value"] else None,
                       provenance=prov))
    items.append(_item("list_entry", eid, source_id, snapshot_id, "nationality", e.get("nationality"),
                       verification=ver("listed_by_authority"), provenance=prov))
    for m in e.get("measures", []):
        items.append(_item("list_entry", eid, source_id, snapshot_id, "measure", m["measure_id"],
                           verification=ver("listed_by_authority"), provenance=prov, extra={"description": m.get("description")}))
    return items


def by_field(items: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in items:
        out.setdefault(it["field"], []).append(it)
    return out


def classify_pair(c_items: list[dict], e_items: list[dict], splink_contrib: list[dict], alias_match: dict | None) -> list[dict]:
    """Label each evidence dimension as supporting / conflicting / missing / neutral with cited IDs."""
    cf, ef = by_field(c_items), by_field(e_items)
    out = []
    lvl = {c["field"]: c["level_key"] for c in splink_contrib}
    cn, en = cf["name"][0], ef["name"][0]
    name_lvl = lvl.get("name")
    out.append({"dimension": "name",
                "classification": "supporting" if name_lvl in ("exact", "alias", "jw_092") else ("neutral" if name_lvl == "jw_080" else "conflicting"),
                "detail": f"Splink name level '{name_lvl}': {cn['observed_value']!r} vs {en['observed_value']!r}",
                "evidence_ids": [cn["evidence_id"], en["evidence_id"]]})
    if alias_match:
        out.append({"dimension": "documented_alias", "classification": "supporting",
                    "detail": f"documented alias match on {alias_match['form']!r} ({alias_match['customer_field']} ↔ {alias_match['entry_field']})",
                    "evidence_ids": alias_match["evidence_ids"]})
    cd, ed = cf["dob"][0], ef["dob"][0]
    if cd["status"] != "known" or ed["status"] != "known":
        cls, det = "missing", "DOB unknown/placeholder on at least one side (kept unknown, not a mismatch)"
    elif lvl.get("dob") in ("full_exact", "year_month", "year_only"):
        cls, det = "supporting", f"DOB agrees at shared precision ({cd['normalised_value']} vs {ed['normalised_value']})"
    else:
        both_vf = all(x["precision"] == "full" and x["verification"]["status"] == "verified" for x in (cd, ed))
        cls = "conflicting"
        det = ("verified full DOBs differ" if both_vf else "DOBs differ at shared precision (not both verified full)") + \
              f": {cd['normalised_value']} vs {ed['normalised_value']}"
    out.append({"dimension": "dob", "classification": cls, "detail": det,
                "precision": [cd["precision"], ed["precision"]],
                "verification": [cd["verification"]["status"], ed["verification"]["status"]],
                "evidence_ids": [cd["evidence_id"], ed["evidence_id"]]})
    ci, ei = cf["national_id"][0], ef["national_id"][0]
    if ci["status"] != "known" or ei["status"] != "known":
        cls, det = "missing", "national ID unknown on at least one side"
    elif ci["observed_value"] == ei["observed_value"]:
        cls, det = "supporting", "identifiers equal"
    else:
        both_v = ci["verification"]["status"] == "verified" and ei["verification"]["status"] == "verified"
        cls, det = "conflicting", ("verified identifiers differ" if both_v else "identifiers differ (not both verified)")
    out.append({"dimension": "national_id", "classification": cls, "detail": det, "evidence_ids": [ci["evidence_id"], ei["evidence_id"]]})
    cnat, enat = cf["nationality"][0], ef["nationality"][0]
    if cnat["status"] != "known" or enat["status"] != "known":
        cls = "missing"
    else:
        cls = "supporting" if cnat["normalised_value"] == enat["normalised_value"] else "conflicting"
    out.append({"dimension": "nationality", "classification": cls, "detail": f"{cnat['observed_value']} vs {enat['observed_value']}",
                "evidence_ids": [cnat["evidence_id"], enat["evidence_id"]]})
    return out
