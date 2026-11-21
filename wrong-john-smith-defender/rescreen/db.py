"""Local SQLite store for snapshots, customers, jobs, alerts, events and decisions.

Timestamps come from a simulated clock by default (deterministic, reproducible exports);
set RESCREEN_REAL_CLOCK=1 to use wall-clock UTC.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS actors (actor_id TEXT PRIMARY KEY, display_name TEXT, role TEXT, entity TEXT);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY, source_id TEXT, jurisdiction TEXT, version TEXT, fingerprint TEXT,
  published_at TEXT, received_at TEXT, status TEXT, entries_received INT, entries_loaded INT,
  entries_rejected INT, validation TEXT, diff TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS feed_checks (
  check_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, attempted TEXT, result TEXT,
  snapshot_id TEXT, detail TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS active_snapshots (
  source_id TEXT PRIMARY KEY, jurisdiction TEXT, snapshot_id TEXT, activated_at TEXT,
  last_check_at TEXT, last_check_result TEXT, last_success_at TEXT, coverage TEXT, rescreen_completed_at TEXT);
CREATE TABLE IF NOT EXISTS kyc_snapshots (kyc_snapshot_id TEXT PRIMARY KEY, imported_at TEXT, counts TEXT);
CREATE TABLE IF NOT EXISTS customers (customer_id TEXT PRIMARY KEY, version INT, kyc_snapshot_id TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS customer_versions (customer_id TEXT, version INT, data TEXT, change TEXT, actor TEXT, at TEXT,
  PRIMARY KEY (customer_id, version));
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY, trigger TEXT, scope TEXT, snapshot_ids TEXT, config_sha256 TEXT, policy_sha256 TEXT,
  status TEXT, started_at TEXT, finished_at TEXT, error TEXT, retry_of TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS screening_results (
  alert_id TEXT, snapshot_id TEXT, kyc_version INT, job_id TEXT, result TEXT, at TEXT,
  PRIMARY KEY (alert_id, snapshot_id, kyc_version));
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY, case_id TEXT UNIQUE, customer_id TEXT, source_id TEXT, entry_id TEXT,
  state TEXT, owner TEXT, priority TEXT, reason TEXT, created_at TEXT, updated_at TEXT, reopen_count INT DEFAULT 0,
  latest_snapshot_id TEXT, latest_kyc_version INT, UNIQUE (customer_id, source_id, entry_id));
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, seq INTEGER, alert_id TEXT, case_id TEXT, type TEXT, payload TEXT, job_id TEXT, actor TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY, case_id TEXT, analyst TEXT, rationale TEXT, evidence_ids TEXT, basis TEXT,
  snapshot_ids TEXT, status TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY, case_id TEXT, proposal_id TEXT, actor TEXT, role TEXT, decision TEXT, comment TEXT,
  evidence_ids TEXT, basis TEXT, snapshot_ids TEXT, at TEXT, validity TEXT, invalidated_by TEXT);
CREATE TABLE IF NOT EXISTS ai_suggestions (
  suggestion_id TEXT PRIMARY KEY, case_id TEXT, origin TEXT, is_replay INT, payload TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS ai_responses (
  response_id TEXT PRIMARY KEY, case_id TEXT, suggestion_id TEXT, actor TEXT, action TEXT, text TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS case_actions (
  action_id TEXT PRIMARY KEY, case_id TEXT, actor TEXT, role TEXT, action TEXT, from_state TEXT, to_state TEXT,
  comment TEXT, payload TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS qa_runs (
  qa_run_id TEXT PRIMARY KEY, proposal_version TEXT, baseline_version TEXT, result TEXT, reviewer TEXT,
  reviewer_action TEXT, at TEXT);
"""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)  # autocommit; API serialises access with a lock
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(value)))


def now(conn) -> str:
    """Simulated clock: start + 1 minute per call (persisted). Real UTC if RESCREEN_REAL_CLOCK=1."""
    if os.environ.get("RESCREEN_REAL_CLOCK") == "1":
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    start = get_meta(conn, "clock_start", "2026-11-21T09:00:00Z")
    tick = get_meta(conn, "clock_tick", 0) + 1
    set_meta(conn, "clock_tick", tick)
    t = datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(minutes=tick)
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_id(prefix: str, *parts) -> str:
    payload = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def add_event(conn, idem_parts: tuple, type_: str, payload: dict, alert_id=None, case_id=None,
              job_id=None, actor=None) -> bool:
    """Idempotent event insert: the event_id is a hash of the idempotency key. Returns True if new."""
    event_id = stable_id("EVT-", type_, *idem_parts)
    if conn.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone():
        return False
    seq = (conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]) + 1
    conn.execute("INSERT INTO events(event_id,seq,alert_id,case_id,type,payload,job_id,actor,at) VALUES(?,?,?,?,?,?,?,?,?)",
                 (event_id, seq, alert_id, case_id, type_, json.dumps(payload, ensure_ascii=False), job_id, actor, now(conn)))
    return True


def j(v):
    return json.loads(v) if v is not None else None
