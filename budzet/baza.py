"""Baza SQLite: schemat (sekcja 3 specyfikacji) i import danych z data/."""
import sqlite3
from pathlib import Path

import pandas as pd

from . import konfig

SCHEMAT = """
CREATE TABLE IF NOT EXISTS stanowisko (
    kod TEXT PRIMARY KEY, nazwa TEXT, osoba TEXT, przelozony_kod TEXT,
    data_odejscia TEXT, data_przyjscia TEXT);
CREATE TABLE IF NOT EXISTS nieobecnosc (stanowisko_kod TEXT, data_od TEXT, data_do TEXT);
CREATE TABLE IF NOT EXISTS zastepstwo (stanowisko_kod TEXT, zastepca_kod TEXT, zakres TEXT);
CREATE TABLE IF NOT EXISTS mpk (mpk INTEGER PRIMARY KEY, nazwa TEXT, linia TEXT);
CREATE TABLE IF NOT EXISTS pozycja (
    pozycja_id INTEGER PRIMARY KEY AUTOINCREMENT, typ TEXT, linia TEXT, mpk INTEGER,
    kategoria TEXT, jednostka TEXT, wolumenowa INTEGER, frachtowa_usd INTEGER,
    jednorazowa INTEGER, flotowa INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS formatka (
    formatka_id TEXT PRIMARY KEY, typ_formatki TEXT, linia TEXT, mpk INTEGER,
    stanowisko_wypelnia TEXT, osoba_wyznaczona TEXT, stanowisko_akceptuje TEXT,
    status TEXT, flaga_spozniona INTEGER DEFAULT 0, czeka_na TEXT,
    termin_zlozenia TEXT, termin_akceptacji TEXT, zlozyl TEXT);
CREATE TABLE IF NOT EXISTS wiersz_formatki (
    formatka_id TEXT, pozycja_id INTEGER, miesiac TEXT,
    wolumen REAL, stawka REAL, stawka_usd REAL, kwota_usd REAL, kwota_pln REAL,
    podpowiedz_kwota REAL, podpowiedz_wolumen REAL, podpowiedz_stawka REAL,
    metoda TEXT, blad_mape REAL, wartosc_rok_poprzedni REAL, wartosc_2026 REAL,
    zrodlo_liczby TEXT, uzasadnienie TEXT,
    PRIMARY KEY (formatka_id, pozycja_id, miesiac));
CREATE TABLE IF NOT EXISTS flota_miesiac (
    formatka_id TEXT, miesiac TEXT, liczba_zestawow INTEGER, rata_leasingu REAL,
    przebieg_km REAL, liczba_etatow REAL, kursy_wlasne REAL, kursy_podwykonawcow REAL,
    udzial_kursow_wlasnych REAL, PRIMARY KEY (formatka_id, miesiac));
CREATE TABLE IF NOT EXISTS historia (
    formatka_id TEXT, akcja TEXT, osoba TEXT, stanowisko TEXT, w_zastepstwie_kogo TEXT,
    data_czas TEXT, komentarz TEXT);
CREATE TABLE IF NOT EXISTS komunikat (data TEXT, do_kogo TEXT, tresc TEXT, formatka_id TEXT);
CREATE TABLE IF NOT EXISTS zalozenia (
    nazwa TEXT, miesiac TEXT, wartosc REAL, ustalil TEXT, data TEXT, domyslne INTEGER,
    PRIMARY KEY (nazwa, miesiac));
CREATE TABLE IF NOT EXISTS wykonanie (
    miesiac TEXT, typ TEXT, linia TEXT, mpk INTEGER, kategoria TEXT, kwota_pln REAL,
    wylaczone_z_uczenia INTEGER DEFAULT 0, powod TEXT);
CREATE TABLE IF NOT EXISTS wolumeny (
    miesiac TEXT PRIMARY KEY, fcl_teu REAL, lcl_m3 REAL, zgloszenia_celne REAL,
    kursy_transport REAL, kurs_usd_pln REAL);
CREATE TABLE IF NOT EXISTS test_wsteczny (pozycja_id INTEGER, metoda TEXT, mape REAL);
CREATE TABLE IF NOT EXISTS prognoza (
    pozycja_id INTEGER, miesiac TEXT, metoda TEXT, kwota_pln REAL, wolumen REAL,
    stawka REAL, mape REAL, wersja_danych TEXT);
CREATE TABLE IF NOT EXISTS budzet_2026 (okres TEXT, miara TEXT, kwota_pln REAL);
CREATE TABLE IF NOT EXISTS opis (
    opis_id INTEGER PRIMARY KEY AUTOINCREMENT, wersja INTEGER, sekcja TEXT, kolejnosc INTEGER,
    tresc TEXT, status_opisu TEXT, zatwierdzil TEXT, data_zatwierdzenia TEXT,
    zgodnosc_liczb INTEGER, lista_ostrzezen TEXT);
"""


