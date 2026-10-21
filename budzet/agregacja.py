"""Moduł 4 — agregacja budżetu (Z4-R1…R8). Jedno źródło liczb dla dashboardów i opisu (Z4-R2)."""
import pandas as pd

from . import baza, konfig

LINIE = ["FCL", "LCL", "CEL", "TRN"]
KOLUMNY = ["miesiac", "typ", "linia", "mpk", "kategoria", "kwota_pln", "zrodlo_liczby", "status", "formatka_id",
           "pozycja_id", "wolumenowa", "frachtowa_usd", "flotowa", "szacunek"]


def _mapuj_linie(d: pd.DataFrame) -> pd.DataFrame:
    """Koszty operacyjne MPK → linia (D22); MPK wspólne zostają bez linii."""
    par = konfig.parametry()
    mapa = {int(k): v["linia"] for k, v in par["mpk"].items()}
    brak = d["linia"].isna() & d["mpk"].notna()
    d.loc[brak, "linia"] = d.loc[brak, "mpk"].astype(int).map(mapa)
    return d


def budzet_2027(conn, tylko_zaakceptowane: bool = False) -> pd.DataFrame:
    """Wszystkie wiersze formatek 2027 z linią, MPK, statusem i znacznikiem źródła (Z4-R1, Z4-R4)."""
    d = baza.df(conn, """
        SELECT w.miesiac, p.typ, COALESCE(f.linia, p.linia) AS linia, COALESCE(p.mpk, f.mpk) AS mpk, p.kategoria,
               w.kwota_pln, w.zrodlo_liczby, f.status, f.formatka_id, p.pozycja_id, p.wolumenowa, p.frachtowa_usd,
               p.flotowa, 0 AS szacunek
        FROM wiersz_formatki w JOIN pozycja p USING(pozycja_id) JOIN formatka f USING(formatka_id)""")
    d.loc[d["typ"] == "koszt_operacyjny", "linia"] = None
    d.loc[d["typ"] != "koszt_operacyjny", "mpk"] = d.loc[d["typ"] != "koszt_operacyjny", "mpk"].where(d["flotowa"] == 1)
    d = _mapuj_linie(d)
    d["kwota_pln"] = d["kwota_pln"].fillna(0.0)
    if tylko_zaakceptowane:
        d = d[d["status"] == "zaakceptowana"]
    return d[KOLUMNY]


def wykonanie(conn, od: str, do: str) -> pd.DataFrame:
    d = baza.df(conn, """
        SELECT w.miesiac, w.typ, w.linia, w.mpk, w.kategoria, w.kwota_pln, NULL AS zrodlo_liczby,
               'wykonanie' AS status, NULL AS formatka_id, NULL AS pozycja_id, 0 AS wolumenowa, 0 AS frachtowa_usd,
               0 AS flotowa, 0 AS szacunek
        FROM wykonanie w WHERE miesiac BETWEEN ? AND ?""", (od, do))
    d["linia"] = d["linia"].replace("", None)
    return _mapuj_linie(d)[KOLUMNY]


def przewidywane_2026(conn) -> pd.DataFrame:
    """Z4-R8: wykonanie I–IX 2026 + prognoza X–XII z etykietą „szacunek” (D27)."""
    w = wykonanie(conn, "2026-01", "2026-09")
    p = baza.df(conn, """
        SELECT r.miesiac, p.typ, p.linia, p.mpk, p.kategoria, r.kwota_pln, 'z_modelu' AS zrodlo_liczby,
               'szacunek' AS status, NULL AS formatka_id, p.pozycja_id, p.wolumenowa, p.frachtowa_usd, 0 AS flotowa,
               1 AS szacunek
        FROM prognoza r JOIN pozycja p USING(pozycja_id) WHERE r.wersja_danych='prognoza_2026'""")
    p.loc[p["typ"] == "koszt_operacyjny", "linia"] = None
    p.loc[p["typ"] != "koszt_operacyjny", "mpk"] = None
    return pd.concat([w, _mapuj_linie(p)[KOLUMNY]], ignore_index=True)


