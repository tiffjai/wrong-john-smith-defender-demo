#!/usr/bin/env python
"""Print per-pair scores/decisions and per-case routes for the three scenarios (scoring only; no labels)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from defender.pipeline import run_pipeline  # noqa: E402

r = run_pipeline()
print(f"{'pair':20s} {'name-only':>18s} {'splink P (decision)':>24s} {'guard decision':>15s}  guard outcome / DOB check")
for c in r["cases"].values():
    print(f"-- {c['case_id']}: routes {c['routes']}")
    for pid in c["pairs"]:
        p = r["pairs_by_id"][pid]
        print(f"{pid:20s} {p['name_only']['score']!s:>9} {p['name_only']['decision']:>8} "
              f"{p['splink']['match_probability']:>14.4f} {p['splink']['decision']:>8} {p['guarded']['decision']:>15s}  "
              f"{p['guarded']['outcome']} / {p['guarded']['dob_check']['status']}")
