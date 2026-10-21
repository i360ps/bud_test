"""Moduł 5 — opis budżetu (sekcja 8, Z5-R1…R9). Szablon regułowy bez modelu językowego (D31).
Wszystkie liczby pochodzą z tabel modułu 4 i z tabeli zalozenia (Z5-R3)."""
import json
import re
from datetime import datetime

from . import agregacja as ag
from . import baza, formatki as fm, konfig, proces

SEKCJE = ["Wnioski", "Założenia", "Linie biznesowe", "Flota", "Koszty operacyjne", "Ryzyka", "Ostrzeżenia"]
STATUSY = ("projekt", "poprawiony", "zatwierdzony")
WZOR_KWOTY = re.compile(r"(-?\d{1,3}(?:[  ]\d{3})+|-?\d+) zł")


def zl(x) -> str:
    return f"{round(x):,} zł".replace(",", " ")


def proc(x, miejsca=1) -> str:
    return f"{x:.{miejsca}f}%".replace(".", ",")


def liczba(x, miejsca=0) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


# ---------------------------------------------------------------- źródło liczb
def _tabele(conn) -> dict:
    d = ag.budzet_2027(conn)
    return {"budzet": d, "zest": ag.zestawienie(d), "linie": ag.wyniki_linii(d), "mpk": ag.koszty_mpk(d),
            "scen": ag.scenariusze(d), "transport": ag.wskazniki_transportu(conn, d),
            "przew_2026": ag.zestawienie(ag.przewidywane_2026(conn)),
            "wyk_2025": ag.zestawienie(ag.wykonanie(conn, "2025-01", "2025-12")),
            "akcept": ag.zestawienie(d[d["status"] == "zaakceptowana"])}


def dozwolone_kwoty(conn, t: dict | None = None) -> set[int]:
    """Wszystkie kwoty (zł, zaokrąglone) obecne w tabelach — opis nie może zawierać innych (Z5-R3)."""
    t = t or _tabele(conn)
    wart = list(t["zest"].values()) + list(t["przew_2026"].values()) + list(t["wyk_2025"].values()) \
        + list(t["akcept"].values()) + [v for v in t["transport"].values() if v is not None]
    wart += t["linie"].select_dtypes("number").to_numpy().ravel().tolist()
    wart += t["mpk"]["kwota_pln"].tolist()
    wart += t["scen"].select_dtypes("number").to_numpy().ravel().tolist()
    wart += [t["zest"]["wynik"] - t["przew_2026"]["wynik"], t["zest"]["marza_brutto"] - t["przew_2026"]["marza_brutto"]]
    t26 = _transport_2026(conn)
    wart += [v for v in t26.values() if v is not None]
    # Ryzyka podajemy słownie („obniża o X zł”), więc dopuszczamy też wartość bezwzględną.
    return {round(v) for v in wart} | {round(abs(v)) for v in wart}


def _transport_2026(conn) -> dict:
    w = ag.wykonanie(conn, "2026-01", "2026-09")
    podw = w[(w["linia"] == "TRN") & (w["kategoria"] == "podwykonawcy transportowi")]["kwota_pln"].sum()
    kursy = baza.df(conn, "SELECT SUM(kursy_transport) AS k FROM wolumeny WHERE miesiac BETWEEN '2026-01' AND '2026-09'")["k"][0]
    return {"koszt_podwykonawcow_2026_I_IX": podw, "koszt_na_kurs_2026_I_IX": podw / kursy if kursy else None}


# ---------------------------------------------------------------- generowanie projektu
def _dopisek_linii(d, linia, typ) -> str:
    """Z5-R5: (prognoza, ± X%) albo (decyzja kierownika) z uzasadnieniem."""
    dl = d[(d["linia"] == linia) & (d["typ"] == typ)]
    if (dl["zrodlo_liczby"] == "zmienione_przez_kierownika").any():
        return "(decyzja kierownika)"
    if (dl["zrodlo_liczby"] == "wpisane_recznie").all():
        return "(wpisane ręcznie)"
    return "(prognoza, ± {})"


