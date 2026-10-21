import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from budzet import baza  # noqa: E402


@pytest.fixture
def conn_dane(tmp_path):
    """Baza tylko z danymi (bez formatek)."""
    c = baza.inicjalizuj(tmp_path / "t.db", z_formatkami=False)
    yield c
    c.close()


@pytest.fixture(scope="session")
def _baza_pelna(tmp_path_factory):
    p = tmp_path_factory.mktemp("db") / "pelna.db"
    c = baza.inicjalizuj(p, z_formatkami=True)
    c.close()
    return p


@pytest.fixture
def conn(_baza_pelna, tmp_path):
    """Pełna baza (z predykcją i formatkami) – kopia na każdy test."""
    import shutil
    p = tmp_path / "kopia.db"
    shutil.copy(_baza_pelna, p)
    c = baza.polacz(p)
    yield c
    c.close()
