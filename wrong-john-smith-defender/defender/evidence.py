"""Per-case JSON evidence packet for independent review (DefenderChallenger).

Self-contained: raw values, source/verification details, date precision, scores, field
contributions, model parameters and guard outcome. Contains NO evaluation labels and never
imports evaluation code. Deterministic (no generation timestamp, stable evidence IDs).
"""
from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path

from .paths import EXPORTS_DIR

SCHEMA_VERSION = "1.0"
FIELDS = ("name", "dob", "country", "city")


def evidence_id(record_id: str, source_id: str, field: str, raw_value) -> str:
    """Stable ID: hash of record + source + field + raw value (independent of scoring)."""
    payload = json.dumps([record_id, source_id, field, raw_value], ensure_ascii=False, separators=(",", ":"))
    return "EV-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _stable_id(prefix: str, *parts) -> str:
    payload = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _round(obj, nd=9):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def record_evidence(rec: dict) -> dict:
    rid, sid, d = rec["record_id"], rec["source"]["source_id"], rec["derived"]
    ver = rec["dob"]["verification"]
    fields = {}
    fields["name"] = {
        "evidence_id": evidence_id(rid, sid, "name", rec["name"]["raw"]),
        "raw_value": rec["name"]["raw"], "family_name_raw": rec["name"].get("family"),
        "given_name_raw": rec["name"].get("given"), "normalised_value": d["name_norm"],
        "status": "known" if rec["name"]["raw"] else "unknown",
        "alias_group": d["alias_group"],
    }
    dob = d["dob"]
    fields["dob"] = {
        "evidence_id": evidence_id(rid, sid, "dob", rec["dob"]["raw"]),
        "raw_value": rec["dob"]["raw"], "normalised_value": dob["value"],
        "date_precision": dob["precision"],
        "parsed": {"year": dob["year"], "month": dob["month"], "day": dob["day"]},
        "status": "known" if dob["precision"] in ("full", "year_month", "year") else "unknown",
        "verification": {"status": ver["status"], "method": ver["method"], "source_id": ver["source_id"]},
    }
    for f in ("country", "city"):
        fields[f] = {
            "evidence_id": evidence_id(rid, sid, f, rec[f]["raw"]),
            "raw_value": rec[f]["raw"], "normalised_value": d[f"{f}_norm"],
            "status": "known" if rec[f]["raw"] else "unknown",
        }
    return {
        "record_id": rid, "tag": rec["tag"], "synthetic": True,
        "source": {"source_id": sid, "source_name": rec["source"]["source_name"],
                   "source_type": rec["source"]["source_type"]},
        "fields": fields,
    }


