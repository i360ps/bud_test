"""Moduł 1 — schemat budżetu i formatki (reguły Z1-R1…R15)."""
from datetime import datetime

import pandas as pd

from . import baza, konfig

EDYTOWALNE = ("w_przygotowaniu", "odrzucona")
ZRODLA = ("z_modelu", "zmienione_przez_kierownika", "wpisane_recznie", "z_modelu_niesprawdzone")
KURS = "kurs_usd_pln_budzet"


def _teraz() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- założenia (D14–D17)
def nazwa_stawki(pozycja_id: int) -> str:
    return f"stawka_centralna_usd:{pozycja_id}"


def _ostatni_miesiac(conn) -> str:
    return conn.execute("SELECT MAX(miesiac) FROM wolumeny").fetchone()[0]


def zalozenia_domyslne(conn) -> None:
    """D17: kurs z ostatniego miesiąca danych i ostatnia stawka USD z historii, flaga domyslne."""
    par = konfig.parametry()
    m = _ostatni_miesiac(conn)
    w = dict(conn.execute("SELECT * FROM wolumeny WHERE miesiac=?", (m,)).fetchone())
    kurs = w["kurs_usd_pln"]
    _zapisz_zalozenie(conn, KURS, kurs, "domyślne (D17)", domyslne=True)
    for p in conn.execute("SELECT * FROM pozycja WHERE frachtowa_usd=1").fetchall():
        kw = conn.execute("SELECT kwota_pln FROM wykonanie WHERE miesiac=? AND linia=? AND kategoria=? AND typ=?",
                          (m, p["linia"], p["kategoria"], p["typ"])).fetchone()
        wol = w[par["wolumen_linii"][p["linia"]]]
        if kw and wol:
            _zapisz_zalozenie(conn, nazwa_stawki(p["pozycja_id"]), kw[0] / kurs / wol, "domyślne (D17)", domyslne=True)
    conn.commit()


def _zapisz_zalozenie(conn, nazwa, wartosc, ustalil, domyslne=False, miesiac="*"):
    conn.execute("INSERT OR REPLACE INTO zalozenia VALUES (?,?,?,?,?,?)",
                 (nazwa, miesiac, float(wartosc), ustalil, _teraz(), int(domyslne)))


def zalozenie(conn, nazwa: str) -> float | None:
    r = conn.execute("SELECT wartosc FROM zalozenia WHERE nazwa=? AND miesiac='*'", (nazwa,)).fetchone()
    return None if r is None else r[0]


def ustaw_zalozenie(conn, nazwa: str, wartosc: float, stanowisko: str, data: str | None = None) -> None:
    """Kurs i stawki ustala CFO, w zastępstwie Kontroler (Z1-R4, D16)."""
    from . import proces
    if not proces.moze_ustalac_zalozenia(conn, stanowisko, data):
        raise PermissionError("Kurs i stawki frachtu ustala CFO (w jego zastępstwie Kontroler).")
    _zapisz_zalozenie(conn, nazwa, wartosc, proces.osoba(conn, stanowisko), domyslne=False)
    przelicz_frachtowe(conn)
    conn.commit()


def przelicz_frachtowe(conn) -> None:
    """Po zmianie kursu/stawki centralnej: przelicz wiersze frachtowe (Z1-R3)."""
    kurs = zalozenie(conn, KURS)
    wiersze = conn.execute(
        "SELECT w.*, p.pozycja_id AS pid FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
        " WHERE p.frachtowa_usd=1").fetchall()
    for w in wiersze:
        st = zalozenie(conn, nazwa_stawki(w["pid"]))
        podp_kwota = None if (st is None or w["podpowiedz_wolumen"] is None) else w["podpowiedz_wolumen"] * st * kurs
        if w["zrodlo_liczby"] in ("z_modelu", "z_modelu_niesprawdzone"):
            stawka_usd, wolumen = st, w["wolumen"]
        else:
            stawka_usd, wolumen = w["stawka_usd"], w["wolumen"]
        kwota_usd = None if (wolumen is None or stawka_usd is None) else wolumen * stawka_usd
        conn.execute(
            "UPDATE wiersz_formatki SET podpowiedz_stawka=?, podpowiedz_kwota=?, stawka_usd=?, kwota_usd=?,"
            " stawka=?, kwota_pln=? WHERE formatka_id=? AND pozycja_id=? AND miesiac=?",
            (st, podp_kwota, stawka_usd, kwota_usd,
             None if stawka_usd is None else stawka_usd * kurs,
             None if kwota_usd is None else kwota_usd * kurs,
             w["formatka_id"], w["pozycja_id"], w["miesiac"]))


