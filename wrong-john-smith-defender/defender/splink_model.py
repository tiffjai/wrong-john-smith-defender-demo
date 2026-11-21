"""Splink 4 / DuckDB scoring with FIXED, documented m/u probabilities (no EM training).

Why no training: the demo has a handful of synthetic records. EM on 3-5 pairs is unstable
and would be fitting noise, so every m/u value is set in the frozen config and Splink is used
as the scoring engine (blocking, comparison levels, Bayes factors, match weights).
"""
from __future__ import annotations

import logging
import math

import pandas as pd
import splink
from splink import DuckDBAPI, Linker, SettingsCreator
from splink import comparison_library as cl

logging.getLogger("splink").setLevel(logging.ERROR)

JW_LEVELS = {"jw_092": 0.92, "jw_080": 0.80}


def _lvl(cfg_level: dict, sql: str) -> dict:
    return {"sql_condition": sql, "label_for_charts": cfg_level["description"],
            "m_probability": cfg_level["m"], "u_probability": cfg_level["u"]}


def _null(description: str, sql: str) -> dict:
    return {"sql_condition": sql, "label_for_charts": description, "is_null_level": True}


def _levels_by_key(cfg_comp: dict) -> dict:
    return {lv["key"]: lv for lv in cfg_comp["levels"]}


def comparison_specs(cfg: dict) -> dict:
    """Ordered level specs per comparison: list of (key, sql_condition). First non-null match wins."""
    c = cfg["comparisons"]
    return {
        "name": {
            "null": "name_norm_l IS NULL OR name_norm_r IS NULL",
            "levels": [
                ("exact", "name_norm_l = name_norm_r"),
                ("alias", "alias_group_l IS NOT NULL AND alias_group_l = alias_group_r"),
                ("jw_092", "jaro_winkler_similarity(name_norm_l, name_norm_r) >= 0.92"),
                ("jw_080", "jaro_winkler_similarity(name_norm_l, name_norm_r) >= 0.80"),
                ("else", "ELSE"),
            ],
        },
        "dob": {
            "null": "dob_year_l IS NULL OR dob_year_r IS NULL",
            "levels": [
                ("full_exact", "dob_day_l IS NOT NULL AND dob_day_r IS NOT NULL AND dob_year_l = dob_year_r "
                               "AND dob_month_l = dob_month_r AND dob_day_l = dob_day_r"),
                ("year_month", "dob_month_l IS NOT NULL AND dob_month_r IS NOT NULL AND dob_year_l = dob_year_r "
                               "AND dob_month_l = dob_month_r AND (dob_day_l IS NULL OR dob_day_r IS NULL)"),
                ("year_only", "dob_year_l = dob_year_r AND (dob_month_l IS NULL OR dob_month_r IS NULL)"),
                ("mismatch", "ELSE"),
            ],
        },
        "country": {
            "null": "country_norm_l IS NULL OR country_norm_r IS NULL",
            "levels": [("same", "country_norm_l = country_norm_r"), ("else", "ELSE")],
        },
        "city": {
            "null": "city_norm_l IS NULL OR city_norm_r IS NULL",
            "levels": [("same", "city_norm_l = city_norm_r"), ("else", "ELSE")],
        },
    }


def build_settings(cfg: dict) -> SettingsCreator:
    specs = comparison_specs(cfg)
    comparisons = []
    for field, spec in specs.items():
        lv_cfg = _levels_by_key(cfg["comparisons"][field])
        levels = [_null(f"{field} unknown on at least one record", spec["null"])]
        for key, sql in spec["levels"]:
            levels.append(_lvl(lv_cfg[key], sql))
        comparisons.append(cl.CustomComparison(
            comparison_levels=levels, output_column_name=field,
            comparison_description=f"{field} comparison (fixed m/u from frozen config)"))
    return SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        probability_two_random_records_match=cfg["probability_two_random_records_match"],
        comparisons=comparisons,
        blocking_rules_to_generate_predictions=[b["sql"] for b in cfg["blocking_rules"]],
        retain_matching_columns=True,
        retain_intermediate_calculation_columns=True,
        additional_columns_to_retain=["case_id"],
    )


def _none_if_nan(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA else v


def records_frame(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        d = r["derived"]
        rows.append({
            "unique_id": r["record_id"], "case_id": r["case_id"], "family_key": d["family_key"],
            "name_norm": d["name_norm"], "alias_group": d["alias_group"],
            "dob_year": d["dob"]["year"], "dob_month": d["dob"]["month"], "dob_day": d["dob"]["day"],
            "country_norm": d["country_norm"], "city_norm": d["city_norm"],
        })
    df = pd.DataFrame(rows)
    for c in ("dob_year", "dob_month", "dob_day"):
        df[c] = df[c].astype("Int64")
    return df


def score_pairs(records: list[dict], cfg: dict) -> dict:
    """Return {(left_id, right_id): {...scores and per-field contributions...}} for Splink's blocked pairs."""
    df = records_frame(records)
    linker = Linker(df, build_settings(cfg), db_api=DuckDBAPI())
    pred = linker.inference.predict().as_pandas_dataframe()
    specs = comparison_specs(cfg)
    prior = cfg["probability_two_random_records_match"]
    prior_weight = math.log2(prior / (1 - prior))
    out = {}
    for _, row in pred.sort_values(["unique_id_l", "unique_id_r"]).iterrows():
        contributions = []
        for field, spec in specs.items():
            lv_cfg = _levels_by_key(cfg["comparisons"][field])
            gamma = int(row[f"gamma_{field}"])
            keys = [k for k, _ in spec["levels"]]
            if gamma == -1:
                key, description, m, u = "null", f"{field} unknown on at least one record (neutral: not imputed, not a mismatch)", None, None
            else:
                key = keys[len(keys) - 1 - gamma]
                description, m, u = lv_cfg[key]["description"], lv_cfg[key]["m"], lv_cfg[key]["u"]
            bf = float(row[f"bf_{field}"])
            contributions.append({
                "field": field, "level_key": key, "level_description": description, "gamma": gamma,
                "m_probability": m, "u_probability": u,
                "bayes_factor": bf, "match_weight": math.log2(bf),
            })
        total_weight = float(row["match_weight"])
        out[(row["unique_id_l"], row["unique_id_r"])] = {
            "case_id": row["case_id_l"],
            "match_key": int(row["match_key"]),
            "prior_probability": prior, "prior_match_weight": prior_weight,
            "match_weight": total_weight,
            "match_probability": float(row["match_probability"]),
            "recomputed_probability": 1 / (1 + 2 ** (-(prior_weight + sum(c["match_weight"] for c in contributions)))),
            "contributions": contributions,
        }
    return {"pairs": out, "splink_version": splink.__version__}


def decide(probability: float, cfg: dict) -> str:
    if probability >= cfg["link_threshold_probability"]:
        return "LINK"
    if probability >= cfg["review_threshold_probability"]:
        return "REVIEW"
    return "NO_LINK"
