"""Frozen scoring configuration: create, load and verify."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import ALIAS_PATH, DRAFT_CONFIG_PATH, FROZEN_CONFIG_PATH, RECORDS_PATH


class ConfigIntegrityError(RuntimeError):
    pass


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file_json(path: Path) -> str:
    """Hash of a JSON file's canonical content (whitespace-insensitive)."""
    return sha256_text(canonical_json(json.loads(Path(path).read_text(encoding="utf-8"))))


def _strip_comments(params: dict) -> dict:
    return {k: v for k, v in params.items() if not k.startswith("_")}


def compute_config_sha256(parameters: dict, inputs_sha256: dict) -> str:
    return sha256_text(canonical_json({"parameters": parameters, "inputs_sha256": inputs_sha256}))


def freeze(draft_path: Path = DRAFT_CONFIG_PATH, out_path: Path = FROZEN_CONFIG_PATH,
           records_path: Path = RECORDS_PATH, alias_path: Path = ALIAS_PATH) -> dict:
    draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    parameters = _strip_comments(draft)
    inputs = {"records": sha256_file_json(records_path), "alias_table": sha256_file_json(alias_path)}
    frozen = {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Frozen before any evaluation run. Pipeline and evaluation refuse to run if config_sha256 does not match.",
        "parameters": parameters,
        "inputs_sha256": inputs,
        "config_sha256": compute_config_sha256(parameters, inputs),
    }
    Path(out_path).write_text(json.dumps(frozen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return frozen


def load_frozen(path: Path = FROZEN_CONFIG_PATH, records_path: Path = RECORDS_PATH,
                alias_path: Path = ALIAS_PATH, verify_inputs: bool = True) -> dict:
    frozen = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = compute_config_sha256(frozen["parameters"], frozen["inputs_sha256"])
    if expected != frozen["config_sha256"]:
        raise ConfigIntegrityError(
            "Frozen config hash mismatch: parameters were edited after freezing. "
            "Re-run scripts/freeze_config.py (this resets frozen_at).")
    if verify_inputs:
        actual = {"records": sha256_file_json(records_path), "alias_table": sha256_file_json(alias_path)}
        if actual != frozen["inputs_sha256"]:
            raise ConfigIntegrityError("Input data (records/alias table) changed since the config was frozen.")
    return frozen