def wersja(conn, nazwa: str, tylko_zaakceptowane: bool = False) -> pd.DataFrame:
    if nazwa == "budżet 2027":
        return budzet_2027(conn, tylko_zaakceptowane)
    if nazwa == "przewidywane wykonanie 2026 (szacunek)":
        return przewidywane_2026(conn)
    if nazwa == "wykonanie 2026 I–IX":
        return wykonanie(conn, "2026-01", "2026-09")
    rok = nazwa[-4:]
    return wykonanie(conn, f"{rok}-01", f"{rok}-12")


WERSJE = ["budżet 2027", "przewidywane wykonanie 2026 (szacunek)", "wykonanie 2026 I–IX", "wykonanie 2025",
          "wykonanie 2024", "wykonanie 2023"]


# ---------------------------------------------------------------- miary
def zestawienie(d: pd.DataFrame) -> dict:
    s = d.groupby("typ")["kwota_pln"].sum()
    przych, kb, ko = s.get("przychod", 0.0), s.get("koszt_bezposredni", 0.0), s.get("koszt_operacyjny", 0.0)
    marza = przych - kb
    return {"przychody": przych, "koszty_bezposrednie": kb, "marza_brutto": marza,
            "marza_proc": marza / przych * 100 if przych else 0.0, "koszty_operacyjne": ko, "wynik": marza - ko}


def wyniki_linii(d: pd.DataFrame) -> pd.DataFrame:
    """Dwa poziomy wyniku linii (Z4-R3): marża − MPK operacyjne linii; wynik po podziale kosztów wspólnych (D21)."""
    par = konfig.parametry()
    wspolne = d[(d["typ"] == "koszt_operacyjny") & d["mpk"].isin(par["mpk_wspolne"])]["kwota_pln"].sum()
    wiersze = []
    for l in LINIE:
        dl = d[d["linia"] == l]
        przych = dl[dl["typ"] == "przychod"]["kwota_pln"].sum()
        kb = dl[dl["typ"] == "koszt_bezposredni"]["kwota_pln"].sum()
        ko = dl[dl["typ"] == "koszt_operacyjny"]["kwota_pln"].sum()
        wiersze.append({"linia": l, "przychody": przych, "koszty_bezposrednie": kb, "marza_brutto": przych - kb,
                        "marza_proc": (przych - kb) / przych * 100 if przych else 0.0,
                        "koszty_MPK_linii": ko, "wynik_linii": przych - kb - ko})
    t = pd.DataFrame(wiersze)
    klucz = t["marza_brutto"].clip(lower=0)
    udzial = klucz / klucz.sum() if klucz.sum() else 0.0
    t["koszty_wspolne_przypisane"] = udzial * wspolne
    t["wynik_po_podziale"] = t["wynik_linii"] - t["koszty_wspolne_przypisane"]
    return t


def koszty_mpk(d: pd.DataFrame) -> pd.DataFrame:
    par = konfig.parametry()
    nazwy = {int(k): v["nazwa"] for k, v in par["mpk"].items()}
    k = d[d["typ"] == "koszt_operacyjny"].groupby("mpk")["kwota_pln"].sum().reset_index()
    k["mpk"] = k["mpk"].astype(int)
    k.insert(1, "nazwa", k["mpk"].map(nazwy))
    return k


def kontrola(d: pd.DataFrame) -> list[dict]:
    """Z4-R5: Σ marża linii − Σ koszty MPK = wynik firmy; Σ MPK = koszty operacyjne razem."""
    par = konfig.parametry()
    z = zestawienie(d)
    linie = wyniki_linii(d)
    mpki = [int(k) for k in par["mpk"]]
    suma_mpk = d[(d["typ"] == "koszt_operacyjny") & d["mpk"].isin(mpki)]["kwota_pln"].sum()
    wynik_z_linii = linie["marza_brutto"].sum() - suma_mpk
    return [
        {"kontrola": "Σ marża linii − Σ koszty MPK = wynik firmy", "lewa": wynik_z_linii, "prawa": z["wynik"],
         "roznica": wynik_z_linii - z["wynik"]},
        {"kontrola": "Σ koszty MPK = koszty operacyjne razem", "lewa": suma_mpk, "prawa": z["koszty_operacyjne"],
         "roznica": suma_mpk - z["koszty_operacyjne"]},
    ]