# ---------------------------------------------------------------- rozesłanie formatek
def _pozycje_formatki(conn, f: dict) -> list:
    if f["typ"] == "linia":
        return conn.execute("SELECT * FROM pozycja WHERE linia=? AND flotowa=0 AND typ IN ('przychod','koszt_bezposredni')"
                            " ORDER BY typ DESC, pozycja_id", (f["linia"],)).fetchall()
    if f["typ"] == "mpk":
        return conn.execute("SELECT * FROM pozycja WHERE mpk=? AND flotowa=0 ORDER BY pozycja_id", (f["mpk"],)).fetchall()
    return conn.execute("SELECT * FROM pozycja WHERE flotowa=1 ORDER BY pozycja_id").fetchall()


def _wartosc_2026(conn, p, miesiac_2027: str) -> float | None:
    """Wartość z tego samego miesiąca 2026: wykonanie (I–IX) albo prognoza (X–XII)."""
    m = "2026" + miesiac_2027[4:]
    if p["mpk"] is not None:
        r = conn.execute("SELECT SUM(kwota_pln) FROM wykonanie WHERE miesiac=? AND mpk=? AND kategoria=?",
                         (m, p["mpk"], p["kategoria"])).fetchone()
    else:
        r = conn.execute("SELECT SUM(kwota_pln) FROM wykonanie WHERE miesiac=? AND linia=? AND kategoria=? AND typ=?",
                         (m, p["linia"], p["kategoria"], p["typ"])).fetchone()
    if r and r[0] is not None:
        return r[0]
    r = conn.execute("SELECT kwota_pln FROM prognoza WHERE pozycja_id=? AND miesiac=? AND wersja_danych='prognoza_2026'",
                     (p["pozycja_id"], m)).fetchone()
    return None if r is None else r[0]


def _podpowiedz(conn, pozycja_id: int, miesiac: str):
    return conn.execute("SELECT * FROM prognoza WHERE pozycja_id=? AND miesiac=? AND wersja_danych='podpowiedz_2027'",
                        (pozycja_id, miesiac)).fetchone()


