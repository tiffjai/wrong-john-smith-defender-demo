"""python -m rescreen_qa [--out DIR] [--db PATH]  -> runs P1 and P2 replays, prints findings, writes qa_replay.json."""
import argparse
import json
import sys
from pathlib import Path

from rescreen.paths import EXPORT_DIR

from .replay import PROPOSALS, record, replay

ap = argparse.ArgumentParser(prog="python -m rescreen_qa")
ap.add_argument("--out", default=str(EXPORT_DIR))
ap.add_argument("--db", default=None, help="optional rescreen DB to record the reviewer action in")
args = ap.parse_args()
results = [replay(k) for k in PROPOSALS]
for r in results:
    print(f"{r['proposal']}: {r['description']}")
    print(f"  versions {r['baseline_version']} -> {r['proposal_version']}; changed {[(c['parameter'], c['baseline'], c['proposed']) for c in r['changed_parameters']]}")
    for m in ("candidate_recall", "missed_true_matches", "false_positives", "review_volume"):
        print(f"  {m:20s} baseline {r['baseline_metrics'][m]['text']:>5s}  proposal {r['proposal_metrics'][m]['text']:>5s}")
    for x in r["lost_true_links"]:
        print(f"  LOST {x['pair']} ({x['dataset']}, critical={x['critical']}): stage={x['stage'].upper()} - {x['detail']}")
    print(f"  policy -> {r['policy_outcome']}; reviewer {r['reviewer_action']['reviewer']}: {r['reviewer_action']['action']}")
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / "qa_replay.json").write_text(json.dumps({"contract_version": "rescreen-contract/1.0", "replays": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if args.db:
    from rescreen.db import connect, now
    c = connect(args.db)
    for r in results:
        record(c, r, now(c))
print(f"wrote {out / 'qa_replay.json'}")
sys.exit(0)
