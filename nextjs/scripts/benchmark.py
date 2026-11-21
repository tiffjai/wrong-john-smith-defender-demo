# /// script
# requires-python = ">=3.11"
# dependencies = ["splink==4.0.17", "duckdb==2.0.1", "rapidfuzz==3.14.6", "pandas==3.1.1"]
# ///
"""Run a fixed cross-table FEBRL4 benchmark without matching on upstream IDs."""

import csv
import hashlib
import io
import json
import logging
import re
import time
from datetime import date
from pathlib import Path
from urllib.request import urlopen

import duckdb
import pandas as pd
import rapidfuzz
import splink
from rapidfuzz.fuzz import token_sort_ratio
from splink import DuckDBAPI, Linker, SettingsCreator, comparison_library

REVISION = "b93d97641952f8c85106be5794ca93b1f1298fbc"
DATA_URL = f"https://raw.githubusercontent.com/J535D165/recordlinkage/{REVISION}/recordlinkage/datasets/febrl/"
BLOCKING = [
    "l.surname = r.surname",
    "l.dob = r.dob",
    "l.postcode = r.postcode AND l.initial = r.initial",
]
NAME_THRESHOLD = 90
SPLINK_THRESHOLD = 0.8
PRIOR = 0.0002
logging.getLogger("splink").setLevel(logging.ERROR)


def normalise(value):
    return " ".join(value.strip().casefold().split()) or None


def parse_dob(raw):
    if not re.fullmatch(r"\d{8}", raw):
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:])).isoformat()
    except ValueError:
        return None


def load(side):
    with urlopen(f"{DATA_URL}dataset4{side}.csv", timeout=30) as response:
        raw = response.read()
    rows, gold_keys = [], {}
    for item in csv.DictReader(io.StringIO(raw.decode("utf-8")), skipinitialspace=True):
        source_id = item["rec_id"].strip()
        key = re.fullmatch(r"rec-(\d+)-(?:org|dup-0)", source_id)
        if key is None:
            raise ValueError(f"Unexpected FEBRL4 ID in side {side}")
        row_id = f"{side}-{hashlib.sha256(f'{side}:{source_id}'.encode()).hexdigest()[:14]}"
        gold_keys[key[1]] = row_id
        given, surname = normalise(item["given_name"]), normalise(item["surname"])
        full_name = " ".join(filter(None, (given, surname))) or None
        rows.append({"row_id": row_id, "name": full_name, "surname": surname,
                     "initial": given[0] if given else None, "postcode": normalise(item["postcode"]),
                     "dob": parse_dob(item["date_of_birth"].strip())})
    if len(rows) != 5000 or len(gold_keys) != 5000:
        raise ValueError(f"Unexpected FEBRL4 record count in side {side}")
    return pd.DataFrame(rows), gold_keys, hashlib.sha256(raw).hexdigest()


def comparison(field, levels):
    return comparison_library.CustomComparison(
        output_column_name=field,
        comparison_levels=[
            {"sql_condition": f"{field}_l IS NULL OR {field}_r IS NULL", "is_null_level": True,
             "label_for_charts": "Unknown"},
            *({"sql_condition": sql, "label_for_charts": title, "m_probability": m, "u_probability": u}
              for title, sql, m, u in levels),
        ],
    )


def predict(left, right):
    name = comparison("name", [
        ("Exact", "name_l = name_r", .54, .0002),
        ("Close", "jaro_winkler_similarity(name_l, name_r) >= 0.93", .24, .0018),
        ("Similar", "jaro_winkler_similarity(name_l, name_r) >= 0.82", .16, .035),
        ("Different", "ELSE", .06, .963),
    ])
    dob = comparison("dob", [("Exact", "dob_l = dob_r", .78, .00004), ("Different", "ELSE", .22, .99996)])
    postcode = comparison("postcode", [("Exact", "postcode_l = postcode_r", .70, .002),
                                       ("Different", "ELSE", .30, .998)])
    settings = SettingsCreator(link_type="link_only", unique_id_column_name="row_id",
                               comparisons=[name, dob, postcode], retain_matching_columns=True,
                               probability_two_random_records_match=PRIOR,
                               blocking_rules_to_generate_predictions=BLOCKING)
    linker = Linker([left, right], settings, db_api=DuckDBAPI(), input_table_aliases=["a", "b"])
    return linker.inference.predict().as_pandas_dataframe()


def counts(pairs, truth, retrieved):
    correct = int((pairs & truth).sum())
    selected = int(pairs.sum())
    return {"trueLinks": correct, "falseLinks": selected - correct,
            "missedTrue": 5000 - correct, "selected": selected,
            "missesAfterRetrieval": retrieved - correct}


def main():
    left, gold_a, digest_a = load("a")
    right, gold_b, digest_b = load("b")
    started = time.perf_counter()
    matches = predict(left, right)
    matches["name_only"] = [token_sort_ratio(a or "", b or "") if a and b else 0
                            for a, b in zip(matches.name_l, matches.name_r)]
    elapsed = round(time.perf_counter() - started, 3)
    if gold_a.keys() != gold_b.keys():
        raise ValueError("The FEBRL4 reference pair keys do not agree")
    links = {(gold_a[key], gold_b[key]) for key in gold_a}
    matches["truth"] = [(a, b) in links for a, b in zip(matches.row_id_l, matches.row_id_r)]
    if matches.duplicated(["row_id_l", "row_id_r"]).any():
        raise ValueError("Candidate pairs are not unique")
    retrieved = int(matches.truth.sum())
    name_links = matches.name_only >= NAME_THRESHOLD
    splink_links = matches.match_probability >= SPLINK_THRESHOLD

    examples = []
    for bucket, subset in [
        ("Recovered by Splink", matches[matches.truth & ~name_links & splink_links]),
        ("False link", matches[~matches.truth & splink_links]),
        ("Miss after retrieval", matches[matches.truth & ~splink_links]),
        ("Both link", matches[matches.truth & name_links & splink_links]),
    ]:
        for row in subset.sort_values(["match_probability", "row_id_l", "row_id_r"], ascending=[False, True, True]).head(6).itertuples():
            examples.append({"id": f"{row.row_id_l}/{row.row_id_r}", "left": row.name_l, "right": row.name_r,
                             "nameScore": round(row.name_only, 2), "splinkProbability": round(row.match_probability, 6),
                             "truePair": bool(row.truth), "category": bucket})
    result = {
        "dataset": "FEBRL4", "revision": REVISION, "sourceHashes": [digest_a, digest_b],
        "leftRecords": len(left), "rightRecords": len(right), "labelledTrue": len(links),
        "possiblePairs": len(left) * len(right), "candidatePairs": len(matches), "retrievedTrue": retrieved,
        "retrievalMisses": len(links) - retrieved, "seconds": elapsed,
        "versions": {"splink": splink.__version__, "duckdb": duckdb.__version__, "rapidfuzz": rapidfuzz.__version__},
        "configuration": {"prior": PRIOR, "nameThreshold": NAME_THRESHOLD, "splinkThreshold": SPLINK_THRESHOLD,
                          "blocking": ["Exact surname", "Exact full date of birth", "Exact postcode and given-name initial"]},
        "methods": {"nameOnly": counts(name_links, matches.truth, retrieved),
                    "splink": counts(splink_links, matches.truth, retrieved)},
        "examples": examples,
    }
    path = Path(__file__).resolve().parents[1] / "data" / "benchmark.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "examples"}, indent=2))


if __name__ == "__main__":
    main()
