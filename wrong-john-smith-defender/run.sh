#!/usr/bin/env bash
# One-command launcher:  ./run.sh            -> create .venv, install pinned deps, start the dashboard
#                        ./run.sh test       -> run the pytest suite
#                        ./run.sh evaluate   -> run the evaluation (reads frozen config)
#                        ./run.sh export     -> regenerate exports/*.json evidence packets
#                        ./run.sh check      -> headless start + health/page check, then stop
# Network is needed ONLY for the one-off `pip install`; the app itself makes no network calls.
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
case "${1:-run}" in
  test)     exec python -m pytest -v ;;
  evaluate) exec python -m evaluation.evaluate ;;
  export)   exec python scripts/export_packets.py ;;
  check)    exec bash scripts/check_server.sh ;;
  run)      exec streamlit run app.py --server.port "${PORT:-8501}" --server.address 127.0.0.1 --server.headless true ;;
  *) echo "usage: ./run.sh [run|test|evaluate|export|check]"; exit 2 ;;
esac
