import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rescreen import acceptance, service, views  # noqa: E402


@pytest.fixture
def fresh(tmp_path):
    s = service.reset(tmp_path / "t.sqlite")
    yield s["conn"]
    s["conn"].close()


@pytest.fixture(scope="session")
def accepted(tmp_path_factory):
    d = tmp_path_factory.mktemp("acc")
    rep = acceptance.run(str(d / "acc.sqlite"), d / "out", verbose=False)
    return {"report": rep, "out": d / "out", "db": d / "acc.sqlite"}


