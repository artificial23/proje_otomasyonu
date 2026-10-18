import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="kulucka_test_")
os.environ["KULUCKA_VERI_DIZINI"] = _TMP
os.environ["KULUCKA_ZAMANLAYICI"] = "harici"
os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from modules import database, seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    database.init_db()
    seed.seed_defaults()
    yield


FIXTURES = Path(__file__).parent / "fixtures"
