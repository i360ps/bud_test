"""Test startu aplikacji: każdy ekran i widok renderuje się bez wyjątku dla każdej roli."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from budzet import konfig

APP = str(Path(__file__).resolve().parent.parent / "app.py")
ROLE = list(konfig.uprawnienia()["stanowiska"])


@pytest.fixture
def baza_testowa(_baza_pelna, tmp_path, monkeypatch):
    p = tmp_path / "app.db"
    shutil.copy(_baza_pelna, p)
    monkeypatch.setattr(konfig, "PLIK_BAZY", p)
    return p


@pytest.mark.parametrize("rola", ROLE)
def test_aplikacja_renderuje_sie(baza_testowa, rola):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    at.sidebar.selectbox[0].select(rola).run()
    assert not at.exception, at.exception
    for strona in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(strona).run()
        assert not at.exception, (rola, strona, at.exception)
        widok = [r for r in at.main.radio if r.label == "Widok"]
        if widok:
            for w in widok[0].options:
                widok[0].set_value(w).run()
                assert not at.exception, (rola, strona, w, at.exception)
                widok = [r for r in at.main.radio if r.label == "Widok"]


def test_klikanie_glowne_sciezki(baza_testowa):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    # Kontroler generuje opis
    at.sidebar.selectbox[0].select("KONTROLER").run()
    at.sidebar.radio[0].set_value("Opis budżetu").run()
    [b for b in at.button if b.label.startswith("Wygeneruj")][0].click().run()
    assert not at.exception, at.exception
    assert any("Wnioski" == s.value for s in at.subheader)
    # Dyrektor Operacyjny (p.o. FCL) przyjmuje podpowiedzi w formatce
    at.sidebar.selectbox[0].select("DO").run()
    at.sidebar.radio[0].set_value("Moje formatki").run()
    [b for b in at.button if b.label == "Przyjmij wszystkie podpowiedzi"][0].click().run()
    assert not at.exception, at.exception
    # Formatka floty w panelu wakatów
    at.sidebar.radio[0].set_value("Wakaty").run()
    assert not at.exception, at.exception