def rozeslij(conn) -> None:
    """Tworzy formatki w statusie w_przygotowaniu z podpowiedziami (krok 2 procesu)."""
    par, upr = konfig.parametry(), konfig.uprawnienia()
    h = par["harmonogram"]
    kurs = zalozenie(conn, KURS)
    miesiace = konfig.miesiace_budzetu(par)
    conn.execute("DELETE FROM formatka"); conn.execute("DELETE FROM wiersz_formatki")
    conn.execute("DELETE FROM flota_miesiac")
    for fid, f in upr["formatki"].items():
        conn.execute(
            "INSERT INTO formatka (formatka_id, typ_formatki, linia, mpk, stanowisko_wypelnia, stanowisko_akceptuje,"
            " status, termin_zlozenia, termin_akceptacji) VALUES (?,?,?,?,?,?,?,?,?)",
            (fid, f["typ"], f.get("linia"), f.get("mpk"), f["wypelnia"], f["akceptuje"], "w_przygotowaniu",
             h["termin_zlozenia"], h["termin_akceptacji"]))
        for p in _pozycje_formatki(conn, f):
            for m in miesiace:
                podp = None if p["flotowa"] else _podpowiedz(conn, p["pozycja_id"], m)
                w2026 = None if p["flotowa"] else _wartosc_2026(conn, p, m)
                rec = dict(formatka_id=fid, pozycja_id=p["pozycja_id"], miesiac=m, wolumen=None, stawka=None,
                           stawka_usd=None, kwota_usd=None, kwota_pln=None, podpowiedz_kwota=None,
                           podpowiedz_wolumen=None, podpowiedz_stawka=None, metoda=None, blad_mape=None,
                           wartosc_rok_poprzedni=w2026, wartosc_2026=w2026,
                           zrodlo_liczby="wpisane_recznie", uzasadnienie=None)
                if podp is not None:
                    rec.update(podpowiedz_kwota=podp["kwota_pln"], podpowiedz_wolumen=podp["wolumen"],
                               podpowiedz_stawka=podp["stawka"], metoda=podp["metoda"], blad_mape=podp["mape"],
                               wolumen=podp["wolumen"], stawka=podp["stawka"], kwota_pln=podp["kwota_pln"],
                               zrodlo_liczby="z_modelu_niesprawdzone")
                    if p["frachtowa_usd"]:
                        st = zalozenie(conn, nazwa_stawki(p["pozycja_id"]))
                        rec.update(stawka_usd=st, podpowiedz_stawka=st)
                conn.execute(f"INSERT INTO wiersz_formatki ({','.join(rec)}) VALUES ({','.join('?' * len(rec))})",
                             tuple(rec.values()))
        if f["typ"] == "flota":
            _zaloz_flote(conn, fid, par, miesiace)
    przelicz_frachtowe(conn)
    przelicz_transport(conn)
    conn.commit()


def _zaloz_flote(conn, fid: str, par: dict, miesiace: list[str]) -> None:
    zestawy = 0
    for m in miesiace:
        zestawy += par["dostawy_zestawow"].get(int(m[5:]), 0)
        udzial = zestawy / par["zestawy_docelowe"] * par["cel_kursow_wlasnych_proc"] / 100
        conn.execute("INSERT INTO flota_miesiac VALUES (?,?,?,?,?,?,?,?,?)",
                     (fid, m, zestawy, zestawy * par["rata_leasingu"], zestawy * par["przebieg_km_na_zestaw"],
                      None, None, None, udzial))


def ustaw_flote(conn, miesiac: str, liczba_zestawow: int | None = None, udzial: float | None = None,
                liczba_etatow: float | None = None, fid: str = "FLOTA") -> None:
    """Edycja danych floty; rata leasingu zawsze liczona (Z1-R9)."""
    _sprawdz_edycje(conn, fid)
    par = konfig.parametry()
    r = dict(conn.execute("SELECT * FROM flota_miesiac WHERE formatka_id=? AND miesiac=?", (fid, miesiac)).fetchone())
    if liczba_zestawow is not None:
        r["liczba_zestawow"] = liczba_zestawow
    if udzial is not None:
        r["udzial_kursow_wlasnych"] = udzial
    if liczba_etatow is not None:
        r["liczba_etatow"] = liczba_etatow
    conn.execute("UPDATE flota_miesiac SET liczba_zestawow=?, rata_leasingu=?, przebieg_km=?, liczba_etatow=?,"
                 " udzial_kursow_wlasnych=? WHERE formatka_id=? AND miesiac=?",
                 (r["liczba_zestawow"], r["liczba_zestawow"] * par["rata_leasingu"],
                  r["liczba_zestawow"] * par["przebieg_km_na_zestaw"], r["liczba_etatow"],
                  r["udzial_kursow_wlasnych"], fid, miesiac))
    przelicz_transport(conn)
    conn.commit()


