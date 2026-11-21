"""Smoke test for the secondary Streamlit check view (renders both cases without exceptions)."""
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_rescreen_app_renders_both_cases(tmp_path, monkeypatch, accepted):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rescreen_state").mkdir()
    shutil.copy(accepted["db"], tmp_path / "rescreen_state" / "ui.sqlite")
    at = AppTest.from_file(str(ROOT / "rescreen_app.py"), default_timeout=60).run()
    assert not at.exception
    for cid in ("RESCREEN-A", "RESCREEN-B"):
        at.sidebar.selectbox(key="case").set_value(cid).run()
        assert not at.exception
        assert any(cid in s.value for s in at.subheader)
