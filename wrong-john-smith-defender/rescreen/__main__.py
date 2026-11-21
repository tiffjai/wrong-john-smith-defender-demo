"""CLI: python -m rescreen <command> [options]   (all output is JSON unless noted)

  reset | acceptance | load-feed --jurisdiction UK --version V2 | simulate-feed-failure | sweep | rescreen
  retry --job JOB-... | update-customer --customer ID --changes JSON --actor ID
  propose --case ID --actor ID --rationale TXT --basis-type T --customer-evidence EV --list-evidence EV [--evidence EV ...]
  approve|return --case ID --actor ID [--comment TXT] | request-evidence --case ID --actor ID --comment TXT
  escalate --case ID --actor ID --queue Legal|Sanctions --comment TXT
  case|packet|handoff --case ID | jurisdictions --case ID --primary UK|US|CN | reviews | feeds | jobs
  export [--out DIR] | serve [--port 8765] | freeze-policy
"""
import argparse
import json
import sys

from . import feeds, jobs, service, views, workflow
from .db import connect
from .paths import DEFAULT_DB, EXPORT_DIR


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rescreen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    for opt in ("--jurisdiction", "--version", "--job", "--customer", "--changes", "--actor", "--case", "--rationale", "--basis-type",
                "--customer-evidence", "--list-evidence", "--comment", "--queue", "--primary", "--out"):
        ap.add_argument(opt)
    ap.add_argument("--evidence", action="append", default=[])
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    out = lambda o: print(json.dumps(o, indent=2, ensure_ascii=False, default=str))
    c = a.command
    if c == "acceptance":
        from .acceptance import run
        rep = run(a.db if a.db != str(DEFAULT_DB) else "rescreen_state/acceptance.sqlite", a.out or EXPORT_DIR)
        return 0 if rep["passed"] else 1
    if c == "freeze-policy":
        from .config import freeze_policy
        out(freeze_policy())
        return 0
    if c == "reset":
        r = service.reset(a.db)
        out({k: v for k, v in r.items() if k != "conn"})
        return 0
    if c == "serve":
        from .api import serve
        serve(a.db, port=a.port)
        return 0
    conn = connect(a.db)
    try:
        if c == "load-feed":
            out(service.load_feed(conn, a.jurisdiction, a.version))
        elif c == "simulate-feed-failure":
            out(service.simulate_feed_failure(conn, a.jurisdiction or "UK"))
        elif c == "sweep":
            out(jobs.daily_sweep(conn))
        elif c == "rescreen":
            out(jobs.run_rescreen(conn, "manual"))
        elif c == "retry":
            out(jobs.retry(conn, a.job))
        elif c == "update-customer":
            out(service.update_customer(conn, a.customer, json.loads(a.changes), a.actor))
        elif c == "propose":
            out(workflow.propose_closure(conn, a.case, a.actor, a.rationale, a.evidence, a.basis_type, a.customer_evidence, a.list_evidence))
        elif c == "approve":
            out(workflow.approve(conn, a.case, a.actor, a.comment or ""))
        elif c == "return":
            out(workflow.return_proposal(conn, a.case, a.actor, a.comment or ""))
        elif c == "request-evidence":
            out(workflow.request_evidence(conn, a.case, a.actor, a.comment or ""))
        elif c == "escalate":
            out(workflow.escalate(conn, a.case, a.actor, a.queue, a.comment or ""))
        elif c == "case":
            out(views.case_view(conn, a.case))
        elif c == "packet":
            out(views.evidence_packet(conn, a.case))
        elif c == "handoff":
            out(views.challenger_handoff(conn, a.case))
        elif c == "jurisdictions":
            out(views.jurisdiction_view(conn, a.case, a.primary or "UK"))
        elif c == "reviews":
            out(views.reviews(conn))
        elif c == "feeds":
            out(feeds.status(conn))
        elif c == "jobs":
            out(jobs.jobs(conn))
        elif c == "export":
            out([str(p) for p in views.export_all(conn, a.out or EXPORT_DIR)])
        else:
            ap.error(f"unknown command {c}")
    except workflow.WorkflowError as e:
        out({"error": e.code, "message": str(e)})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
