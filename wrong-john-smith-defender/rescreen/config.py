"""Frozen rescreen policy + the reused milestone-1 frozen scoring config."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from defender.config import ConfigIntegrityError, canonical_json, load_frozen, sha256_text

from .paths import DRAFT_POLICY, FROZEN_POLICY


def freeze_policy(draft: Path = DRAFT_POLICY, out: Path = FROZEN_POLICY) -> dict:
    params = {k: v for k, v in json.loads(Path(draft).read_text(encoding="utf-8")).items() if not k.startswith("_")}
    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "policy": params,
              "policy_sha256": sha256_text(canonical_json(params))}
    Path(out).write_text(json.dumps(frozen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return frozen


def load_policy(path: Path = FROZEN_POLICY) -> dict:
    frozen = json.loads(Path(path).read_text(encoding="utf-8"))
    if sha256_text(canonical_json(frozen["policy"])) != frozen["policy_sha256"]:
        raise ConfigIntegrityError("rescreen policy edited after freezing")
    return frozen


def load_scoring() -> dict:
    """Milestone-1 frozen scoring config, verified, and pinned by the rescreen policy."""
    scoring = load_frozen()
    pol = load_policy()
    if scoring["config_sha256"] != pol["policy"]["scoring_config_sha256"]:
        raise ConfigIntegrityError("scoring config hash differs from the one pinned in the rescreen policy")
    return scoring
