"""Approval basis: what an approval rests on, and whether it still holds on current evidence."""
from __future__ import annotations

BASIS_FIELDS = {"verified_identifier_conflict": "national_id", "verified_full_dob_conflict": "dob"}


class BasisError(ValueError):
    pass


def _find(items, eid):
    return next((i for i in items if i["evidence_id"] == eid), None)


def _current(items, field):
    return next((i for i in items if i["field"] == field), None)


def _condition(field, ci, ei):
    if not ci or not ei:
        return False, "evidence missing"
    if ci["status"] != "known" or ei["status"] != "known":
        return False, "value unknown on at least one side"
    if ci["verification"]["status"] != "verified" or ei["verification"]["status"] != "verified":
        return False, "not verified on both sides"
    if field == "dob":
        if ci["precision"] != "full" or ei["precision"] != "full":
            return False, "not full precision on both sides"
        if ci["normalised_value"] == ei["normalised_value"]:
            return False, f"DOBs now agree ({ci['normalised_value']})"
        return True, f"verified full DOBs differ ({ci['normalised_value']} vs {ei['normalised_value']})"
    if ci["observed_value"] == ei["observed_value"]:
        return False, "identifiers now equal"
    return True, f"verified identifiers differ ({ci['observed_value']} vs {ei['observed_value']})"


def make_basis(type_: str, customer_evidence_id: str, list_evidence_id: str, c_items, e_items) -> dict:
    if type_ not in BASIS_FIELDS:
        raise BasisError(f"unknown basis type {type_!r}")
    field = BASIS_FIELDS[type_]
    ci, ei = _find(c_items, customer_evidence_id), _find(e_items, list_evidence_id)
    if not ci or ci["field"] != field or not ei or ei["field"] != field:
        raise BasisError(f"basis {type_} needs current {field} evidence IDs for the customer and the list entry")
    ok, why = _condition(field, ci, ei)
    if not ok:
        raise BasisError(f"basis does not hold on current evidence: {why}")
    return {"type": type_, "field": field, "customer_evidence_id": customer_evidence_id, "list_evidence_id": list_evidence_id,
            "statement": f"{why}: customer {customer_evidence_id} vs list {list_evidence_id}",
            "cited_values": {"customer": ci["observed_value"], "list": ei["observed_value"]}}


def evaluate(basis: dict, c_items, e_items) -> dict:
    field = basis["field"]
    ci, ei = _current(c_items, field), _current(e_items, field)
    same_ids = bool(ci and ei and ci["evidence_id"] == basis["customer_evidence_id"] and ei["evidence_id"] == basis["list_evidence_id"])
    ok, why = _condition(field, ci, ei)
    if same_ids and ok:
        status = "HOLDS"
    elif ok:
        status = "CITED_EVIDENCE_SUPERSEDED"
    else:
        status = "BASIS_NO_LONGER_HOLDS"
    return {"status": status, "holds": status == "HOLDS", "reason": why,
            "cited": {"customer_evidence_id": basis["customer_evidence_id"], "list_evidence_id": basis["list_evidence_id"]},
            "current": {"customer_evidence_id": ci["evidence_id"] if ci else None, "customer_value": ci["observed_value"] if ci else None,
                        "list_evidence_id": ei["evidence_id"] if ei else None, "list_value": ei["observed_value"] if ei else None}}
