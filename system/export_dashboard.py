#!/usr/bin/env python3
"""Generate predictions and a local-only dashboard evidence snapshot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from bank_resolver import BankResolver


def export(folder, output):
    start = time.monotonic()
    folder = folder.resolve(strict=True)
    for file in folder.iterdir():
        if file.is_symlink() and not file.resolve().is_relative_to(folder):
            raise ValueError('Data files must remain within the supplied folder')
    engine = BankResolver(folder)
    rows = engine.run()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'dev.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows))
    snapshot = {'generatedAt':datetime.now(timezone.utc).isoformat(), 'source':'Development set · local participant data', 'synthetic':False, 'predictions':rows,
                'traces':engine.trace, 'durationSeconds':round(time.monotonic()-start, 2),
                'policySha256':hashlib.sha256((folder/'POLICY.md').read_bytes()).hexdigest()}
    (output / 'screening-dashboard.local.json').write_text(json.dumps(snapshot, ensure_ascii=False))
    print(f'{len(rows)} predictions; {snapshot["durationSeconds"]} seconds; no API calls')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Usage: python3 system/export_dashboard.py <data folder> <output directory>')
    export(Path(sys.argv[1]), Path(sys.argv[2]))