def przelicz_transport(conn) -> None:
    """Z1-R11: kursy własne = kursy TRN × udział; podwykonawcy liczeni tylko od kursów obcych (Z3-R7).
    Leasing = liczba zestawów × rata (Z1-R9)."""
    par = konfig.parametry()
    pz = par["pozycja_podwykonawcow"]
    p_podw = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia=? AND kategoria=? AND typ='koszt_bezposredni'",
                          (pz["linia"], pz["kategoria"])).fetchone()
    p_przych = conn.execute("SELECT pozycja_id FROM pozycja WHERE linia='TRN' AND typ='przychod' AND wolumenowa=1"
                            " ORDER BY pozycja_id").fetchone()
    p_leasing = conn.execute("SELECT pozycja_id FROM pozycja WHERE flotowa=1 AND kategoria='leasing zestawów'").fetchone()
    for fm in conn.execute("SELECT * FROM flota_miesiac").fetchall():
        m = fm["miesiac"]
        kursy = None
        if p_przych:
            r = conn.execute("SELECT wolumen FROM wiersz_formatki WHERE formatka_id='LINIA_TRN' AND pozycja_id=? AND miesiac=?",
                             (p_przych[0], m)).fetchone()
            kursy = r[0] if r else None
        wlasne = None if kursy is None else round(kursy * (fm["udzial_kursow_wlasnych"] or 0))
        obce = None if kursy is None else kursy - wlasne
        conn.execute("UPDATE flota_miesiac SET kursy_wlasne=?, kursy_podwykonawcow=? WHERE formatka_id=? AND miesiac=?",
                     (wlasne, obce, fm["formatka_id"], m))
        if p_podw and obce is not None:
            w = conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id='LINIA_TRN' AND pozycja_id=? AND miesiac=?",
                             (p_podw[0], m)).fetchone()
            if w is not None:
                stawka = w["stawka"] if w["stawka"] is not None else w["podpowiedz_stawka"]
                podp = None if w["podpowiedz_stawka"] is None else obce * w["podpowiedz_stawka"]
                kwota = None if stawka is None else obce * stawka
                conn.execute("UPDATE wiersz_formatki SET wolumen=?, podpowiedz_wolumen=?, podpowiedz_kwota=?, kwota_pln=?"
                             " WHERE formatka_id='LINIA_TRN' AND pozycja_id=? AND miesiac=?",
                             (obce, obce, podp, kwota, p_podw[0], m))
        if p_leasing:
            conn.execute("UPDATE wiersz_formatki SET kwota_pln=?, zrodlo_liczby='wpisane_recznie'"
                         " WHERE formatka_id=? AND pozycja_id=? AND miesiac=?",
                         (fm["liczba_zestawow"] * par["rata_leasingu"], fm["formatka_id"], p_leasing[0], m))


# ---------------------------------------------------------------- edycja wierszy
def _sprawdz_edycje(conn, fid: str) -> None:
    st = conn.execute("SELECT status FROM formatka WHERE formatka_id=?", (fid,)).fetchone()[0]
    if st not in EDYTOWALNE:
        raise PermissionError(f"Formatki w statusie '{st}' nie można edytować.")