def polacz(sciezka: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(sciezka or konfig.PLIK_BAZY), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def utworz_schemat(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMAT)
    conn.commit()


def _zaladuj_strukture(conn, upr: dict, par: dict) -> None:
    for kod, s in upr["stanowiska"].items():
        conn.execute(
            "INSERT INTO stanowisko VALUES (?,?,?,?,?,?)",
            (kod, s["nazwa"], s.get("osoba"), s.get("przelozony"),
             s.get("data_odejscia"), s.get("data_przyjscia")))
    for n in upr.get("nieobecnosci", []):
        conn.execute("INSERT INTO nieobecnosc VALUES (?,?,?)", (n["stanowisko"], n["od"], n["do"]))
    for z in upr.get("zastepstwa", []):
        conn.execute("INSERT INTO zastepstwo VALUES (?,?,?)", (z["stanowisko"], z["zastepca"], z["zakres"]))
    for nr, m in par["mpk"].items():
        conn.execute("INSERT INTO mpk VALUES (?,?,?)", (int(nr), m["nazwa"], m["linia"]))


def _zaladuj_wykonanie(conn, par: dict) -> pd.DataFrame:
    df = pd.read_csv(konfig.KATALOG_DANYCH / "dane_finansowe_miesieczne.csv", sep=";", dtype={"mpk": "string"})
    df["linia"] = df["linia"].fillna("")
    df["mpk"] = pd.to_numeric(df["mpk"], errors="coerce")
    df["wylaczone_z_uczenia"] = 0
    df["powod"] = None
    for a in par.get("anomalie", []):
        maska = (df["miesiac"] == a["miesiac"]) & (df["linia"] == a["linia"]) & (df["kategoria"] == a["kategoria"])
        df.loc[maska, "wylaczone_z_uczenia"] = 1
        df.loc[maska, "powod"] = a["powod"]
    for r in df.itertuples(index=False):
        conn.execute(
            "INSERT INTO wykonanie VALUES (?,?,?,?,?,?,?,?)",
            (r.miesiac, r.typ, r.linia or None, None if pd.isna(r.mpk) else int(r.mpk),
             r.kategoria, float(r.kwota_pln), int(r.wylaczone_z_uczenia), r.powod))
    return df


def _zaladuj_wolumeny(conn) -> None:
    w = pd.read_csv(konfig.KATALOG_DANYCH / "wolumeny_miesieczne.csv", sep=";")
    for r in w.itertuples(index=False):
        vals = [None if pd.isna(v) else float(v) for v in
                (r.fcl_teu, r.lcl_m3, r.zgloszenia_celne, r.kursy_transport, r.kurs_usd_pln)]
        conn.execute("INSERT INTO wolumeny VALUES (?,?,?,?,?,?)", (r.miesiac, *vals))


def _zaladuj_budzet_2026(conn) -> None:
    plik = konfig.KATALOG_DANYCH / "budzet_2026.csv"
    if not plik.exists():
        return
    b = pd.read_csv(plik, sep=";")
    for r in b.itertuples(index=False):
        if pd.notna(r.kwota_pln):
            conn.execute("INSERT INTO budzet_2026 VALUES (?,?,?)", (r.okres, r.miara, float(r.kwota_pln)))


def _zaladuj_pozycje(conn, df: pd.DataFrame, par: dict) -> None:
    frachtowe = set(par["pozycje_frachtowe_usd"])
    jednorazowe = {(j["mpk"], j["kategoria"]) for j in par["pozycje_jednorazowe"]}
    kombinacje = df[["typ", "linia", "mpk", "kategoria"]].drop_duplicates()
    # MPK 440 istnieje od 07.2025; jego pozycje są w danych, więc trafiają na listę.
    for r in kombinacje.sort_values(["typ", "linia", "mpk", "kategoria"]).itertuples(index=False):
        mpk = None if pd.isna(r.mpk) else int(r.mpk)
        linia = r.linia or None
        wolumenowa = int(r.typ in ("przychod", "koszt_bezposredni"))
        conn.execute(
            "INSERT INTO pozycja (typ, linia, mpk, kategoria, jednostka, wolumenowa, frachtowa_usd, jednorazowa)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (r.typ, linia, mpk, r.kategoria,
             par["jednostka_linii"].get(linia) if wolumenowa else None,
             wolumenowa, int(r.kategoria in frachtowe), int((mpk, r.kategoria) in jednorazowe)))
    for kat in par["pozycje_floty"]:
        conn.execute(
            "INSERT INTO pozycja (typ, linia, mpk, kategoria, jednostka, wolumenowa, frachtowa_usd, jednorazowa, flotowa)"
            " VALUES (?,?,?,?,?,?,?,?,1)",
            ("koszt_bezposredni" if par["flota_koszt_bezposredni"] else "koszt_operacyjny",
             "TRN", par["mpk_floty"], kat, None, 0, 0, 0))


def inicjalizuj(sciezka: Path | str | None = None, z_formatkami: bool = True) -> sqlite3.Connection:
    """Tworzy bazę od zera (import CSV + konfiguracja). Zwraca połączenie."""
    sciezka = Path(sciezka or konfig.PLIK_BAZY)
    if sciezka.exists():
        sciezka.unlink()
    conn = polacz(sciezka)
    utworz_schemat(conn)
    par, upr = konfig.parametry(), konfig.uprawnienia()
    _zaladuj_strukture(conn, upr, par)
    df = _zaladuj_wykonanie(conn, par)
    _zaladuj_wolumeny(conn)
    _zaladuj_budzet_2026(conn)
    _zaladuj_pozycje(conn, df, par)
    conn.commit()
    if z_formatkami:
        from . import formatki, predykcja
        predykcja.uruchom(conn)
        formatki.zalozenia_domyslne(conn)
        formatki.rozeslij(conn)
    return conn


def df(conn, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def sumy_roczne(conn) -> pd.DataFrame:
    """Sumy roczne wykonania wg typu (tys. zł) – kontrola importu."""
    d = df(conn, "SELECT substr(miesiac,1,4) AS rok, typ, SUM(kwota_pln) AS kwota FROM wykonanie GROUP BY rok, typ")
    return d.pivot(index="typ", columns="rok", values="kwota") / 1000