def kontrola_ok(d: pd.DataFrame) -> bool:
    return all(abs(k["roznica"]) < 0.5 for k in kontrola(d))


def scenariusze(d: pd.DataFrame, proc: float | None = None) -> pd.DataFrame:
    """Z4-R7 / D28: wpływ ±proc% kursu USD, stawek frachtu i wolumenu na wynik."""
    proc = proc if proc is not None else konfig.parametry()["scenariusz_proc"]
    baza_wynik = zestawienie(d)["wynik"]
    def wplyw(maska, znak):
        e = d.copy()
        e.loc[maska, "kwota_pln"] *= (1 + znak * proc / 100)
        return zestawienie(e)["wynik"] - baza_wynik
    usd = d["frachtowa_usd"] == 1
    wol = (d["wolumenowa"] == 1) & d["typ"].isin(["przychod", "koszt_bezposredni"])
    wiersze = []
    for nazwa, maska in [("kurs USD/PLN", usd), ("stawki frachtu (USD)", usd), ("wolumen", wol)]:
        wiersze.append({"scenariusz": nazwa, f"+{proc:g}%": wplyw(maska, 1), f"−{proc:g}%": wplyw(maska, -1)})
    return pd.DataFrame(wiersze)


def wskazniki_transportu(conn, d: pd.DataFrame) -> dict:
    """Z4-R6: łączny koszt kursów i koszt na kurs — własny i obcy."""
    fl = baza.df(conn, "SELECT SUM(kursy_wlasne) AS w, SUM(kursy_podwykonawcow) AS o FROM flota_miesiac")
    flota = d[(d["flotowa"] == 1)]["kwota_pln"].sum()
    podw = d[(d["linia"] == "TRN") & (d["kategoria"] == "podwykonawcy transportowi")]["kwota_pln"].sum()
    w, o = fl["w"][0] or 0, fl["o"][0] or 0
    return {"koszt_kursow_lacznie": flota + podw, "kursy_wlasne": w, "kursy_obce": o,
            "koszt_na_kurs_wlasny": flota / w if w else None, "koszt_na_kurs_obcy": podw / o if o else None}


def udzial_zrodel(d: pd.DataFrame) -> pd.DataFrame:
    x = d.groupby("zrodlo_liczby")["kwota_pln"].apply(lambda s: s.abs().sum()).reset_index()
    x["udzial_proc"] = x["kwota_pln"] / x["kwota_pln"].sum() * 100
    return x


def niezaakceptowane(d: pd.DataFrame) -> list[str]:
    return sorted(d.loc[d["status"].isin(["w_przygotowaniu", "zlozona", "odrzucona"]), "formatka_id"].dropna().unique())


def filtruj(d: pd.DataFrame, linia=None, mpk=None) -> pd.DataFrame:
    if linia:
        d = d[d["linia"] == linia]
    if mpk:
        d = d[d["mpk"] == mpk]
    return d


def okres(d: pd.DataFrame, rodzaj: str) -> pd.Series:
    if rodzaj == "miesiąc":
        return d["miesiac"]
    if rodzaj == "kwartał":
        return d["miesiac"].str[:4] + "-Q" + ((d["miesiac"].str[5:].astype(int) - 1) // 3 + 1).astype(str)
    return d["miesiac"].str[:4]


def wolumeny_2027(conn) -> pd.DataFrame:
    par = konfig.parametry()
    d = baza.df(conn, """SELECT f.linia, w.miesiac, MAX(w.wolumen) AS wolumen FROM wiersz_formatki w
        JOIN pozycja p USING(pozycja_id) JOIN formatka f USING(formatka_id)
        WHERE f.typ_formatki='linia' AND p.typ='przychod' AND p.wolumenowa=1 GROUP BY f.linia, w.miesiac""")
    d["jednostka"] = d["linia"].map(par["jednostka_linii"])
    return d


def wolumeny_historia(conn, od: str, do: str) -> pd.DataFrame:
    return baza.df(conn, "SELECT * FROM wolumeny WHERE miesiac BETWEEN ? AND ?", (od, do))


def budzet_2026(conn) -> pd.DataFrame:
    return baza.df(conn, "SELECT * FROM budzet_2026")
