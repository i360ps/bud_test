"""Etap 1: dane i konfiguracja."""
from budzet import baza, konfig


def test_konfiguracja_wczytuje_sie():
    p, u = konfig.parametry(), konfig.uprawnienia()
    assert p["rok_budzetu"] == 2027
    assert "formatki" in u and "stanowiska" in u


def test_import_wierszy(conn_dane):
    assert conn_dane.execute("SELECT COUNT(*) FROM wykonanie").fetchone()[0] == 1605
    assert conn_dane.execute("SELECT COUNT(*) FROM wolumeny").fetchone()[0] == 45


def test_przychody_2025_zgodne_z_danymi(conn_dane):
    s = baza.sumy_roczne(conn_dane)
    # Specyfikacja: 166 470 tys. zł; dane dają 166 468,9 tys. (zaokrąglenie w specyfikacji) – patrz LUKI.
    assert round(s.loc["przychod", "2025"]) == 166469
    assert abs(s.loc["przychod", "2025"] - 166470) < 1.5


def test_brak_lcl_sierpien_2024(conn_dane):
    r = conn_dane.execute("SELECT lcl_m3 FROM wolumeny WHERE miesiac='2024-08'").fetchone()
    assert r[0] is None


def test_anomalie_oznaczone(conn_dane):
    n = conn_dane.execute("SELECT COUNT(*) FROM wykonanie WHERE wylaczone_z_uczenia=1").fetchone()[0]
    assert n == 3


def test_wszystkie_tabele_z_sekcji_3(conn_dane):
    tabele = {r[0] for r in conn_dane.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ["stanowisko", "nieobecnosc", "zastepstwo", "mpk", "pozycja", "formatka", "wiersz_formatki",
              "flota_miesiac", "historia", "zalozenia", "wykonanie", "wolumeny", "test_wsteczny",
              "prognoza", "budzet_2026", "opis"]:
        assert t in tabele


def test_pozycje_floty_i_mpk_450(conn_dane):
    n = conn_dane.execute("SELECT COUNT(*) FROM pozycja WHERE flotowa=1 AND mpk=450").fetchone()[0]
    assert n == 7
    assert conn_dane.execute("SELECT linia FROM mpk WHERE mpk=450").fetchone()[0] == "TRN"
