"""Tiny local JSON API (stdlib only) for the Next.js dashboard. Binds 127.0.0.1. Offline.

Actor for POSTs: header `X-Demo-Actor` (simulated sign-in with seeded roles) or body field "actor".
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import feeds, jobs, service, views, workflow
from .db import connect

ROUTES_DOC = {
    "GET /api/health": "liveness + contract version",
    "GET /api/feeds": "feed health, active snapshots, checks, reconciliation, diff",
    "GET /api/jobs": "rescreen jobs (trigger, scope, snapshots, status, counts)",
    "GET /api/cases": "alert queue (all cases)",
    "GET /api/cases/{case_id}": "single case view",
    "GET /api/cases/{case_id}/packet": "label-free evidence packet",
    "GET /api/cases/{case_id}/challenger-handoff": "changed fields + approval basis + evidence IDs only",
    "GET /api/cases/{case_id}/jurisdictions?primary=UK|US|CN": "UK/US/CN matrix with fictional measures",
    "GET /api/reviews": "pending work vs completed decisions",
    "POST /api/demo/reset": "fresh demo DB (V1 loaded, initial screening)",
    "POST /api/feeds/load {jurisdiction, version}": "validate + activate + rescreen",
    "POST /api/feeds/simulate-failure": "load malformed V3 (last-good kept)",
    "POST /api/jobs/sweep": "daily sweep (same job logic)",
    "POST /api/jobs/{job_id}/retry": "retry a failed job",
    "POST /api/customers/{customer_id} {changes}": "KYC update; material change triggers rescreen",
    "POST /api/cases/{case_id}/propose {rationale, evidence_ids, basis_type, customer_evidence_id, list_evidence_id}": "analyst proposes FP closure",
    "POST /api/cases/{case_id}/approve {comment}": "different senior approves",
    "POST /api/cases/{case_id}/return {comment}": "different senior returns",
    "POST /api/cases/{case_id}/request-evidence {comment}": "-> AWAITING_EVIDENCE",
    "POST /api/cases/{case_id}/escalate {queue, comment}": "-> ESCALATED",
    "POST /api/cases/{case_id}/ai-response {suggestion_id, action, text}": "accept/amend/reject AI suggestion",
}


ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}


class App:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = connect(db_path)

    def handle(self, method, path, query, body, actor):
        p = path.rstrip("/")
        if method == "GET":
            if p == "/api/health":
                return 200, {"status": "ok", "contract_version": views.CONTRACT_VERSION, "grok_live": False, "routes": ROUTES_DOC}
            if p == "/api/feeds":
                return 200, {"contract_version": views.CONTRACT_VERSION, "feeds": feeds.status(self.conn)}
            if p == "/api/jobs":
                return 200, {"contract_version": views.CONTRACT_VERSION, "jobs": jobs.jobs(self.conn)}
            if p == "/api/reviews":
                return 200, views.reviews(self.conn)
            if p == "/api/cases":
                rows = [dict(r) for r in self.conn.execute("SELECT case_id,customer_id,source_id,entry_id,state,owner,priority,reason,created_at,updated_at,reopen_count FROM alerts ORDER BY case_id")]
                return 200, {"contract_version": views.CONTRACT_VERSION, "cases": rows}
            m = re.fullmatch(r"/api/cases/([\w-]+)(?:/(packet|challenger-handoff|jurisdictions))?", p)
            if m:
                cid, sub = m.groups()
                if sub is None:
                    return 200, views.case_view(self.conn, cid)
                if sub == "packet":
                    return 200, views.evidence_packet(self.conn, cid)
                if sub == "challenger-handoff":
                    return 200, views.challenger_handoff(self.conn, cid)
                return 200, views.jurisdiction_view(self.conn, cid, query.get("primary", ["UK"])[0])
            return 404, {"error": "not found"}
        if method == "POST":
            if p == "/api/demo/reset":
                self.conn.close()
                self.conn = service.reset(self.db_path)["conn"]
                return 200, {"status": "reset"}
            if p == "/api/feeds/load":
                return 200, service.load_feed(self.conn, body["jurisdiction"], body["version"])
            if p == "/api/feeds/simulate-failure":
                return 200, service.simulate_feed_failure(self.conn, body.get("jurisdiction", "UK"))
            if p == "/api/jobs/sweep":
                return 200, jobs.daily_sweep(self.conn)
            m = re.fullmatch(r"/api/jobs/([\w-]+)/retry", p)
            if m:
                return 200, jobs.retry(self.conn, m.group(1))
            m = re.fullmatch(r"/api/customers/([\w-]+)", p)
            if m:
                return 200, service.update_customer(self.conn, m.group(1), body["changes"], actor)
            m = re.fullmatch(r"/api/cases/([\w-]+)/(propose|approve|return|request-evidence|escalate|ai-response)", p)
            if m:
                cid, act = m.groups()
                if act == "propose":
                    return 200, workflow.propose_closure(self.conn, cid, actor, body.get("rationale", ""), body.get("evidence_ids", []),
                                                         body["basis_type"], body["customer_evidence_id"], body["list_evidence_id"])
                if act == "approve":
                    return 200, workflow.approve(self.conn, cid, actor, body.get("comment", ""))
                if act == "return":
                    return 200, workflow.return_proposal(self.conn, cid, actor, body.get("comment", ""))
                if act == "request-evidence":
                    return 200, workflow.request_evidence(self.conn, cid, actor, body.get("comment", ""))
                if act == "escalate":
                    return 200, workflow.escalate(self.conn, cid, actor, body["queue"], body.get("comment", ""))
                return 200, workflow.respond_to_ai(self.conn, cid, body["suggestion_id"], actor, body["action"], body.get("text", ""))
            return 404, {"error": "not found"}
        return 405, {"error": "method not allowed"}


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            origin = self.headers.get("Origin")
            if origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Demo-Actor")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, {})

        def _dispatch(self, method):
            u = urlparse(self.path)
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, {"error": "invalid JSON body"})
            actor = self.headers.get("X-Demo-Actor") or body.get("actor")
            try:
                with app.lock:
                    code, obj = app.handle(method, u.path, parse_qs(u.query), body, actor)
            except workflow.WorkflowError as e:
                code, obj = (403 if e.code in ("ROLE_NOT_ALLOWED", "SELF_APPROVAL_FORBIDDEN", "UNKNOWN_ACTOR") else 409), {"error": e.code, "message": str(e)}
            except KeyError as e:
                code, obj = 404, {"error": "not found", "message": str(e)}
            except (ValueError, TypeError) as e:
                code, obj = 400, {"error": "bad request", "message": str(e)}
            self._send(code, obj)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def log_message(self, fmt, *args):
            pass

    return H


def serve(db_path, host="127.0.0.1", port=8765):
    app = App(db_path)
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"rescreen API on http://{host}:{port}  (db {db_path})", flush=True)
    srv.serve_forever()
