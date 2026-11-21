# Verification log (run on the build box, 2026-11-20 UTC, Python 3.13.5, Linux x86_64)

| # | Command | Result |
|---|---|---|
| 1 | `./run.sh test` → `python -m pytest -v` (from a freshly created `.venv`, installing the pinned requirements) | **45 passed** (`pytest_output.txt`) |
| 2 | `./run.sh check` → headless `streamlit run`, `curl /_stcore/health`, `curl /`, stop | health `ok` HTTP 200; page HTTP 200 (`server_check_output.txt`) |
| 3 | `./run.sh evaluate` (loads frozen config, verifies hash, then evaluates) | see `evaluation_output.txt`; `frozen_at` < `evaluated_at` |
| 4 | `./run.sh export` | wrote 3 packets to `exports/` (byte-identical to regeneration: test) |
| 5 | `python scripts/report_cases.py` | per-pair scores/decisions (`case_report_output.txt`) |
| 6 | Headless Chrome (CDP) screenshots of the live server for each case (`screenshot_CASE-0x.png`) | UI renders for all three cases |

What the pytest suite covers: date parsing/precision; guard (verified+full+different = contradiction; partial, unverified, unknown,
unparseable = not assessable); same candidate pairs for all three methods and generator == Splink blocking; Splink BF == m/u and
probability recomputation; CASE-01 and CASE-08 → `ANALYST_REVIEW` in the guarded column; CASE-03 stays `CANDIDATE_VISIBLE` (alias-only
candidate; absent when the alias table is disabled); frozen config tamper detection (parameters and inputs); evaluation uses frozen
thresholds and runs after `frozen_at`; measured counts; packet content, stable evidence IDs, no label keys/values, no label file opened
and no evaluation module imported by scoring/export; offline (sockets blocked while the app and pipeline run, no network imports/URLs in
source); Streamlit `AppTest` per case (case selector, three columns, review control saves, download button, labels hidden until toggled).

Notes: the page HTML references `http://www.apache.org/licenses/LICENSE-2.0` only inside Streamlit's licence comment (not a request).
`config/frozen_config.json` was first frozen 21:12:19 UTC, then re-frozen at 21:12:37 UTC after a cosmetic key rename
(`label`→`description`, `tag`) and **no value changes**; the evaluation ran afterwards (first at 21:13:18 UTC; final run in `evaluation_output.txt`).
