"""Etap 2: formatki linii, MPK i floty (Z1-K1…K3)."""
import pytest

from budzet import formatki, konfig


def _poz(conn, linia=None, mpk=None, kategoria=None):
    if linia:
        return conn.execute("SELECT pozycja_id FROM pozycja WHERE linia=? AND kategoria=? AND flotowa=0",
                            (linia, kategoria)).fetchone()[0]
    return conn.execute("SELECT pozycja_id FROM pozycja WHERE mpk=? AND kategoria=?", (mpk, kategoria)).fetchone()[0]


def test_formatki_rozeslane(conn):
    n = conn.execute("SELECT COUNT(*) FROM formatka").fetchone()[0]
    assert n == len(konfig.uprawnienia()["formatki"])
    assert {r[0] for r in conn.execute("SELECT DISTINCT typ_formatki FROM formatka")} == {"linia", "mpk", "flota"}
    assert conn.execute("SELECT COUNT(DISTINCT miesiac) FROM wiersz_formatki").fetchone()[0] == 12


def test_z1_k1_teu_i_stawka_daja_przychod_koszt_marze(conn):
    """Z1-K1: wpisanie TEU i stawki w formatce FCL pokazuje przychód, koszt i marżę brutto."""
    kurs = formatki.zalozenie(conn, formatki.KURS)
    fracht = _poz(conn, "FCL", kategoria="fracht morski")
    koszt = _poz(conn, "FCL", kategoria="fracht armatorski")
    formatki.zapisz_wiersz(conn, "LINIA_FCL", fracht, "2027-01", wolumen=3000, stawka=700)
    formatki.zapisz_wiersz(conn, "LINIA_FCL", koszt, "2027-01", wolumen=3000, stawka=600)
    w = conn.execute("SELECT kwota_usd, kwota_pln FROM wiersz_formatki WHERE formatka_id='LINIA_FCL'"
                     " AND pozycja_id=? AND miesiac='2027-01'", (fracht,)).fetchone()
    assert w["kwota_usd"] == pytest.approx(2_100_000)
    assert w["kwota_pln"] == pytest.approx(2_100_000 * kurs)
    s = formatki.podsumowanie(conn, "LINIA_FCL")
    assert s["marza_brutto"] == pytest.approx(s["przychod"] - s["koszt_bezposredni"])
    # pozycja PLN (nie USD): wolumen × stawka
    opl = _poz(conn, "FCL", kategoria="oplaty lokalne i dokumentacja")
    formatki.zapisz_wiersz(conn, "LINIA_FCL", opl, "2027-02", wolumen=2500, stawka=400)
    assert conn.execute("SELECT kwota_pln FROM wiersz_formatki WHERE formatka_id='LINIA_FCL' AND pozycja_id=?"
                        " AND miesiac='2027-02'", (opl,)).fetchone()[0] == pytest.approx(1_000_000)


def test_z1_k2_transport_bez_kursow_wlasnych_ostrzega(conn):
    assert not any("kursów własnych" in o for o in formatki.ostrzezenia(conn, "LINIA_TRN"))
    for m in konfig.miesiace_budzetu():
        formatki.ustaw_flote(conn, m, udzial=0)
    assert any("kursów własnych" in o for o in formatki.ostrzezenia(conn, "LINIA_TRN"))


def test_z1_k3_odchylenie_bez_uzasadnienia_blokuje(conn):
    poz = _poz(conn, mpk=100, kategoria="wynagrodzenia z narzutami")
    w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='MPK_100' AND pozycja_id=? AND miesiac='2027-01'",
                     (poz,)).fetchone()
    baza_por = w["podpowiedz_kwota"] if w["podpowiedz_kwota"] is not None else w["wartosc_2026"]
    formatki.zapisz_wiersz(conn, "MPK_100", poz, "2027-01", kwota=baza_por * 2)
    assert formatki.bledy_walidacji(conn, "MPK_100")
    formatki.ustaw_uzasadnienie(conn, "MPK_100", poz, "Nowy członek zarządu od stycznia")
    assert not formatki.bledy_walidacji(conn, "MPK_100")


def test_male_odchylenie_nie_wymaga_uzasadnienia(conn):
    poz = _poz(conn, mpk=100, kategoria="samochody sluzbowe")
    w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='MPK_100' AND pozycja_id=? AND miesiac='2027-03'",
                     (poz,)).fetchone()
    baza_por = w["podpowiedz_kwota"] if w["podpowiedz_kwota"] is not None else w["wartosc_2026"]
    formatki.zapisz_wiersz(conn, "MPK_100", poz, "2027-03", kwota=baza_por * 1.5)  # >10%, ale < 50 000 zł
    assert not formatki.bledy_walidacji(conn, "MPK_100")


def test_leasing_liczony_z_zestawow(conn):
    rata = konfig.parametry()["rata_leasingu"]
    r = conn.execute("SELECT w.kwota_pln FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                     " WHERE formatka_id='FLOTA' AND p.kategoria='leasing zestawów' AND miesiac='2027-02'").fetchone()
    assert r[0] == 10 * rata
    with pytest.raises(PermissionError):
        pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE kategoria='leasing zestawów'").fetchone()[0]
        formatki.zapisz_wiersz(conn, "FLOTA", pid, "2027-02", kwota=1)
    formatki.ustaw_flote(conn, "2027-02", liczba_zestawow=8)
    assert conn.execute("SELECT w.kwota_pln FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                        " WHERE formatka_id='FLOTA' AND p.kategoria='leasing zestawów' AND miesiac='2027-02'"
                        ).fetchone()[0] == 8 * rata


def test_udzial_kursow_wlasnych_z_zestawow(conn):
    r = conn.execute("SELECT udzial_kursow_wlasnych FROM flota_miesiac WHERE miesiac='2027-01'").fetchone()[0]
    assert r == pytest.approx(6 / 14 * 0.6)
    assert conn.execute("SELECT udzial_kursow_wlasnych FROM flota_miesiac WHERE miesiac='2027-06'"
                        ).fetchone()[0] == pytest.approx(0.6)
