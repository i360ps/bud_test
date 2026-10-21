"""Etap 6: opis budżetu, kontrola zgodności, obieg Kontroler → CFO (Z5-K1…K3, Z3-K3)."""
import pytest

from budzet import formatki, opis, proces


def _sekcja(conn, nazwa):
    return [s for s in opis.sekcje(conn) if s["sekcja"] == nazwa][0]["tresc"]


def test_struktura_i_limit(conn):
    opis.generuj(conn)
    assert [s["sekcja"] for s in opis.sekcje(conn)] == opis.SEKCJE
    k = opis.kontrola(conn)
    assert k["zgodnosc_liczb"] and k["w_limicie"]


def test_z5_k1_roznica_1_zl_blokuje_wyslanie(conn):
    opis.generuj(conn)
    t = _sekcja(conn, "Koszty operacyjne")
    m = opis.WZOR_KWOTY.search(t)
    v = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
    zmieniony = t.replace(m.group(0), opis.zl(v + 1), 1)
    opis.popraw(conn, "Koszty operacyjne", zmieniony, "KONTROLER")
    with pytest.raises(ValueError):
        opis.wyslij_do_cfo(conn, "KONTROLER")
    opis.popraw(conn, "Koszty operacyjne", t, "KONTROLER")
    opis.wyslij_do_cfo(conn, "KONTROLER")
    assert opis.status(conn) == "poprawiony"


def test_z5_k2_lcl_z_modelu_niezaakceptowana_ostrzezenie(conn):
    opis.generuj(conn)
    o = _sekcja(conn, "Ostrzeżenia")
    assert "LINIA_LCL: niezaakceptowana" in o
    assert "LINIA_LCL: wypełniona z modelu, nikt nie sprawdził" in o


def test_z5_k3_pierwszy_akapit(conn):
    opis.generuj(conn)
    pierwszy = _sekcja(conn, "Wnioski").split("\n\n")[0]
    assert "wynik operacyjny" in pierwszy and "kursie USD/PLN" in pierwszy
    assert "stawkach frachtu" in pierwszy and "USD/TEU" in pierwszy and "TEU" in pierwszy and "wolumenach" in pierwszy


def test_z3_k3_decyzja_kierownika_w_opisie(conn):
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia='CEL' AND kategoria='zgloszenia celne' AND typ='przychod'").fetchone()[0]
    w = conn.execute("SELECT wolumen FROM wiersz_formatki WHERE formatka_id='LINIA_CEL' AND pozycja_id=? AND miesiac='2027-04'",
                     (pid,)).fetchone()[0]
    formatki.zapisz_wiersz(conn, "LINIA_CEL", pid, "2027-04", wolumen=w * 2)
    formatki.ustaw_uzasadnienie(conn, "LINIA_CEL", pid, "Nowy klient od kwietnia")
    opis.generuj(conn)
    linie = _sekcja(conn, "Linie biznesowe")
    cel = [l for l in linie.split("\n") if l.startswith("CEL")][0]
    assert "(decyzja kierownika)" in cel and "Nowy klient od kwietnia" in cel
    fcl = [l for l in linie.split("\n") if l.startswith("FCL")][0]
    assert "(prognoza, ±" in fcl


def test_limit_slow_blokuje(conn):
    opis.generuj(conn)
    opis.popraw(conn, "Wnioski", _sekcja(conn, "Wnioski") + " słowo" * 1000, "KONTROLER")
    with pytest.raises(ValueError):
        opis.wyslij_do_cfo(conn, "KONTROLER")


def test_obieg_zatwierdzenia(conn):
    opis.generuj(conn)
    with pytest.raises(PermissionError):
        opis.popraw(conn, "Wnioski", "x", "CFO")
    opis.wyslij_do_cfo(conn, "KONTROLER")
    # urlop CFO: zatwierdza Prezes, nie Kontroler (D7, D13)
    assert proces.zatwierdzajacy_opis(conn, "2026-11-05") == "PREZES"
    with pytest.raises(PermissionError):
        opis.zatwierdz(conn, "KONTROLER", "2026-11-05")
    opis.zatwierdz(conn, "CFO", "2026-11-25")
    assert opis.status(conn) == "zatwierdzony"


def test_zmiana_danych_po_wygenerowaniu_wykrywana(conn):
    opis.generuj(conn)
    pid = conn.execute("SELECT pozycja_id FROM pozycja WHERE mpk=300 AND kategoria='marketing i podroze'").fetchone()[0]
    formatki.zapisz_wiersz(conn, "MPK_300", pid, "2027-06", kwota=123456.0)
    assert opis.niezgodne_kwoty(conn)