def _mape_linii(conn, linia, typ) -> float:
    r = conn.execute("SELECT AVG(w.blad_mape) FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id)"
                     " JOIN formatka f USING(formatka_id) WHERE f.linia=? AND p.typ=? AND w.blad_mape IS NOT NULL",
                     (linia, typ)).fetchone()[0]
    return r or 0.0


def _uzasadnienia(conn, linia) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT w.uzasadnienie FROM wiersz_formatki w JOIN formatka f USING(formatka_id)"
        " WHERE f.linia=? AND w.zrodlo_liczby='zmienione_przez_kierownika' AND w.uzasadnienie IS NOT NULL", (linia,))]


def ostrzezenia(conn, d) -> list[str]:
    """Sekcja 8: formatka niezaakceptowana; założenie domyślne; wiersze z_modelu_niesprawdzone."""
    wyn = []
    for fid in ag.niezaakceptowane(d):
        st = conn.execute("SELECT status FROM formatka WHERE formatka_id=?", (fid,)).fetchone()[0]
        wyn.append(f"Formatka {fid}: niezaakceptowana (status: {st}).")
    if conn.execute("SELECT COUNT(*) FROM zalozenia WHERE domyslne=1").fetchone()[0]:
        wyn.append("Kurs USD/PLN lub stawki frachtu przyjęto domyślnie — nie ustalił ich CFO.")
    for r in conn.execute("SELECT formatka_id, COUNT(*) FROM wiersz_formatki WHERE zrodlo_liczby='z_modelu_niesprawdzone'"
                          " GROUP BY formatka_id ORDER BY formatka_id"):
        wyn.append(f"Formatka {r[0]}: wypełniona z modelu, nikt nie sprawdził ({r[1]} wierszy).")
    return wyn


