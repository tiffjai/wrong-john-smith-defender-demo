"""Wrong John Smith Defender - analyst dashboard (SYNTHETIC DATA, runs fully offline)."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from defender import review_store
from defender.evidence import build_packet, packet_json
from defender.pipeline import run_pipeline

st.set_page_config(page_title="Wrong John Smith Defender", page_icon="🛡️", layout="wide")

DECISION_BADGE = {"LINK": ":blue-badge[LINK]", "REVIEW": ":orange-badge[ANALYST REVIEW]", "NO_LINK": ":gray-badge[NO LINK]"}
ROUTE_BADGE = {"ANALYST_REVIEW": ":orange-badge[ANALYST REVIEW]", "CANDIDATE_VISIBLE": ":blue-badge[CANDIDATE VISIBLE]",
               "NO_CANDIDATE": ":gray-badge[NO CANDIDATE SURFACED]"}
METHODS = [("name_only", "1 · Name-only (RapidFuzz)"), ("splink", "2 · Splink"), ("splink_guard", "3 · Splink + contradiction guard")]


@st.cache_resource(show_spinner="Scoring synthetic records (Splink + DuckDB, offline)...")
def get_result():
    return run_pipeline()


@st.cache_data(show_spinner=False)
def get_evaluation():
    from evaluation.evaluate import evaluate  # labels live only in the evaluation package
    return evaluate(get_result())


def unk(v):
    return "unknown" if v in (None, "") else v


def pair_title(p):
    return f"{p['left_tag']}–{p['right_tag']}"


def records_table(res, case_id):
    rows = []
    for rid in res["cases"][case_id]["records"]:
        r = res["records_by_id"][rid]
        d, v = r["derived"]["dob"], r["dob"]["verification"]
        rows.append({
            "Tag": r["tag"], "Record ID": rid, "Source ID": r["source"]["source_id"], "Source": r["source"]["source_name"],
            "Name (raw)": unk(r["name"]["raw"]), "DOB (raw)": unk(r["dob"]["raw"]), "DOB normalised": unk(d["value"]),
            "Date precision": d["precision"], "DOB verification": v["status"],
            "Verification source ID": unk(v["source_id"]), "Verification method": unk(v["method"]),
            "Country (raw)": unk(r["country"]["raw"]), "City (raw)": unk(r["city"]["raw"]),
        })
    return pd.DataFrame(rows)


def pair_summary(p, method):
    if method == "name_only":
        s = p["name_only"]
        score = "n/a" if s["score"] is None else f"{s['score']:.1f} / 100"
        return DECISION_BADGE[s["decision"]], f"name score {score}"
    if method == "splink":
        s = p["splink"]
        return DECISION_BADGE[s["decision"]], f"P(match) {s['match_probability']:.3f} · weight {s['match_weight']:+.2f}"
    g = p["guarded"]
    note = {"PASS_NO_CONTRADICTION": "no contradiction applies",
            "ROUTED_TO_REVIEW_DIRECT_CONTRADICTION": "direct DOB contradiction",
            "ROUTED_TO_REVIEW_CHAIN_CONTRADICTION": "chain contradiction",
            "CONTRADICTION_NOTED_NOT_SURFACED": "contradiction noted"}[g["outcome"]]
    return DECISION_BADGE[g["decision"]], f"P(match) {p['splink']['match_probability']:.3f} · {note}"


def edge_caption(p):
    return ("Splink link edge" if p["splink"]["decision"] == "LINK" else "direct comparison (not a Splink link)")


def contributions_df(p):
    rows = []
    for c in p["splink"]["contributions"]:
        rows.append({"Field": c["field"], "Level": c["level_description"],
                     "m": "—" if c["m_probability"] is None else f"{c['m_probability']:g}",
                     "u": "—" if c["u_probability"] is None else f"{c['u_probability']:g}",
                     "Bayes factor": round(c["bayes_factor"], 4), "Match weight (log2)": round(c["match_weight"], 3)})
    return pd.DataFrame(rows)


def render_three_columns(res, case_id):
    case = res["cases"][case_id]
    pairs = [res["pairs_by_id"][pid] for pid in case["pairs"]]
    st.caption(f"All three columns show the **same {len(pairs)} candidate pairs** "
               f"(generated once by blocking: {', '.join(sorted({r for p in pairs for r in p['blocking_rules']}))}).")
    cols = st.columns(3)
    for col, (m, title) in zip(cols, METHODS):
        with col:
            st.subheader(title)
            st.markdown("Case outcome: " + ROUTE_BADGE[case["routes"][m]])
            for p in pairs:
                badge, detail = pair_summary(p, m)
                with st.container(border=True):
                    st.markdown(f"**{pair_title(p)}** · {p['left']} ↔ {p['right']}")
                    st.markdown(f"{badge} &nbsp; {detail}")
                    st.caption(edge_caption(p))


def render_evidence(res, p):
    st.markdown(f"#### Evidence for pair **{pair_title(p)}** ({p['left']} ↔ {p['right']})")
    if p["splink"]["contributions"][0]["level_key"] == "alias":
        a = res["alias"]["groups"][res["records_by_id"][p["left"]]["derived"]["alias_group"]]
        st.info(f"Candidate found through a **documented alias**: group `{a['alias_group']}`, source `{a['source_id']}` "
                f"({a['source_name']}). Forms: " + ", ".join(f["form"] for f in a["forms"]))
    with st.container(border=True):
        st.markdown("**1 · Name-only (RapidFuzz)**")
        s = p["name_only"]
        st.write(f"Compared normalised names {s.get('compared')} with `{s['scorer']}` → score **{s['score']}** "
                 f"(link ≥ {s['thresholds']['link']}, review ≥ {s['thresholds']['review']}) → **{s['decision']}**")
        st.caption("Uses the name string only. It cannot see dates, places, aliases or verification.")
    with st.container(border=True):
        st.markdown("**2 · Splink field contributions** (fixed m/u from the frozen config)")
        s = p["splink"]
        st.dataframe(contributions_df(p), hide_index=True, width="stretch")
        st.write(f"Prior weight {s['prior_match_weight']:+.3f} + Σ field weights = **{s['match_weight']:+.3f}** "
                 f"→ P(match) **{s['match_probability']:.4f}** → **{s['decision']}** "
                 f"(link ≥ {res['config']['parameters']['splink']['link_threshold_probability']}, "
                 f"review ≥ {res['config']['parameters']['splink']['review_threshold_probability']})")
        st.caption("Unknown fields (level 'unknown') contribute weight 0: they are neither support nor mismatch.")
    with st.container(border=True):
        st.markdown("**3 · Contradiction guard**")
        g = p["guarded"]
        chk = g["dob_check"]
        st.write(f"Outcome: **{g['outcome']}** → decision **{g['decision']}**"
                 + (" (changed by guard)" if g["changed_by_guard"] else ""))
        st.dataframe(pd.DataFrame([
            {"Side": "left " + chk["left"]["record_id"], "Raw DOB": unk(chk["left"]["raw"]), "Precision": chk["left"]["precision"], "Verification": chk["left"]["verification"]},
            {"Side": "right " + chk["right"]["record_id"], "Raw DOB": unk(chk["right"]["raw"]), "Precision": chk["right"]["precision"], "Verification": chk["right"]["verification"]},
        ]), hide_index=True, width="stretch")
        st.write(f"DOB check: **{chk['status']}**")
        for r in chk["reasons"]:
            st.markdown(f"- {r}")
        for r in g["reasons"]:
            st.markdown(f"- guard: {r}")


def render_chain(res, case_id):
    comps = res["cases"][case_id]["components"]
    pairs = [res["pairs_by_id"][pid] for pid in res["cases"][case_id]["pairs"]]
    if len(res["cases"][case_id]["records"]) < 3:
        return
    st.markdown("#### Chain view: A–B, B–C and the direct A–C comparison")
    for p in pairs:
        chk = p["guarded"]["dob_check"]
        st.markdown(f"- **{pair_title(p)}**: Splink {p['splink']['decision']} (P={p['splink']['match_probability']:.3f}); "
                    f"DOB check **{chk['status']}** ({'; '.join(chk['reasons'])}); guard → **{p['guarded']['decision']}**")
    for c in comps:
        verdict = ("contains a verified full-DOB contradiction in " + ", ".join(c["contradicting_pairs"])) if c["has_contradiction"] else "no contradiction"
        msg = f"Linked component {', '.join(c['records'])}: {verdict}."
        (st.warning if c["has_contradiction"] else st.success)(msg)


def render_review(case_id, pair):
    pid = pair["pair_id"]
    st.markdown(f"### Analyst review — pair {pair_title(pair)} ({pid})")
    st.caption("Your decision is stored in `reviews/analyst_reviews.json` on this machine. It is not part of the evidence packet and never changes the scores.")
    saved = review_store.load().get(pid)
    with st.form(key=f"review_form_{pid}"):
        decision = st.radio("Decision", review_store.OPTIONS, horizontal=True, key=f"review_decision_{pid}",
                            index=review_store.OPTIONS.index(saved["decision"]) if saved else 0)
        note = st.text_area("Note", value=saved["note"] if saved else "", key=f"review_note_{pid}")
        submitted = st.form_submit_button("Save review")
    if submitted:
        rec = review_store.save(pid, case_id, decision, note)
        st.success(f"Saved: {pid} → {rec['decision']} at {rec['saved_at']}")
    elif saved:
        st.info(f"Last saved: {saved['decision']} ({saved['saved_at']}) — {saved['note'] or 'no note'}")


def tab_case(res):
    case_id = st.session_state["case_id"]
    case = res["cases"][case_id]
    pairs = [res["pairs_by_id"][pid] for pid in case["pairs"]]
    st.markdown(f"### {case_id}")
    st.markdown("**Records** (raw values exactly as in the source; unknown stays unknown)")
    st.dataframe(records_table(res, case_id), hide_index=True, width="stretch")
    st.markdown("### Three comparisons")
    render_three_columns(res, case_id)
    render_chain(res, case_id)
    st.markdown("### Evidence behind each decision")
    pid = st.radio("Pair", [p["pair_id"] for p in pairs], horizontal=True, key=f"evidence_pair_{case_id}",
                   format_func=lambda x: f"{pair_title(res['pairs_by_id'][x])}  ({x})")
    render_evidence(res, res["pairs_by_id"][pid])
    st.divider()
    render_review(case_id, res["pairs_by_id"][pid])
    st.divider()
    st.markdown("### Evidence packet (JSON)")
    packet = build_packet(res, case_id)
    text = packet_json(packet)
    st.download_button("⬇ Download evidence packet JSON", data=text, file_name=f"evidence_packet_{case_id}.json",
                       mime="application/json", key=f"dl_{case_id}")
    st.caption("Self-contained; contains raw values, sources, date precision, scores, field contributions and guard outcome. No evaluation labels.")
    with st.expander("Preview packet"):
        st.json(json.loads(text), expanded=1)


def tab_eval(res):
    ev = get_evaluation()
    d = ev["denominators"]
    st.markdown("### Evaluation (separate from scoring and from exports)")
    st.write(f"Thresholds frozen at **{ev['frozen_at']}** (config `{ev['config_sha256'][:16]}…`); evaluated at {ev['evaluated_at']}. "
             f"Denominators: **{d['candidate_pairs']}** candidate pairs, **{d['labelled_true_matches']}** labelled true matches, "
             f"**{d['labelled_non_matches']}** labelled non-matches.")
    m = ev["metrics"]
    rows = []
    for k, v in m["by_method"].items():
        rows.append({"Method": v["name"],
                     "False positives (auto-linked non-matches)": v["false_positives"]["text"],
                     "Missed true matches": v["missed_true_matches"]["text"],
                     "Manual-review pairs": v["manual_review"]["text"],
                     "True matches auto-linked": v["true_matches_linked"]["text"],
                     "True matches sent to review": v["true_matches_in_review"]["text"],
                     "Non-matches sent to review": v["non_matches_in_review"]["text"],
                     "Candidate recall (shared candidate set)": m["candidate_recall"]["text"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("FP = labelled non-match pairs / false positives; missed = labelled true-match pairs with neither LINK nor REVIEW; "
               "manual review = candidate pairs. Candidate recall = labelled true-match pairs that are in the candidate set / labelled true-match pairs.")
    ab = m["ablation_no_alias_table"]
    st.write(f"Ablation without the alias table: {ab['candidate_pairs_total']} candidate pairs, candidate recall {ab['candidate_recall']['text']} "
             f"(not candidates: {', '.join(ab['true_matches_not_candidates']) or 'none'}).")
    st.warning("Only 5 synthetic pairs in 3 scenarios, with parameters set by the builder who knew the scenarios. These counts demonstrate the pipeline; they are not evidence of real-world accuracy.")
    if st.toggle("Show evaluation labels and scenario names (analyst view hides these)", key="show_labels"):
        from evaluation.evaluate import load_labels
        lab = load_labels()
        st.dataframe(pd.DataFrame(lab["pair_labels"]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"case_id": k, **v} for k, v in lab["scenarios"].items()]), hide_index=True, width="stretch")
        decs = pd.DataFrame({v["name"]: v["decisions"] for v in m["by_method"].values()})
        st.dataframe(decs, width="stretch")


def tab_method(res):
    cfg = res["config"]
    st.markdown("### Frozen configuration")
    st.write(f"`frozen_at` {cfg['frozen_at']} · `config_sha256` `{cfg['config_sha256']}`")
    st.json(cfg["parameters"], expanded=1)
    st.markdown("### Documented alias table (synthetic)")
    for g in res["alias"]["groups"].values():
        st.write(f"**{g['alias_group']}** · source `{g['source_id']}` · {g['source_name']}")
        st.dataframe(pd.DataFrame(g["forms"]), hide_index=True)
    st.markdown("### Notes")
    st.markdown(
        "- **No EM training.** Five synthetic records are far too few; m/u probabilities are fixed in the frozen config.\n"
        "- **Guard:** only a verified, full-precision date of birth on both records that differs is a contradiction. "
        "Partial, unverified or unknown dates are *not assessable*, never a contradiction and never imputed.\n"
        "- **Chain check:** records joined by Splink LINK edges form a component; any pair in it with a contradiction sends all pairs in the component to review.\n"
        "- **Offline:** no network calls at runtime; all assets are local.")


def main():
    res = get_result()
    st.title("🛡️ Wrong John Smith Defender")
    st.error("SYNTHETIC DATA ONLY — every person, ID and source is fictional. The analyst makes the final screening decision.")
    with st.sidebar:
        st.header("Case")
        if "case_id" not in st.session_state and st.query_params.get("case") in res["cases"]:
            st.session_state["case_id"] = st.query_params["case"]   # deep link: ?case=CASE-08
        st.selectbox("Select case", sorted(res["cases"]), key="case_id")
        st.caption(f"Frozen config `{res['config']['config_sha256'][:12]}…`  \nfrozen {res['config']['frozen_at']}  \nSplink {res['splink_version']} · DuckDB backend · offline")
    t1, t2, t3 = st.tabs(["Case review", "Evaluation", "Method & parameters"])
    with t1:
        tab_case(res)
    with t2:
        tab_eval(res)
    with t3:
        tab_method(res)


main()
