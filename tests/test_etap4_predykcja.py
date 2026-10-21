"""Etap 4: test wsteczny, wybór metody, podpowiedzi, prognoza 2026 (Z3-K1…K3)."""
import pytest

from budzet import formatki, konfig, predykcja


def test_punkt_kontrolny_fcl(conn):
    """Sekcja 6: przychody FCL razem — powtórka 26,7%, średnia 29,1%."""
    w = predykcja.test_linii(conn, "FCL")
    assert round(w["powtorka_roku"], 1) == 26.7
    assert round(w["srednia_12m"], 1) == 29.1


def test_metoda_wybrana_wg_najnizszego_mape(conn):
    t = predykcja.wyniki_testu(conn)
    for r in t.itertuples():
        mapy = {m: getattr(r, m) for m in predykcja.METODY if hasattr(r, m) and getattr(r, m) == getattr(r, m)}
        if r.kategoria == "IT i licencje":
            assert r.wybrana == "powtorka_roku"  # Z3-R4
        else:
            assert r.wybrana == min(mapy, key=mapy.get)


def test_flota_bez_podpowiedzi(conn):
    assert conn.execute("SELECT COUNT(*) FROM prognoza JOIN pozycja USING(pozycja_id) WHERE flotowa=1").fetchone()[0] == 0
    assert any("brak podpowiedzi" in o for o in formatki.ostrzezenia(conn, "FLOTA"))


def test_prognoza_2026_x_xii(conn):
    m = {r[0] for r in conn.execute("SELECT DISTINCT miesiac FROM prognoza WHERE wersja_danych='prognoza_2026'")}
    assert m == {"2026-10", "2026-11", "2026-12"}


def test_z3_k1_tekst_podpowiedzi_fcl(conn):
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia='FCL' AND kategoria='fracht morski'").fetchone()[0]
    t = formatki.opis_podpowiedzi(conn, "LINIA_FCL", pid, "2027-03")
    assert "TEU ×" in t and "USD/TEU (stawka centralna) × kurs" in t and "rok temu" in t and "błąd ±" in t


def test_podpowiedz_frachtowa_ze_stawki_centralnej(conn):
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia='FCL' AND kategoria='fracht morski'").fetchone()[0]
    w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='LINIA_FCL' AND pozycja_id=? AND miesiac='2027-03'",
                     (pid,)).fetchone()
    kurs = formatki.zalozenie(conn, formatki.KURS)
    st = formatki.zalozenie(conn, formatki.nazwa_stawki(pid))
    assert w["kwota_pln"] == pytest.approx(w["podpowiedz_wolumen"] * st * kurs)
    formatki.ustaw_zalozenie(conn, formatki.KURS, kurs * 1.1, "CFO", "2026-10-30")
    w2 = conn.execute("SELECT kwota_pln FROM wiersz_formatki WHERE formatka_id='LINIA_FCL' AND pozycja_id=? AND miesiac='2027-03'",
                      (pid,)).fetchone()
    assert w2[0] == pytest.approx(w["kwota_pln"] * 1.1)


def _koszt_podwykonawcow(conn):
    return conn.execute("SELECT SUM(w.kwota_pln) FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                        " WHERE formatka_id='LINIA_TRN' AND p.kategoria='podwykonawcy transportowi'").fetchone()[0]


def test_z3_k2_wiecej_kursow_wlasnych_mniej_podwykonawcow(conn):
    przed = _koszt_podwykonawcow(conn)
    for m in konfig.miesiace_budzetu():
        formatki.ustaw_flote(conn, m, udzial=0.8)
    assert _koszt_podwykonawcow(conn) < przed
    for m in konfig.miesiace_budzetu():
        formatki.ustaw_flote(conn, m, udzial=0.0)
    assert _koszt_podwykonawcow(conn) > przed


def test_z3_k3_kwota_duzo_wyzsza_wymaga_uzasadnienia(conn):
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia='CEL' AND kategoria='zgloszenia celne' AND typ='przychod'").fetchone()[0]
    w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='LINIA_CEL' AND pozycja_id=? AND miesiac='2027-04'",
                     (pid,)).fetchone()
    formatki.zapisz_wiersz(conn, "LINIA_CEL", pid, "2027-04", wolumen=w["wolumen"] * 2)
    r = conn.execute("SELECT zrodlo_liczby FROM wiersz_formatki WHERE formatka_id='LINIA_CEL' AND pozycja_id=? AND miesiac='2027-04'",
                     (pid,)).fetchone()[0]
    assert r == "zmienione_przez_kierownika"
    assert formatki.bledy_walidacji(conn, "LINIA_CEL")


def test_znaczniki_zrodla_po_rozeslaniu(conn):
    z = {r[0] for r in conn.execute("SELECT DISTINCT zrodlo_liczby FROM wiersz_formatki")}
    assert z <= set(formatki.ZRODLA)
    assert "z_modelu_niesprawdzone" in z
