#!/usr/bin/env bash
# Milestone 2 (rescreening) launcher. Reuses the milestone-1 venv/requirements (no new dependencies).
#   ./run_rescreen.sh acceptance   end-to-end acceptance run (fresh DB) -> exports/rescreen/*.json, exit 0 if all checks pass
#   ./run_rescreen.sh qa           QA threshold replay -> exports/rescreen/qa_replay.json
#   ./run_rescreen.sh api          local JSON API for the Next.js dashboard on http://127.0.0.1:8765 (DB rescreen_state/api.sqlite)
#   ./run_rescreen.sh ui           Streamlit check view on http://127.0.0.1:8502
#   ./run_rescreen.sh test         full pytest (milestone 1 + rescreen)
#   ./run_rescreen.sh release      every release check, outputs captured in verification_rescreen/
#   ./run_rescreen.sh cli ARGS...  python -m rescreen ARGS...
#   ./run_rescreen.sh sweep        daily sweep entry point (for cron) against rescreen_state/api.sqlite
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
STAMP=".venv/.requirements.sha256"
WANT="$(sha256sum requirements.txt requirements-dev.txt | sha256sum | cut -d' ' -f1)"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$WANT" ]; then
  pip install --quiet --disable-pip-version-check -r requirements-dev.txt
  echo "$WANT" > "$STAMP"
fi
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
API_DB="${RESCREEN_DB:-rescreen_state/api.sqlite}"
case "${1:-acceptance}" in
  acceptance) exec python -m rescreen acceptance ;;
  qa)         exec python -m rescreen_qa ;;
  api)        [ -f "$API_DB" ] || python -m rescreen reset --db "$API_DB" >/dev/null; exec python -m rescreen serve --db "$API_DB" --port "${PORT:-8765}" ;;
  ui)         exec streamlit run rescreen_app.py --server.port "${PORT:-8502}" --server.address 127.0.0.1 --server.headless true ;;
  test)       exec python -m pytest -v ;;
  release)    exec bash scripts/rescreen_release_checks.sh ;;
  sweep)      exec python -m rescreen sweep --db "$API_DB" ;;
  cli)        shift; exec python -m rescreen "$@" ;;
  *) echo "usage: ./run_rescreen.sh [acceptance|qa|api|ui|test|release|sweep|cli ...]"; exit 2 ;;
esac
