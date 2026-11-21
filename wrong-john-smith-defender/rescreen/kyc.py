"""Customer registry keyed by stable customer ID (synthetic KYC snapshot import + material updates)."""
from __future__ import annotations

import json
from pathlib import Path

from defender.config import canonical_json

from .config import load_policy
from .db import now
from .evidence import PLACEHOLDER_DOBS
from .paths import KYC_V1

REQUIRED = ("customer_id", "names", "dob", "national_id", "booking_entity")


def import_snapshot(conn, path: Path = KYC_V1) -> dict:
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    at = now(conn)
    imported, rejected = [], []
    conn.execute("BEGIN")
    for c in snap["customers"]:
        missing = [k for k in REQUIRED if k not in c]
        if missing:
            rejected.append({"customer_id": c.get("customer_id"), "reasons": [f"missing {m}" for m in missing]})
            continue
        if c["dob"].get("value") in PLACEHOLDER_DOBS:
            c["dob"]["placeholder_flag"] = True  # represented as unknown downstream
        row = conn.execute("SELECT version FROM customers WHERE customer_id=?", (c["customer_id"],)).fetchone()
        ver = (row["version"] + 1) if row else 1
        conn.execute("INSERT OR REPLACE INTO customers(customer_id,version,kyc_snapshot_id,data,updated_at) VALUES(?,?,?,?,?)",
                     (c["customer_id"], ver, snap["kyc_snapshot_id"], json.dumps(c, ensure_ascii=False), at))
        conn.execute("INSERT OR REPLACE INTO customer_versions(customer_id,version,data,change,actor,at) VALUES(?,?,?,?,?,?)",
                     (c["customer_id"], ver, json.dumps(c, ensure_ascii=False), json.dumps({"type": "import"}), "system", at))
        imported.append(c["customer_id"])
    active = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    counts = {"received": len(snap["customers"]), "imported": len(imported), "rejected": len(rejected), "active": active,
              "rejected_detail": rejected}
    conn.execute("INSERT OR REPLACE INTO kyc_snapshots(kyc_snapshot_id,imported_at,counts) VALUES(?,?,?)",
                 (snap["kyc_snapshot_id"], at, json.dumps(counts)))
    conn.execute("COMMIT")
    return {"kyc_snapshot_id": snap["kyc_snapshot_id"], "source_id": snap["source_id"], **counts}


def current(conn, customer_ids=None) -> list[dict]:
    rows = conn.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
    return [{"data": json.loads(r["data"]), "source_id": "SYN-KYC", "kyc_snapshot_id": r["kyc_snapshot_id"], "version": r["version"]}
            for r in rows if customer_ids is None or r["customer_id"] in customer_ids]


def update_customer(conn, customer_id: str, changes: dict, actor: str) -> dict:
    """Apply field changes to the SAME customer record (new version). Returns material change info."""
    row = conn.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
    if not row:
        raise KeyError(customer_id)
    data = json.loads(row["data"])
    new = {**data, **changes}
    material_fields = load_policy()["policy"]["material_kyc_fields"]
    changed = sorted(k for k in set(data) | set(new) if canonical_json(data.get(k)) != canonical_json(new.get(k)))
    material = [k for k in changed if k in material_fields]
    if not changed:
        return {"customer_id": customer_id, "version": row["version"], "changed_fields": [], "material": False}
    at = now(conn)
    ver = row["version"] + 1
    conn.execute("BEGIN")
    conn.execute("UPDATE customers SET version=?, data=?, updated_at=? WHERE customer_id=?",
                 (ver, json.dumps(new, ensure_ascii=False), at, customer_id))
    conn.execute("INSERT INTO customer_versions(customer_id,version,data,change,actor,at) VALUES(?,?,?,?,?,?)",
                 (customer_id, ver, json.dumps(new, ensure_ascii=False),
                  json.dumps({"type": "update", "changed_fields": changed, "material_fields": material}), actor, at))
    conn.execute("COMMIT")
    return {"customer_id": customer_id, "version": ver, "changed_fields": changed, "material": bool(material),
            "material_fields": material}
