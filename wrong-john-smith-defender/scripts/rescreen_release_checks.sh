#!/usr/bin/env bash
# Runs every milestone-2 release check and captures output in verification_rescreen/. Exit non-zero on any failure.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=verification_rescreen; mkdir -p "$OUT"; FAIL=0
step() { echo "== $1"; }
step "1 full pytest (milestone 1 + rescreen)"
python -m pytest -v > "$OUT/pytest_output.txt" 2>&1 || FAIL=1; tail -n 1 "$OUT/pytest_output.txt"
step "2 end-to-end acceptance"
python -m rescreen acceptance > "$OUT/acceptance_output.txt" 2>&1 || FAIL=1; tail -n 1 "$OUT/acceptance_output.txt"
step "3 QA threshold replay"
python -m rescreen_qa > "$OUT/qa_replay_output.txt" 2>&1 || FAIL=1; grep -E "LOST|policy" "$OUT/qa_replay_output.txt"
step "4 schema validation of exports"
python - > "$OUT/schema_validation_output.txt" 2>&1 <<'PY' || FAIL=1
import glob, json, jsonschema
m = {"case_view_*.json": "case_view", "evidence_packet_*.json": "evidence_packet", "challenger_handoff_*.json": "challenger_handoff",
     "reviews.json": "reviews", "jurisdictions_*.json": "jurisdictions", "feeds_status.json": "feeds_status", "qa_replay.json": "qa_replay"}
n = 0
for pat, name in m.items():
    s = json.load(open(f"rescreen/schema/{name}.schema.json"))
    for f in sorted(glob.glob("exports/rescreen/" + pat)):
        jsonschema.Draft202012Validator(s).validate(json.load(open(f))); print("valid", name, f); n += 1
print("validated", n, "files")
PY
tail -n 1 "$OUT/schema_validation_output.txt"
step "5 API start + health + case + stop"
rm -f rescreen_state/release_api.sqlite
python -m rescreen reset --db rescreen_state/release_api.sqlite > /dev/null 2>&1
python -m rescreen serve --db rescreen_state/release_api.sqlite --port 8766 > "$OUT/api_server.log" 2>&1 & API=$!
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:8766/api/health > /dev/null 2>&1 && break; sleep 0.5; done
{ echo "GET /api/health:"; curl -fsS -w "\nHTTP %{http_code}\n" http://127.0.0.1:8766/api/health | python -c "import sys,json; t=sys.stdin.read(); b,code=t.rsplit('\n',2)[0],t.strip().splitlines()[-1]; d=json.loads(b); print(d['status'], d['contract_version'], 'grok_live=',d['grok_live']); print(code)";
  echo "GET /api/cases:"; curl -fsS http://127.0.0.1:8766/api/cases | python -c "import sys,json; print([(c['case_id'],c['state']) for c in json.load(sys.stdin)['cases']])";
  echo "POST /api/feeds/load V2:"; curl -fsS -X POST -H 'Content-Type: application/json' -d '{"jurisdiction":"UK","version":"V2"}' http://127.0.0.1:8766/api/feeds/load | python -c "import sys,json; d=json.load(sys.stdin); print(d['result'], d['snapshot_id'])"; } > "$OUT/api_check_output.txt" 2>&1 || FAIL=1
kill $API; wait $API 2>/dev/null; cat "$OUT/api_check_output.txt"
step "6 Streamlit check UI start + health + stop"
rm -f rescreen_state/ui.sqlite
streamlit run rescreen_app.py --server.port 8597 --server.address 127.0.0.1 --server.headless true > "$OUT/ui_server.log" 2>&1 & UI=$!
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8597/_stcore/health > /dev/null 2>&1 && break; sleep 1; done
{ echo "health: $(curl -fsS http://127.0.0.1:8597/_stcore/health)"; curl -fsS -o /dev/null -w "page: HTTP %{http_code}\n" http://127.0.0.1:8597/; } > "$OUT/ui_check_output.txt" 2>&1 || FAIL=1
kill $UI; wait $UI 2>/dev/null; cat "$OUT/ui_check_output.txt"
step "7 milestone-1 exports byte-identical to the hashes recorded before milestone 2 started"
{ python scripts/export_packets.py && sha256sum -c verification_rescreen/milestone1_expected_sha256.txt; } > "$OUT/milestone1_exports_check.txt" 2>&1 || FAIL=1
cat "$OUT/milestone1_exports_check.txt"
echo "RELEASE CHECKS: $([ $FAIL = 0 ] && echo PASS || echo FAIL)" | tee "$OUT/RESULT.txt"
exit $FAIL