def generuj(conn) -> int:
    """Tworzy nowy projekt opisu (status: projekt). Zwraca numer wersji."""
    par = konfig.parametry()
    t = _tabele(conn)
    d, z = t["budzet"], t["zest"]
    kurs = fm.zalozenie(conn, fm.KURS)
    stawki = conn.execute("SELECT p.linia, p.typ, p.kategoria, z.wartosc FROM zalozenia z JOIN pozycja p"
                          " ON z.nazwa = 'stawka_centralna_usd:' || p.pozycja_id WHERE p.typ='przychod'").fetchall()
    wol = ag.wolumeny_2027(conn).groupby(["linia", "jednostka"])["wolumen"].sum().reset_index()
    stawki_txt = ", ".join(f"{s['linia']} {liczba(s['wartosc'], 0)} USD/{par['jednostka_linii'][s['linia']]}" for s in stawki)
    wol_txt = ", ".join(f"{r.linia} {liczba(r.wolumen)} {r.jednostka}" for r in wol.itertuples())

    s = {}
    s["Wnioski"] = (
        f"Budżet 2027 zakłada wynik operacyjny {zl(z['wynik'])} i marżę brutto {zl(z['marza_brutto'])} "
        f"({proc(z['marza_proc'])} przychodów) przy kursie USD/PLN {liczba(kurs, 4)}, stawkach frachtu {stawki_txt} "
        f"oraz wolumenach {wol_txt}. Wobec przewidywanego wykonania 2026 (szacunek) wynik zmienia się o "
        f"{zl(z['wynik'] - t['przew_2026']['wynik'])}, a marża brutto o {zl(z['marza_brutto'] - t['przew_2026']['marza_brutto'])}."
        "\n\n[Wnioski Kontrolera — do uzupełnienia]")
    sc = t["scen"]
    s["Założenia"] = (
        f"Kurs USD/PLN: {liczba(kurs, 4)}; stawki frachtu: {stawki_txt}; wolumeny: {wol_txt}. "
        + " ".join(f"Zmiana {r.scenariusz} o +{par['scenariusz_proc']}% zmienia wynik o {zl(getattr(r, '_2'))}."
                   for r in sc.itertuples()))
    linie_txt = []
    for r in t["linie"].itertuples():
        dop = _dopisek_linii(d, r.linia, "przychod").format(proc(_mape_linii(conn, r.linia, "przychod")))
        tekst = (f"{r.linia}: przychody {zl(r.przychody)} {dop}, marża brutto {zl(r.marza_brutto)} "
                 f"({proc(r.marza_proc)}), wynik linii {zl(r.wynik_linii)}, po podziale kosztów wspólnych "
                 f"{zl(r.wynik_po_podziale)}.")
        uz = _uzasadnienia(conn, r.linia)
        if uz:
            tekst += " Uzasadnienie kierownika: " + "; ".join(uz) + "."
        linie_txt.append(tekst)
    s["Linie biznesowe"] = "\n".join(linie_txt)
    tr, t26 = t["transport"], _transport_2026(conn)
    s["Flota"] = (
        f"Od 2027 r. własna flota: {par['zestawy_docelowe']} zestawów w leasingu, docelowo "
        f"{par['cel_kursow_wlasnych_proc']}% kursów własnych; zastępuje część podwykonawców, dlatego koszty transportu "
        f"zmieniają strukturę, a marża TRN nie jest wprost porównywalna z 2026 r. Łączny koszt kursów 2027: "
        f"{zl(tr['koszt_kursow_lacznie'])}; koszt na kurs własny "
        f"{zl(tr['koszt_na_kurs_wlasny']) if tr['koszt_na_kurs_wlasny'] else 'brak danych'}, obcy "
        f"{zl(tr['koszt_na_kurs_obcy']) if tr['koszt_na_kurs_obcy'] else 'brak danych'}; w I–IX 2026 koszt na kurs "
        f"(podwykonawcy) wynosił {zl(t26['koszt_na_kurs_2026_I_IX'])}.")
    s["Koszty operacyjne"] = (
        f"Koszty operacyjne razem: {zl(z['koszty_operacyjne'])}. "
        + "; ".join(f"MPK {r.mpk} {r.nazwa}: {zl(r.kwota_pln)}" for r in t["mpk"].itertuples()) + ".")
    s["Ryzyka"] = " ".join(
        f"Spadek o {par['scenariusz_proc']}% — {r.scenariusz}: wynik niższy o {zl(-getattr(r, '_3'))}."
        if getattr(r, "_3") < 0 else
        f"Spadek o {par['scenariusz_proc']}% — {r.scenariusz}: wynik zmienia się o {zl(getattr(r, '_3'))}."
        for r in sc.itertuples())
    ost = ostrzezenia(conn, d)
    if ost:
        ost.append(f"Wynik tylko z formatek zaakceptowanych: {zl(t['akcept']['wynik'])}.")
    s["Ostrzeżenia"] = "\n".join(ost) if ost else "Brak ostrzeżeń."

    nowa = (conn.execute("SELECT MAX(wersja) FROM opis").fetchone()[0] or 0) + 1
    for i, nazwa in enumerate(SEKCJE):
        conn.execute("INSERT INTO opis (wersja, sekcja, kolejnosc, tresc, status_opisu, zgodnosc_liczb, lista_ostrzezen)"
                     " VALUES (?,?,?,?,?,?,?)", (nowa, nazwa, i, s[nazwa], "projekt", None,
                                                json.dumps(ost, ensure_ascii=False)))
    conn.commit()
    return nowa


# ---------------------------------------------------------------- odczyt, edycja, kontrole, obieg
def ostatnia_wersja(conn) -> int | None:
    return conn.execute("SELECT MAX(wersja) FROM opis").fetchone()[0]


def sekcje(conn, wersja: int | None = None) -> list:
    wersja = wersja or ostatnia_wersja(conn)
    return conn.execute("SELECT * FROM opis WHERE wersja=? ORDER BY kolejnosc", (wersja,)).fetchall()


def tekst(conn, wersja=None) -> str:
    return "\n\n".join(f"{r['sekcja']}\n{r['tresc']}" for r in sekcje(conn, wersja))