def zapisz_wiersz(conn, fid: str, pozycja_id: int, miesiac: str, wolumen: float | None = None,
                  stawka: float | None = None, kwota: float | None = None, uzasadnienie: str | None = None) -> None:
    """Zapis wiersza. Pozycje wolumenowe: kwota = wolumen × stawka (frachtowe: stawka w USD × kurs)."""
    _sprawdz_edycje(conn, fid)
    w = dict(conn.execute("SELECT * FROM wiersz_formatki WHERE formatka_id=? AND pozycja_id=? AND miesiac=?",
                          (fid, pozycja_id, miesiac)).fetchone())
    p = conn.execute("SELECT * FROM pozycja WHERE pozycja_id=?", (pozycja_id,)).fetchone()
    if p["flotowa"] and p["kategoria"] == "leasing zestawów":
        raise PermissionError("Rata leasingu jest liczona z liczby zestawów (Z1-R9).")
    if wolumen is not None:
        w["wolumen"] = wolumen
    if p["wolumenowa"] and w["wolumen"] is not None:
        if p["frachtowa_usd"]:
            if stawka is not None:
                w["stawka_usd"] = stawka
            kurs = zalozenie(conn, KURS)
            if w["stawka_usd"] is not None:
                w["kwota_usd"] = w["wolumen"] * w["stawka_usd"]
                w["stawka"] = w["stawka_usd"] * kurs
                w["kwota_pln"] = w["kwota_usd"] * kurs
        else:
            if stawka is not None:
                w["stawka"] = stawka
            if w["stawka"] is not None:
                w["kwota_pln"] = w["wolumen"] * w["stawka"]
    elif kwota is not None:
        w["kwota_pln"] = kwota
    if uzasadnienie is not None:
        w["uzasadnienie"] = uzasadnienie or None
    if w["podpowiedz_kwota"] is None:
        w["zrodlo_liczby"] = "wpisane_recznie"
    elif w["kwota_pln"] is not None and abs(w["kwota_pln"] - w["podpowiedz_kwota"]) < 0.5:
        w["zrodlo_liczby"] = "z_modelu"
    else:
        w["zrodlo_liczby"] = "zmienione_przez_kierownika"
    cols = [c for c in w if c not in ("formatka_id", "pozycja_id", "miesiac")]
    conn.execute(f"UPDATE wiersz_formatki SET {', '.join(c + '=?' for c in cols)}"
                 " WHERE formatka_id=? AND pozycja_id=? AND miesiac=?",
                 (*[w[c] for c in cols], fid, pozycja_id, miesiac))
    if fid == "LINIA_TRN" and p["wolumenowa"]:
        przelicz_transport(conn)
    conn.commit()


def ustaw_uzasadnienie(conn, fid: str, pozycja_id: int, tekst: str) -> None:
    """Uzasadnienie dla pozycji (wszystkie miesiące)."""
    _sprawdz_edycje(conn, fid)
    conn.execute("UPDATE wiersz_formatki SET uzasadnienie=? WHERE formatka_id=? AND pozycja_id=?",
                 (tekst or None, fid, pozycja_id))
    conn.commit()


def przyjmij_podpowiedzi(conn, fid: str) -> None:
    """Przyjęcie podpowiedzi: z_modelu_niesprawdzone → z_modelu."""
    _sprawdz_edycje(conn, fid)
    conn.execute("UPDATE wiersz_formatki SET zrodlo_liczby='z_modelu' WHERE formatka_id=? AND zrodlo_liczby='z_modelu_niesprawdzone'",
                 (fid,))
    conn.commit()


# ---------------------------------------------------------------- walidacja i ostrzeżenia
def _przekracza_prog(kwota, baza_por, par) -> bool:
    if kwota is None or baza_por is None:
        return False
    roznica = abs(kwota - baza_por)
    proc = roznica / abs(baza_por) * 100 if baza_por else float("inf")
    return proc > par["prog_uzasadnienia_proc"] and roznica > par["prog_uzasadnienia_kwota"]


