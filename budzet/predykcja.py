"""Moduł 3 — predykcja (sekcja 6 specyfikacji, Z3-R1…R10).

Metody: (1) powtórka roku, (2) średnia 12 mies., (3) trend liniowy z sezonowością (scikit-learn),
(4) czynnikowy: wolumen × stawka (tylko pozycje wolumenowe).
Test wsteczny: uczenie do 09.2025, prognoza 10.2025–09.2026, MAPE. Wybór metody: najniższy MAPE (D25).
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from . import baza, konfig

METODY = ["powtorka_roku", "srednia_12m", "trend_sezon", "czynnikowy"]
NAZWY_METOD = {"powtorka_roku": "powtórka roku", "srednia_12m": "średnia 12 mies.",
               "trend_sezon": "trend z sezonowością", "czynnikowy": "czynnikowy (wolumen × stawka)"}


def _mies(m: str, k: int) -> str:
    """Przesunięcie miesiąca 'RRRR-MM' o k."""
    r, mm = int(m[:4]), int(m[5:])
    n = r * 12 + mm - 1 + k
    return f"{n // 12}-{n % 12 + 1:02d}"


def zakres(od: str, do: str) -> list[str]:
    wyn, m = [], od
    while m <= do:
        wyn.append(m)
        m = _mies(m, 1)
    return wyn


# ---------------------------------------------------------------- metody (seria: pd.Series indeks 'RRRR-MM', NaN = brak/wyłączone)
def _ucz(s: pd.Series, do: str) -> pd.Series:
    return s[s.index <= do].dropna()


def prognoza_metoda(metoda: str, s: pd.Series, uczenie_do: str, miesiace: list[str],
                    wol: pd.Series | None = None) -> pd.Series:
    u = _ucz(s, uczenie_do)
    sr12 = u.iloc[-12:].mean()
    if metoda == "srednia_12m":
        return pd.Series(sr12, index=miesiace)
    if metoda == "powtorka_roku":
        return _powtorka(s, uczenie_do, miesiace, sr12)
    if metoda == "trend_sezon":
        t0 = u.index[0]
        def cechy(ms):
            t = [len(zakres(t0, m)) - 1 for m in ms]
            mies = [int(m[5:]) for m in ms]
            return np.array([[ti] + [1.0 if mi == k else 0.0 for k in range(2, 13)] for ti, mi in zip(t, mies)])
        model = LinearRegression().fit(cechy(list(u.index)), u.values)
        return pd.Series(model.predict(cechy(miesiace)), index=miesiace)
    if metoda == "czynnikowy":
        vf = prognoza_wolumenu(wol, uczenie_do, miesiace)
        return vf * stawka_historyczna(s, wol, uczenie_do)
    raise ValueError(metoda)


def _powtorka(s: pd.Series, uczenie_do: str, miesiace: list[str], awaryjnie: float) -> pd.Series:
    wyn = {}
    for m in miesiace:
        zrodlo = _mies(m, -12)
        if zrodlo <= uczenie_do:
            v = s.get(zrodlo, np.nan)
        else:
            v = wyn.get(zrodlo, np.nan)
        wyn[m] = awaryjnie if pd.isna(v) else v
    return pd.Series(wyn)


def prognoza_wolumenu(wol: pd.Series, uczenie_do: str, miesiace: list[str]) -> pd.Series:
    """Wolumen w modelu czynnikowym: powtórka roku (jak w teście Zespołu 3)."""
    u = _ucz(wol, uczenie_do)
    return _powtorka(wol, uczenie_do, miesiace, u.iloc[-12:].mean())


def stawka_historyczna(s: pd.Series, wol: pd.Series, uczenie_do: str) -> float:
    """Stawka na jednostkę: suma kwot / suma wolumenu z ostatnich 3 miesięcy uczenia (bez braków)."""
    d = pd.DataFrame({"s": s, "w": wol})
    d = d[(d.index <= uczenie_do)].dropna().iloc[-3:]
    return d["s"].sum() / d["w"].sum()


def mape(rzecz: pd.Series, prog: pd.Series) -> float:
    d = pd.DataFrame({"r": rzecz, "p": prog}).dropna()
    d = d[d["r"] != 0]
    return float((abs(d["p"] - d["r"]) / abs(d["r"])).mean() * 100)


def test_wsteczny_serii(s: pd.Series, wol: pd.Series | None = None, par: dict | None = None) -> dict:
    par = par or konfig.parametry()
    test = zakres(par["test_od"], par["test_do"])
    metody = METODY if wol is not None else METODY[:3]
    return {m: mape(s.reindex(test), prognoza_metoda(m, s, par["test_uczenie_do"], test, wol)) for m in metody}


# ---------------------------------------------------------------- dane
def _dane(conn):
    w = baza.df(conn, "SELECT * FROM wykonanie")
    vol = baza.df(conn, "SELECT * FROM wolumeny").set_index("miesiac")
    return w, vol


def seria(w: pd.DataFrame, typ: str, linia=None, mpk=None, kategoria=None, z_wykluczeniami=True,
          miesiace=None) -> pd.Series:
    d = w[w["typ"] == typ]
    if linia:
        d = d[d["linia"] == linia]
    if mpk is not None:
        mpki = mpk if isinstance(mpk, (list, tuple, set)) else [mpk]
        d = d[d["mpk"].isin(mpki)]
    if kategoria:
        d = d[d["kategoria"] == kategoria]
    if z_wykluczeniami:
        d = d.assign(kwota_pln=d["kwota_pln"].where(d["wylaczone_z_uczenia"] == 0))
    s = d.groupby("miesiac")["kwota_pln"].sum(min_count=1)
    if miesiace is not None:
        s = s.reindex(miesiace)
    return s


def test_linii(conn, linia: str, typ: str = "przychod", z_wykluczeniami: bool = False) -> dict:
    """MAPE dla całej linii (punkt kontrolny sekcji 6: przychody FCL razem)."""
    par = konfig.parametry()
    w, vol = _dane(conn)
    wsz = sorted(w["miesiac"].unique())
    s = seria(w, typ, linia=linia, z_wykluczeniami=z_wykluczeniami, miesiace=wsz)
    return test_wsteczny_serii(s, vol[par["wolumen_linii"][linia]].reindex(wsz), par)


# ---------------------------------------------------------------- uruchomienie
def uruchom(conn) -> None:
    """Test wsteczny dla każdej pozycji, wybór metody, podpowiedzi 2027 i prognoza X–XII 2026."""
    par = konfig.parametry()
    w, vol = _dane(conn)
    wsz = sorted(w["miesiac"].unique())
    dane_do = par["dane_do"]
    horyzont = zakres(_mies(dane_do, 1), f"{par['rok_budzetu']}-12")
    lacz = set(par["mpk_lacz_w_uczeniu"])
    conn.execute("DELETE FROM test_wsteczny"); conn.execute("DELETE FROM prognoza")

    for p in conn.execute("SELECT * FROM pozycja WHERE flotowa=0").fetchall():
        mpk = p["mpk"]
        if mpk in lacz:  # D23: MPK 410+440 łączone w uczeniu
            s = seria(w, p["typ"], mpk=list(lacz), kategoria=p["kategoria"], miesiace=wsz)
        else:
            s = seria(w, p["typ"], linia=p["linia"], mpk=mpk, kategoria=p["kategoria"], miesiace=wsz)
        v = vol[par["wolumen_linii"][p["linia"]]].reindex(wsz) if p["wolumenowa"] else None
        wyniki = test_wsteczny_serii(s, v, par)
        for met, wart in wyniki.items():
            conn.execute("INSERT INTO test_wsteczny VALUES (?,?,?)", (p["pozycja_id"], met, wart))
        metoda = "powtorka_roku" if p["jednorazowa"] else min(wyniki, key=lambda k: (np.inf if pd.isna(wyniki[k]) else wyniki[k]))
        blad = wyniki[metoda]
        prog = prognoza_metoda(metoda, s, dane_do, horyzont, v)
        if mpk in lacz:
            prog = prog * _udzial_mpk(w, mpk, p["kategoria"], lacz, dane_do)
        prog_wol = prognoza_wolumenu(v, dane_do, horyzont) if v is not None else None
        for m in horyzont:
            kw = float(prog[m])
            wl = None if prog_wol is None else float(prog_wol[m])
            st = None if not wl else kw / wl
            wersja = "podpowiedz_2027" if m.startswith(str(par["rok_budzetu"])) else "prognoza_2026"
            conn.execute("INSERT INTO prognoza VALUES (?,?,?,?,?,?,?,?)",
                         (p["pozycja_id"], m, metoda, kw, wl, st, blad, wersja))
    conn.commit()


def _udzial_mpk(w, mpk, kategoria, lacz, dane_do) -> float:
    """Podział prognozy łącznej 410+440 na MPK wg udziału z ostatnich 12 miesięcy (patrz LUKI)."""
    ost = zakres(_mies(dane_do, -11), dane_do)
    d = w[(w["typ"] == "koszt_operacyjny") & (w["mpk"].isin(list(lacz))) & (w["kategoria"] == kategoria)
          & (w["miesiac"].isin(ost))]
    razem = d["kwota_pln"].sum()
    return float(d.loc[d["mpk"] == mpk, "kwota_pln"].sum() / razem) if razem else 0.0


def wyniki_testu(conn) -> pd.DataFrame:
    t = baza.df(conn, "SELECT * FROM test_wsteczny").pivot(index="pozycja_id", columns="metoda", values="mape")
    poz = baza.df(conn, "SELECT pozycja_id, typ, linia, mpk, kategoria FROM pozycja WHERE flotowa=0")
    wyb = baza.df(conn, "SELECT DISTINCT pozycja_id, metoda AS wybrana FROM prognoza")
    return poz.merge(t.reset_index(), on="pozycja_id").merge(wyb, on="pozycja_id", how="left")
