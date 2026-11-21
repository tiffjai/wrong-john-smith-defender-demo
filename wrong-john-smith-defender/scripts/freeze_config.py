#!/usr/bin/env python
"""Freeze config/draft_config.json -> config/frozen_config.json (hash + timestamp).

Refuses to overwrite an existing frozen config unless --force is given.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defender.config import freeze  # noqa: E402
from defender.paths import FROZEN_CONFIG_PATH  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true")
args = ap.parse_args()
if FROZEN_CONFIG_PATH.exists() and not args.force:
    sys.exit(f"{FROZEN_CONFIG_PATH} already exists; refusing to overwrite (use --force and accept a new frozen_at).")
f = freeze()
print("frozen_at     :", f["frozen_at"])
print("config_sha256 :", f["config_sha256"])