def bledy_walidacji(conn, fid: str) -> list[str]:
    """Z1-R5: odchylenie powyżej progu (% i kwota łącznie) bez uzasadnienia blokuje złożenie.
    Baza porównania: podpowiedź, a gdy jej brak — wartość 2026 (D19; patrz LUKI)."""
    par = konfig.parametry()
    bledy = []
    for w in conn.execute("SELECT w.*, p.kategoria FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                          " WHERE formatka_id=?", (fid,)).fetchall():
        baza_por = w["podpowiedz_kwota"] if w["podpowiedz_kwota"] is not None else w["wartosc_2026"]
        if _przekracza_prog(w["kwota_pln"], baza_por, par) and not w["uzasadnienie"]:
            bledy.append(f"{w['kategoria']} {w['miesiac']}: odchylenie powyżej progu bez uzasadnienia")
    return bledy


def ostrzezenia(conn, fid: str) -> list[str]:
    wyn = []
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    if f["linia"] == "TRN" or f["typ_formatki"] == "flota":
        s = conn.execute("SELECT COALESCE(SUM(udzial_kursow_wlasnych),0) FROM flota_miesiac").fetchone()[0]
        if not s:
            wyn.append("Plan transportu na 2027 nie ma kursów własnych (Z1-R12).")
    if f["typ_formatki"] == "flota":
        n = conn.execute("SELECT COUNT(*) FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                         " WHERE formatka_id=? AND kwota_pln IS NULL", (fid,)).fetchone()[0]
        if n:
            wyn.append("Pola floty: brak podpowiedzi — wpisz sam (Z3-R8).")
    if conn.execute("SELECT COUNT(*) FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                    " WHERE formatka_id=? AND p.frachtowa_usd=1", (fid,)).fetchone()[0]:
        if conn.execute("SELECT COUNT(*) FROM zalozenia WHERE domyslne=1").fetchone()[0]:
            wyn.append("Kurs USD/PLN lub stawki frachtu są domyślne — CFO jeszcze ich nie ustalił (D17).")
    return wyn


def _liczba(x, miejsca=0) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def opis_podpowiedzi(conn, fid: str, pozycja_id: int, miesiac: str) -> str | None:
    """Z3-K1/Z3-R9: „X TEU × Y USD/TEU (stawka centralna) × kurs, rok temu Z, błąd ± M%”."""
    w = conn.execute("SELECT w.*, p.frachtowa_usd, p.jednostka, p.wolumenowa FROM wiersz_formatki w"
                     " JOIN pozycja p USING(pozycja_id) WHERE formatka_id=? AND pozycja_id=? AND miesiac=?",
                     (fid, pozycja_id, miesiac)).fetchone()
    if w is None or w["podpowiedz_kwota"] is None:
        return None
    rok_temu = "brak" if w["wartosc_rok_poprzedni"] is None else _liczba(w["wartosc_rok_poprzedni"]) + " zł"
    blad = f"błąd ± {_liczba(w['blad_mape'] or 0, 1)}%"
    if w["wolumenowa"] and w["podpowiedz_wolumen"]:
        j = w["jednostka"] or ""
        if w["frachtowa_usd"]:
            kurs = zalozenie(conn, KURS)
            stawka = f"{_liczba(w['podpowiedz_stawka'], 2)} USD/{j} (stawka centralna) × kurs {_liczba(kurs, 4)}"
        else:
            stawka = f"{_liczba(w['podpowiedz_stawka'], 2)} zł/{j}"
        return (f"{_liczba(w['podpowiedz_wolumen'])} {j} × {stawka} = {_liczba(w['podpowiedz_kwota'])} zł, "
                f"rok temu {rok_temu}, {blad}")
    return f"{_liczba(w['podpowiedz_kwota'])} zł ({w['metoda']}), rok temu {rok_temu}, {blad}"


def wiersze(conn, fid: str) -> pd.DataFrame:
    return baza.df(conn, "SELECT w.*, p.typ, p.kategoria, p.wolumenowa, p.frachtowa_usd, p.jednostka, p.flotowa"
                         " FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id) WHERE formatka_id=?"
                         " ORDER BY p.typ DESC, w.pozycja_id, w.miesiac", (fid,))


def podsumowanie(conn, fid: str) -> dict:
    """Przychód, koszt bezpośredni i marża brutto formatki linii (Z1-K1)."""
    d = wiersze(conn, fid)
    przych = d.loc[d["typ"] == "przychod", "kwota_pln"].sum()
    koszt = d.loc[d["typ"] == "koszt_bezposredni", "kwota_pln"].sum()
    if fid == "LINIA_TRN":
        koszt += baza.df(conn, "SELECT COALESCE(SUM(kwota_pln),0) AS k FROM wiersz_formatki WHERE formatka_id='FLOTA'")["k"][0] \
            if konfig.parametry()["flota_koszt_bezposredni"] else 0
    return {"przychod": przych, "koszt_bezposredni": koszt, "marza_brutto": przych - koszt,
            "koszt_operacyjny": d.loc[d["typ"] == "koszt_operacyjny", "kwota_pln"].sum()}
