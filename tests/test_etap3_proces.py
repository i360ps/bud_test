"""Etap 3: statusy, akceptacje, zastępstwa, eskalacje, historia (Z2-K1…K3)."""
import pytest

from budzet import formatki, proces


def _zloz_bez_bledow(conn, fid, kod, data):
    formatki.przyjmij_podpowiedzi(conn, fid)
    for pid in {r[0] for r in conn.execute("SELECT pozycja_id FROM wiersz_formatki WHERE formatka_id=?", (fid,))}:
        formatki.ustaw_uzasadnienie(conn, fid, pid, "test")
    proces.zloz(conn, fid, kod, data)


def test_z2_k1_formatka_fcl_dyrektora_trafia_do_prezesa(conn):
    """Z2-K1: Dyrektor Operacyjny (p.o. kierownika FCL) składa – akceptuje Prezes."""
    _zloz_bez_bledow(conn, "LINIA_FCL", "DO", "2026-11-05")
    a = proces.akceptujacy(conn, "LINIA_FCL", "2026-11-16")
    assert a["kod"] == "PREZES"
    with pytest.raises(PermissionError):
        proces.akceptuj(conn, "LINIA_FCL", "DO", "2026-11-16")
    proces.akceptuj(conn, "LINIA_FCL", "PREZES", "2026-11-16")
    assert conn.execute("SELECT status FROM formatka WHERE formatka_id='LINIA_FCL'").fetchone()[0] == "zaakceptowana"


def test_z2_k2_kontroler_w_zastepstwie_cfo(conn):
    """Z2-K2: w okresie urlopu CFO formatkę MPK akceptuje Kontroler, w historii 'w zastępstwie CFO'."""
    _zloz_bez_bledow(conn, "MPK_300", "DH", "2026-11-03")
    a = proces.akceptujacy(conn, "MPK_300", "2026-11-05")
    assert a["kod"] == "KONTROLER" and a["w_zastepstwie"] == "CFO"
    proces.akceptuj(conn, "MPK_300", "KONTROLER", "2026-11-05")
    h = proces.historia(conn, "MPK_300")
    wpis = h[h.akcja == "akceptacja"].iloc[0]
    assert wpis["w_zastepstwie_kogo"] == "CFO"
    # po urlopie akceptuje znowu CFO
    _zloz_bez_bledow(conn, "MPK_500", "K_IT", "2026-11-12")
    assert proces.akceptujacy(conn, "MPK_500", "2026-11-16")["kod"] == "CFO"


def test_kontroler_nie_akceptuje_wlasnej_formatki_w_zastepstwie(conn):
    _zloz_bez_bledow(conn, "MPK_200", "KONTROLER", "2026-11-03")
    assert proces.akceptujacy(conn, "MPK_200", "2026-11-05")["kod"] == "CFO"


def test_z2_k3_spozniona_formatka_i_na_kogo_czeka(conn):
    proces.aktualizuj_terminy(conn, "2026-11-14")
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id='LINIA_CEL'").fetchone()
    assert f["flaga_spozniona"] == 1 and f["czeka_na"] == "Kierownik Działu Celnego"
    proces.aktualizuj_terminy(conn, "2026-11-10")
    assert conn.execute("SELECT flaga_spozniona FROM formatka WHERE formatka_id='LINIA_CEL'").fetchone()[0] == 0


def test_wakat_lcl_i_osoba_wyznaczona(conn):
    data = "2026-11-02"
    assert proces.jest_wakat(conn, "K_LCL", data)
    assert proces.wypelniajacy(conn, "LINIA_LCL", data) is None
    proces.aktualizuj_terminy(conn, "2026-11-14")
    assert "brak osoby" in conn.execute("SELECT czeka_na FROM formatka WHERE formatka_id='LINIA_LCL'").fetchone()[0]
    with pytest.raises(PermissionError):
        proces.wyznacz_osobe(conn, "LINIA_LCL", "Kierownik Działu Celnego", "CFO")
    proces.wyznacz_osobe(conn, "LINIA_LCL", "Kierownik Działu Celnego", "DO")
    assert proces.wypelniajacy(conn, "LINIA_LCL", data) == "Kierownik Działu Celnego"
    assert "LINIA_LCL" in proces.formatki_do_wypelnienia(conn, "K_CEL", data)


def test_flota_wakat_do_lutego(conn):
    assert proces.jest_wakat(conn, "K_FLOTY", "2026-11-01")
    assert proces.akceptujacy(conn, "FLOTA", "2026-11-16")["kod"] == "DO"


def test_odrzucenie_wymaga_komentarza_i_wraca_do_edycji(conn):
    _zloz_bez_bledow(conn, "MPK_430", "K_CEL", "2026-11-05")
    with pytest.raises(ValueError):
        proces.odrzuc(conn, "MPK_430", "DO", "", "2026-11-16")
    proces.odrzuc(conn, "MPK_430", "DO", "Za wysokie wynagrodzenia", "2026-11-16")
    assert conn.execute("SELECT status FROM formatka WHERE formatka_id='MPK_430'").fetchone()[0] == "odrzucona"
    pid = conn.execute("SELECT pozycja_id FROM wiersz_formatki WHERE formatka_id='MPK_430' LIMIT 1").fetchone()[0]
    formatki.zapisz_wiersz(conn, "MPK_430", pid, "2027-01", kwota=1000)  # edycja znowu możliwa


def test_zlozenie_blokowane_przez_walidacje(conn):
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE mpk=500 AND kategoria='wynagrodzenia z narzutami'").fetchone()[0]
    w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='MPK_500' AND pozycja_id=? AND miesiac='2027-05'",
                     (pid,)).fetchone()
    baza_por = w["podpowiedz_kwota"] or w["wartosc_2026"]
    formatki.zapisz_wiersz(conn, "MPK_500", pid, "2027-05", kwota=baza_por * 3)
    with pytest.raises(ValueError):
        proces.zloz(conn, "MPK_500", "K_IT", "2026-11-05")


def test_eskalacja_po_dwoch_dniach(conn):
    proces.aktualizuj_terminy(conn, "2026-11-15")
    k = conn.execute("SELECT * FROM komunikat WHERE formatka_id='LINIA_CEL'").fetchall()
    odbiorcy = {r["do_kogo"] for r in k}
    assert {"Dyrektor Operacyjny", "Kontroler Finansowy"} <= odbiorcy
    proces.aktualizuj_terminy(conn, "2026-11-13")
    k = conn.execute("SELECT tresc FROM komunikat WHERE formatka_id='LINIA_CEL'").fetchall()
    assert any("Dziś mija termin" in r[0] for r in k)


def test_kurs_ustala_cfo_lub_kontroler_w_zastepstwie(conn):
    with pytest.raises(PermissionError):
        formatki.ustaw_zalozenie(conn, formatki.KURS, 4.0, "KONTROLER", "2026-10-30")
    formatki.ustaw_zalozenie(conn, formatki.KURS, 4.0, "KONTROLER", "2026-11-05")
    formatki.ustaw_zalozenie(conn, formatki.KURS, 3.9, "CFO", "2026-10-30")
    assert formatki.zalozenie(conn, formatki.KURS) == 3.9
