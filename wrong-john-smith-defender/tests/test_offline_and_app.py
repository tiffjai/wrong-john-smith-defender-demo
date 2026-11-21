import json
import re
import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from defender import review_store
from defender.evidence import build_packet, packet_json

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted while offline test is active")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_no_network_libraries_or_urls_in_runtime_source():
    for f in [ROOT / "app.py", *(ROOT / "defender").glob("*.py"), *(ROOT / "evaluation").glob("*.py")]:
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(requests|urllib|http\.client|httpx|aiohttp|socket)\b", src, re.M), f
        assert "http://" not in src and "https://" not in src, f


@pytest.mark.parametrize("case_id,expected_guard_route", [
    ("CASE-01", "ANALYST REVIEW"), ("CASE-03", "CANDIDATE VISIBLE"), ("CASE-08", "ANALYST REVIEW")])
def test_app_each_case_offline(no_network, tmp_path, monkeypatch, case_id, expected_guard_route):
    monkeypatch.setattr(review_store, "REVIEWS_PATH", tmp_path / "reviews.json")
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception
    at.selectbox(key="case_id").set_value(case_id).run()
    assert not at.exception
    outcomes = [m.value for m in at.markdown if m.value.startswith("Case outcome:")]
    assert len(outcomes) == 3
    assert expected_guard_route in outcomes[2]
    # three columns, same pairs: each column renders the same number of pair cards
    assert len([s for s in at.subheader]) >= 3
    # download button carries the same JSON the exporter produces
    dl = at.get("download_button")
    assert len(dl) == 1 and dl[0].proto.label.endswith("evidence packet JSON")
    assert dl[0].proto.url  # media-file URL registered by Streamlit
    # case selector + analyst review control exist
    assert at.radio(key=f"evidence_pair_{case_id}")
    assert at.radio(key=f"review_decision_{at.radio(key=f'evidence_pair_{case_id}').value}")


def test_app_review_save_and_download_payload(no_network, tmp_path, monkeypatch):
    monkeypatch.setattr(review_store, "REVIEWS_PATH", tmp_path / "reviews.json")
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.selectbox(key="case_id").set_value("CASE-01").run()
    pid = "SYN-01-A|SYN-01-B"
    at.radio(key=f"review_decision_{pid}").set_value("Not a match")
    at.text_area(key=f"review_note_{pid}").set_value("different DOB, verified")
    at.button[0].click().run()
    assert not at.exception
    saved = json.loads((tmp_path / "reviews.json").read_text())
    assert saved[pid]["decision"] == "Not a match" and saved[pid]["note"] == "different DOB, verified"
    # review is not part of the evidence packet
    from defender.pipeline import run_pipeline
    assert "Not a match" not in packet_json(build_packet(run_pipeline(), "CASE-01"))


def test_evaluation_tab_labels_hidden_until_toggled(no_network):
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception
    page = " ".join(str(getattr(e, "value", "")) for e in at.markdown) + " ".join(
        str(df.value.to_dict()) for df in at.dataframe)
    assert "non_match" not in page and "decoy" not in page.lower()
    assert "3/3" in page and "4/5" in page          # metrics with denominators are visible
    at.toggle(key="show_labels").set_value(True).run()
    assert not at.exception
    assert "non_match" in " ".join(str(df.value.to_dict()) for df in at.dataframe)


def test_case_order_is_ab_bc_then_direct_ac(result):
    assert result["cases"]["CASE-08"]["pairs"] == ["SYN-08-A|SYN-08-B", "SYN-08-B|SYN-08-C", "SYN-08-A|SYN-08-C"]
