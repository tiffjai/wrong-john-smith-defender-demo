import json
import shutil

import pytest

from defender.config import ConfigIntegrityError, load_frozen
from defender.paths import ALIAS_PATH, FROZEN_CONFIG_PATH, RECORDS_PATH
from evaluation.evaluate import evaluate


def test_frozen_config_hash_verifies():
    cfg = load_frozen()
    assert len(cfg["config_sha256"]) == 64 and cfg["frozen_at"]


def test_editing_a_threshold_after_freeze_is_detected(tmp_path):
    tampered = tmp_path / "frozen.json"
    data = json.loads(FROZEN_CONFIG_PATH.read_text())
    data["parameters"]["splink"]["link_threshold_probability"] = 0.5
    tampered.write_text(json.dumps(data))
    with pytest.raises(ConfigIntegrityError):
        load_frozen(tampered)


def test_changed_inputs_after_freeze_are_detected(tmp_path):
    rec = tmp_path / "records.json"
    rec.write_text(RECORDS_PATH.read_text().replace("Testford", "Testfordd"))
    with pytest.raises(ConfigIntegrityError):
        load_frozen(FROZEN_CONFIG_PATH, records_path=rec, alias_path=ALIAS_PATH)


def test_evaluation_uses_frozen_thresholds_and_orders_after_freeze(result):
    ev = evaluate(result)
    assert ev["config_sha256"] == result["config"]["config_sha256"]
    assert ev["frozen_at"] <= ev["evaluated_at"]
    assert ev["thresholds"]["splink"]["link_threshold_probability"] == 0.80
    assert ev["thresholds"]["name_only"]["link_threshold"] == 90.0


def test_measured_counts(result):
    ev = evaluate(result)
    d = ev["denominators"]
    assert (d["candidate_pairs"], d["labelled_true_matches"], d["labelled_non_matches"]) == (5, 2, 3)
    m = ev["metrics"]
    assert m["candidate_recall"]["text"] == "2/2"
    got = {k: (v["false_positives"]["text"], v["missed_true_matches"]["text"], v["manual_review"]["text"])
           for k, v in m["by_method"].items()}
    assert got == {"name_only": ("3/3", "1/2", "0/5"), "splink": ("2/3", "0/2", "0/5"),
                   "splink_guard": ("0/3", "0/2", "4/5")}
    assert m["ablation_no_alias_table"]["candidate_recall"]["text"] == "1/2"
    assert m["ablation_no_alias_table"]["candidate_pairs_total"] == 4