def status(conn, wersja=None) -> str | None:
    s = sekcje(conn, wersja)
    return s[0]["status_opisu"] if s else None


def popraw(conn, sekcja: str, tresc: str, kod: str, wersja=None) -> None:
    """Kontroler poprawia opis i pisze wnioski (Z2-R4, D32)."""
    if kod not in konfig.uprawnienia()["uprawnienia"]["poprawia_opis"]:
        raise PermissionError("Opis poprawia Kontroler Finansowy.")
    wersja = wersja or ostatnia_wersja(conn)
    if status(conn, wersja) == "zatwierdzony":
        raise PermissionError("Opis jest zatwierdzony.")
    conn.execute("UPDATE opis SET tresc=?, status_opisu='projekt', zgodnosc_liczb=NULL WHERE wersja=? AND sekcja=?",
                 (tresc, wersja, sekcja))
    conn.commit()


def liczba_slow(conn, wersja=None) -> int:
    return len(tekst(conn, wersja).split())


def niezgodne_kwoty(conn, wersja=None) -> list[str]:
    """Kwoty w opisie, których nie ma w tabelach (różnica choćby o 1 zł)."""
    dozw = dozwolone_kwoty(conn)
    zle = []
    for m in WZOR_KWOTY.finditer(tekst(conn, wersja)):
        v = int(re.sub(r"[  ]", "", m.group(1)))
        if v not in dozw:
            zle.append(m.group(0))
    return zle


def kontrola(conn, wersja=None) -> dict:
    par = konfig.parametry()
    zle = niezgodne_kwoty(conn, wersja)
    slowa = liczba_slow(conn, wersja)
    return {"zgodnosc_liczb": not zle, "niezgodne": zle, "slowa": slowa, "limit": par["limit_slow_opisu"],
            "w_limicie": slowa <= par["limit_slow_opisu"]}


def wyslij_do_cfo(conn, kod: str, wersja=None) -> None:
    """Kontrola zgodności liczb i limitu słów przed wysłaniem (Z5-R3, Z5-K1)."""
    if kod not in konfig.uprawnienia()["uprawnienia"]["poprawia_opis"]:
        raise PermissionError("Opis do CFO wysyła Kontroler.")
    wersja = wersja or ostatnia_wersja(conn)
    k = kontrola(conn, wersja)
    conn.execute("UPDATE opis SET zgodnosc_liczb=? WHERE wersja=?", (int(k["zgodnosc_liczb"]), wersja))
    conn.commit()
    if not k["zgodnosc_liczb"]:
        raise ValueError("Liczby w opisie nie zgadzają się z tabelami: " + ", ".join(k["niezgodne"][:5]))
    if not k["w_limicie"]:
        raise ValueError(f"Opis ma {k['slowa']} słów, limit {k['limit']}.")
    conn.execute("UPDATE opis SET status_opisu='poprawiony' WHERE wersja=?", (wersja,))
    conn.commit()


def zatwierdz(conn, kod: str, data: str | None = None, wersja=None) -> None:
    """Zatwierdza CFO, w zastępstwie Prezes (D13); Kontroler nie zatwierdza własnego opisu (D7)."""
    wersja = wersja or ostatnia_wersja(conn)
    if status(conn, wersja) != "poprawiony":
        raise PermissionError("Zatwierdzić można opis poprawiony i wysłany przez Kontrolera.")
    kto = proces.zatwierdzajacy_opis(conn, data)
    if kod != kto:
        raise PermissionError(f"Opis zatwierdza: {proces.osoba(conn, kto)}.")
    if niezgodne_kwoty(conn, wersja):
        raise ValueError("Liczby w opisie nie zgadzają się już z tabelami — wygeneruj opis ponownie.")
    conn.execute("UPDATE opis SET status_opisu='zatwierdzony', zatwierdzil=?, data_zatwierdzenia=? WHERE wersja=?",
                 (proces.osoba(conn, kod), datetime.now().isoformat(timespec="seconds"), wersja))
    conn.commit()
