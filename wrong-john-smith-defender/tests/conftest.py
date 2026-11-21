import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defender.pipeline import run_pipeline  # noqa: E402


@pytest.fixture(scope="session")
def result():
    return run_pipeline()
