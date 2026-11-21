#!/usr/bin/env bash
# Start Streamlit headless, probe /_stcore/health and the page, then stop it.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${CHECK_PORT:-8599}"
LOG="$(mktemp)"
streamlit run app.py --server.port "$PORT" --server.address 127.0.0.1 --server.headless true >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true; wait $PID 2>/dev/null || true' EXIT
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/_stcore/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
echo "health: $(curl -fsS -w ' (HTTP %{http_code})' "http://127.0.0.1:$PORT/_stcore/health")"
curl -fsS -o /tmp/wjsd_page.html -w "page: HTTP %{http_code}, %{size_download} bytes\n" "http://127.0.0.1:$PORT/"
grep -qi "<title>Streamlit</title>\|<noscript>" /tmp/wjsd_page.html && echo "page contains Streamlit shell: yes"
if grep -qiE 'https?://[^"'"'"' ]*' /tmp/wjsd_page.html; then
  echo "external URLs referenced in page HTML:"; grep -oiE 'https?://[^"'"'"' <)]+' /tmp/wjsd_page.html | sort -u | head
else echo "external URLs referenced in page HTML: none"; fi
echo "server log tail:"; tail -n 5 "$LOG"
