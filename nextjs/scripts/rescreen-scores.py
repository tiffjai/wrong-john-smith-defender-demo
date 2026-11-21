# /// script
# requires-python = ">=3.11"
# dependencies = ["splink==4.0.17", "duckdb==2.0.1", "rapidfuzz==3.14.6", "pandas==3.1.1"]
# ///
"""Export real RapidFuzz and Splink scores for the offline review exercise."""
import json
from pathlib import Path

import pandas as pd
from rapidfuzz.fuzz import token_sort_ratio

from benchmark import predict


ROOT = Path(__file__).resolve().parents[1] / "data"
FIXTURE = json.loads((ROOT / "rescreen-fixtures.json").read_text())


def romanised(record):
    return record["name"].split(" / ")[-1].replace("-", " ").lower()


def frame_row(row_id, record, name):
    return {"row_id": row_id, "name": name, "surname": name.split()[0],
            "initial": name.split()[1][0], "postcode": None, "dob": record["dob"]}


def score_version(version):
    watchlist = FIXTURE["versions"][version]
    primary = romanised(watchlist)
    alias = watchlist["alias"]
    # For this fixture, the sourced V2 list alias is the chosen Splink name.
    # RapidFuzz always uses the two primary names for its name-only baseline.
    list_name = alias["value"].lower() if alias else primary
    customers = FIXTURE["customers"]
    left = [frame_row(key, record, romanised(record)) for key, record in customers.items()]
    right = [frame_row(FIXTURE["watchlistEntryId"], watchlist, list_name)]
    prediction = predict(pd.DataFrame(left), pd.DataFrame(right))
    found = {row.row_id_l: row for row in prediction.itertuples()}
    return {key: {
        "retrieved": key in found,
        "rapidfuzz": round(token_sort_ratio(romanised(record), primary), 4),
        "splink": round(float(found[key].match_probability), 9) if key in found else None,
    } for key, record in customers.items()}


if __name__ == "__main__":
    scores = {version: score_version(version) for version in ("V1", "V2")}
    (ROOT / "rescreen-scores.json").write_text(json.dumps(scores, indent=2) + "\n")
    print(json.dumps(scores, indent=2))
