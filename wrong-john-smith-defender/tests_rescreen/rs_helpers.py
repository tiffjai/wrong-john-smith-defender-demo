"""Shared helpers for the rescreen tests."""
from rescreen import acceptance


def approve_both(conn):
    from rescreen import workflow
    ev = acceptance.ev_id
    a1, a2 = ev(conn, "RESCREEN-A", "customer", "national_id"), ev(conn, "RESCREEN-A", "list_entry", "national_id")
    workflow.propose_closure(conn, "RESCREEN-A", "ana.analyst", "id conflict", [a1, a2], "verified_identifier_conflict", a1, a2)
    workflow.approve(conn, "RESCREEN-A", "rio.senior", "ok")
    b1, b2 = ev(conn, "RESCREEN-B", "customer", "dob"), ev(conn, "RESCREEN-B", "list_entry", "dob")
    workflow.propose_closure(conn, "RESCREEN-B", "sam.analyst", "dob conflict", [b1, b2], "verified_full_dob_conflict", b1, b2)
    workflow.approve(conn, "RESCREEN-B", "kai.senior", "ok")