def _pair_packet(pair: dict, rec_ev: dict, alias: dict, in_splink_chain: bool, params: dict) -> dict:
    lid, rid = pair["left"], pair["right"]
    lf, rf = rec_ev[lid]["fields"], rec_ev[rid]["fields"]
    contributions = []
    for c in pair["splink"]["contributions"]:
        f = c["field"]
        contributions.append({
            "pair_evidence_id": _stable_id("PE-", pair["pair_id"], f, c["level_key"], lf[f]["evidence_id"], rf[f]["evidence_id"]),
            "field": f,
            "left": {"evidence_id": lf[f]["evidence_id"], "raw_value": lf[f]["raw_value"]},
            "right": {"evidence_id": rf[f]["evidence_id"], "raw_value": rf[f]["raw_value"]},
            "comparison_level": c["level_key"], "level_description": c["level_description"],
            "m_probability": c["m_probability"], "u_probability": c["u_probability"],
            "bayes_factor": c["bayes_factor"], "match_weight": c["match_weight"],
            "effect": ("neutral (unknown field: not imputed, not a mismatch)" if c["level_key"] == "null"
                       else "supports match" if c["match_weight"] > 0 else "counts against match"),
        })
    g = pair["guarded"]
    chk = g["dob_check"]
    alias_ev = None
    la, ra = rec_ev[lid]["fields"]["name"]["alias_group"], rec_ev[rid]["fields"]["name"]["alias_group"]
    if la and la == ra:
        entry = alias["groups"][la]
        alias_ev = {"alias_group": la, "source_id": entry["source_id"], "source_name": entry["source_name"],
                    "description": entry["description"], "forms": entry["forms"],
                    "used_by_comparison": pair["splink"]["contributions"][0]["level_key"] == "alias",
                    "evidence_ids": [lf["name"]["evidence_id"], rf["name"]["evidence_id"]]}
    return {
        "pair_id": pair["pair_id"],
        "left_record_id": lid, "right_record_id": rid,
        "pair_name": f"{pair['left_tag']}-{pair['right_tag']}",
        "edge_type": ("splink_link_edge" if pair["splink"]["decision"] == "LINK"
                      else "direct_comparison_not_linked_by_splink"),
        "candidate_generation": {"blocking_rules": pair["blocking_rules"], "alias_derived_candidate": bool(alias_ev and "same_alias_group" in pair["blocking_rules"] and "same_family_name" not in pair["blocking_rules"])},
        "alias_evidence": alias_ev,
        "scores": {
            "name_only": {**pair["name_only"], "evidence_ids": [lf["name"]["evidence_id"], rf["name"]["evidence_id"]]},
            "splink": {
                "match_weight": pair["splink"]["match_weight"], "match_probability": pair["splink"]["match_probability"],
                "prior_probability": pair["splink"]["prior_probability"], "prior_match_weight": pair["splink"]["prior_match_weight"],
                "decision": pair["splink"]["decision"],
                "thresholds": {"link_probability": params["splink"]["link_threshold_probability"],
                               "review_probability": params["splink"]["review_threshold_probability"]},
                "field_contributions": contributions,
            },
        },
        "guard": {
            "outcome": g["outcome"], "decision_after_guard": g["decision"],
            "changed_by_guard": g["changed_by_guard"], "reasons": g["reasons"],
            "dob_check": {
                "status": chk["status"], "reasons": chk["reasons"],
                "left": {**chk["left"], "evidence_id": lf["dob"]["evidence_id"]},
                "right": {**chk["right"], "evidence_id": rf["dob"]["evidence_id"]},
            },
            "linked_component": g["component"],
        },
        "decisions": {"name_only": pair["name_only"]["decision"], "splink": pair["splink"]["decision"],
                      "splink_with_guard": g["decision"]},
    }


def build_packet(result: dict, case_id: str) -> dict:
    case = result["cases"][case_id]
    params = result["config"]["parameters"]
    rec_ev = {rid: record_evidence(result["records_by_id"][rid]) for rid in case["records"]}
    pairs = [result["pairs_by_id"][pid] for pid in case["pairs"]]
    pair_packets = [_pair_packet(p, rec_ev, result["alias"], False, params) for p in pairs]
    versions = {}
    for pkg in ("splink", "duckdb", "rapidfuzz", "streamlit"):
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = None
    packet = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "wrong-john-smith-defender/evidence-packet",
        "synthetic": True,
        "synthetic_notice": "All records are fictional synthetic data for a demo. An analyst makes the final screening decision.",
        "case_id": case_id,
        "case_outcome": {
            "name_only": case["routes"]["name_only"], "splink": case["routes"]["splink"],
            "splink_with_guard": case["routes"]["splink_guard"],
            "route_meaning": {
                "ANALYST_REVIEW": "at least one pair needs an analyst",
                "CANDIDATE_VISIBLE": "at least one pair is a visible candidate link; none need review",
                "NO_CANDIDATE": "no pair was surfaced",
            },
        },
        "records": [rec_ev[rid] for rid in case["records"]],
        "candidate_pairs": pair_packets,
        "chain_analysis": {
            "method": "connected components over Splink LINK edges; every candidate pair inside a component is checked for a verified full-DOB contradiction",
            "components": case["components"],
        },
        "model": {
            "config_sha256": result["config"]["config_sha256"], "frozen_at": result["config"]["frozen_at"],
            "inputs_sha256": result["config"]["inputs_sha256"],
            "parameters": params,
            "how_to_recompute": "match_weight = log2(prior/(1-prior)) + sum(log2(m/u) of the chosen level per field); null levels contribute 0; match_probability = 2^w/(1+2^w)",
            "versions": versions,
        },
        "guard_rule": params["guard"]["rule"],
    }
    return _round(packet)


def packet_json(packet: dict) -> str:
    return json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def export_all(result: dict, out_dir: Path = EXPORTS_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for case_id in sorted(result["cases"]):
        p = out_dir / f"evidence_packet_{case_id}.json"
        p.write_text(packet_json(build_packet(result, case_id)), encoding="utf-8")
        paths.append(p)
    return paths
