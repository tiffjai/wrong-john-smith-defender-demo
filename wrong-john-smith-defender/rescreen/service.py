"""High-level operations used by the CLI, the HTTP API and the acceptance run."""
from __future__ import annotations

import json
from pathlib import Path

from . import feeds, jobs, kyc
from .config import load_policy
from .db import connect, set_meta
from .paths import ACTORS, DEFAULT_DB, FEED_FILES, KYC_V1, POLICIES

SOURCES = {"UK": "FICT-UK-SL", "US": "FICT-US-SL", "CN": "FICT-CN-ML"}


def reset(db_path: Path | str = DEFAULT_DB) -> dict:
    """Fresh demo database: seeded actors, KYC V1, UK V1 / US V1 / CN V1 feeds, initial screening job."""
    p = Path(db_path)
    if p.exists():
        p.unlink()
    conn = connect(p)
    set_meta(conn, "clock_start", load_policy()["policy"]["simulated_clock_start"])
    set_meta(conn, "clock_tick", 0)
    for a in json.loads(ACTORS.read_text(encoding="utf-8"))["actors"]:
        conn.execute("INSERT INTO actors VALUES(?,?,?,?)", (a["actor_id"], a["display_name"], a["role"], a["entity"]))
    k = kyc.import_snapshot(conn, KYC_V1)
    loads = [feeds.load_feed(conn, FEED_FILES[(jur, "V1")], SOURCES[jur], jur) for jur in ("UK", "US", "CN")]
    job = jobs.run_rescreen(conn, "initial_screening")
    return {"conn": conn, "kyc": k, "feed_loads": loads, "job": job}


def load_feed(conn, jurisdiction: str, version: str | None = None, path: str | None = None) -> dict:
    f = Path(path) if path else FEED_FILES[(jurisdiction, version)]
    res = feeds.load_feed(conn, f, SOURCES[jurisdiction], jurisdiction)
    res["rescreen_job"] = jobs.run_rescreen(conn, "list_change") if res["result"] == "ACTIVATED" else None
    return res


def simulate_feed_failure(conn, jurisdiction: str = "UK") -> dict:
    return load_feed(conn, jurisdiction, "V3_MALFORMED")


def update_customer(conn, customer_id: str, changes: dict, actor: str) -> dict:
    res = kyc.update_customer(conn, customer_id, changes, actor)
    res["rescreen_job"] = jobs.run_rescreen(conn, "kyc_change", [customer_id]) if res["material"] else None
    return res


def policies() -> dict:
    return json.loads(POLICIES.read_text(encoding="utf-8"))
