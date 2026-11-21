"""Rescreen case view for OUR verification (secondary; the product UI is the team's Next.js dashboard).

Run: ./run_rescreen.sh ui   (uses rescreen_state/ui.sqlite; fully offline, no Grok)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from rescreen import feeds, jobs, service, views, workflow
from rescreen.db import connect

DB = Path("rescreen_state/ui.sqlite")
st.set_page_config(page_title="Rescreen case view (synthetic)", layout="wide")


@st.cache_resource
def conn():
    if not DB.exists():
        service.reset(DB)["conn"].close()
    return connect(DB)


c = conn()
st.title("Track 3 rescreening — case view (synthetic, offline)")
st.error("SYNTHETIC DATA ONLY. Simulated sign-in with seeded roles. Challenger/Grok: live unavailable; any AI text shown is a labelled replay.")
with st.sidebar:
    st.header("Feeds & jobs")
    if st.button("Reset demo (V1)"):
        st.cache_resource.clear()
        service.reset(DB)["conn"].close()
        st.rerun()
    if st.button("Load V2"):
        st.session_state["last"] = service.load_feed(c, "UK", "V2")
    if st.button("Simulate feed failure"):
        st.session_state["last"] = service.simulate_feed_failure(c)
    if st.button("Run daily sweep"):
        st.session_state["last"] = jobs.daily_sweep(c)
    if "last" in st.session_state:
        st.json(st.session_state["last"], expanded=False)
    actor = st.selectbox("Act as (simulated sign-in)", [r["actor_id"] for r in c.execute("SELECT actor_id FROM actors ORDER BY actor_id")])
    cases = [r["case_id"] for r in c.execute("SELECT case_id FROM alerts ORDER BY case_id")]
    if "case" not in st.session_state and st.query_params.get("case") in cases:
        st.session_state["case"] = st.query_params["case"]
    case_id = st.selectbox("Case", cases, key="case")

t1, t2, t3, t4 = st.tabs(["Case", "Reviews", "Jurisdictions", "Feeds"])
with t1:
    cv = views.case_view(c, case_id)
    h = cv["case"]
    st.subheader(f"{case_id} · state {h['state']} · {h['disposition']}")
    st.caption(f"alert key {h['alert_key']} · owner {h['owner']} · priority {h['priority']} · reopened {h['reopen_count']}x")
    cs = cv["current_screening"]
    a, b, g = st.columns(3)
    a.metric("Name-only (RapidFuzz)", cs["name_only"]["decision"], f"score {cs['name_only']['score']}")
    b.metric("Splink / DuckDB", cs["splink"]["decision"], f"P={cs['splink']['match_probability']:.4f}")
    g.metric("Splink + guard", cs["guard"]["decision"], cs["guard"]["outcome"])
    st.markdown("**Evidence (supporting / conflicting / missing)**")
    st.dataframe(pd.DataFrame(cs["evidence_classification"]), hide_index=True, width="stretch")
    st.markdown("**V1 / V2 evidence side by side**")
    sbs = cv["evidence_side_by_side"]
    st.dataframe(pd.DataFrame([{"subject": r["subject_type"], "field": r["field"], "changed": r["changed"],
                                **{col: "; ".join(f"{x['evidence_id']}={x['value']} ({x['precision']}, {x['verification']})" for x in r["values"][col]) or "—"
                                   for col in sbs["columns"]}} for r in sbs["rows"]]), hide_index=True, width="stretch")
    st.markdown("**Earlier rationale and decisions**")
    for d in cv["earlier_rationale_and_decisions"]:
        st.write(f"- {d['decided_at']} · {d['decision']} ({d['validity']}) by {d['reviewer']} on proposal by {d['proposer']}: "
                 f"*{d['rationale']}* — basis: {d['basis']['statement']}")
    st.markdown("**Events**")
    st.dataframe(pd.DataFrame([{"seq": e["seq"], "at": e["at"], "type": e["type"], "actor": e["actor"], "job": e["job_id"]} for e in cv["events"]]), hide_index=True)
    ch = cv["ai"]["challenger"]
    with st.expander("Challenger (live unavailable)"):
        st.write(ch["live"]["reason"])
        if ch["replay"]:
            st.warning(ch["replay"]["replay_label"])
            st.json(ch["replay"])
        st.json(views.challenger_handoff(c, case_id), expanded=False)
    st.markdown("**Actions**")
    ev = {(i["subject_type"], i["field"]): i["evidence_id"] for i in cv["current_evidence"]}
    if "propose_closure" in cv["allowed_actions"]:
        bt = st.selectbox("Basis", ["verified_identifier_conflict", "verified_full_dob_conflict"])
        fld = "national_id" if bt == "verified_identifier_conflict" else "dob"
        rat = st.text_input("Rationale")
        if st.button("Propose false-positive closure"):
            try:
                st.success(workflow.propose_closure(c, case_id, actor, rat, [], bt, ev[("customer", fld)], ev[("list_entry", fld)]))
            except workflow.WorkflowError as e:
                st.error(str(e))
    if "approve" in cv["allowed_actions"]:
        for label, fn in (("Approve", workflow.approve), ("Return", workflow.return_proposal)):
            if st.button(label):
                try:
                    st.success(fn(c, case_id, actor, f"{label} via check UI"))
                except workflow.WorkflowError as e:
                    st.error(str(e))
    if "request_evidence" in cv["allowed_actions"] and st.button("Request evidence"):
        try:
            st.success(workflow.request_evidence(c, case_id, actor, "request independent identifier"))
        except workflow.WorkflowError as e:
            st.error(str(e))
with t2:
    rv = views.reviews(c)
    st.markdown(f"**Pending ({rv['counts']['pending']})**")
    st.dataframe(pd.DataFrame(rv["pending"]), hide_index=True, width="stretch")
    st.markdown(f"**Completed decisions ({rv['counts']['completed']})**")
    st.dataframe(pd.DataFrame([{k: d[k] for k in ("case_id", "decision", "validity", "proposer", "reviewer", "decided_at")} for d in rv["completed"]]), hide_index=True)
with t3:
    prim = st.radio("Primary view", ["UK", "US", "CN"], horizontal=True)
    jv = views.jurisdiction_view(c, case_id, prim)
    st.caption(jv["fictional_measures_notice"])
    st.write(f"Default queue: **{jv['default_queue']}** · potential conflict: **{jv['potential_conflict']['status']}**")
    st.dataframe(pd.DataFrame([{**r, "measures": ", ".join(m["measure_id"] for m in r["measures"]), "identity_evidence": json.dumps(r["identity_evidence"])} for r in jv["rows"]]), hide_index=True, width="stretch")
with t4:
    st.dataframe(pd.DataFrame([{k: f[k] for k in ("jurisdiction", "source_id", "active_snapshot_id", "last_check_result", "coverage", "rescreen_completed_at")} for f in feeds.status(c)]), hide_index=True, width="stretch")
