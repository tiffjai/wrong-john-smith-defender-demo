#!/usr/bin/env python
"""Regenerate exports/evidence_packet_<CASE>.json for every case (no labels involved)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defender.evidence import export_all  # noqa: E402
from defender.pipeline import run_pipeline  # noqa: E402

for p in export_all(run_pipeline()):
    print("wrote", p.relative_to(Path(__file__).resolve().parent.parent))
