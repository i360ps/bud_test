"""Dashboardy (sekcja 7): Prezes, CFO, Dyrektor Operacyjny, Rada, Kontroler."""
import pandas as pd
import streamlit as st

from . import agregacja as ag
from . import baza, konfig, proces
from .ui_formatki import zl


def _kontrolka(d: pd.DataFrame) -> None:
    """Z4-R5: kontrolka zgodności na każdym ekranie."""
    k = ag.kontrola(d)
    if all(abs(x["roznica"]) < 0.5 for x in k):
        st.success("Kontrola zgodności sum: OK (Σ marża linii − Σ MPK = wynik; Σ MPK = koszty operacyjne).")
    else:
        for x in k:
            if abs(x["roznica"]) >= 0.5:
                st.error(f"🔴 NIEZGODNOŚĆ: {x['kontrola']} — różnica {zl(x['roznica'])}")


def _filtry(conn, klucz: str, domyslna="budżet 2027"):
    c = st.columns(5)
    wersja = c[0].selectbox("Wersja danych", ag.WERSJE, index=ag.WERSJE.index(domyslna), key=f"w_{klucz}")
    rodzaj = c[1].selectbox("Okres", ["rok", "kwartał", "miesiąc"], key=f"o_{klucz}")
    linia = c[2].selectbox("Linia", [None] + ag.LINIE, format_func=lambda x: str(x) if x else "wszystkie", key=f"l_{klucz}")
    mpki = [int(m) for m in konfig.parametry()["mpk"]]
    mpk = c[3].selectbox("MPK", [None] + mpki, format_func=lambda x: str(x) if x else "wszystkie", key=f"m_{klucz}")
    tylko = c[4].checkbox("Tylko zaakceptowane", key=f"t_{klucz}", disabled=wersja != "budżet 2027")
    d = ag.wersja(conn, wersja, tylko)
    return wersja, rodzaj, ag.filtruj(d, linia, mpk), d


def _naglowek_budzetu(conn, wersja, d_pelne):
    if wersja != "budżet 2027":
        if "szacunek" in wersja:
            st.caption("Etykieta: **szacunek** — X–XII 2026 z prognozy (D27).")
        return
    nz = ag.niezaakceptowane(d_pelne)
    if nz:
        tylko = ag.zestawienie(d_pelne[d_pelne["status"] == "zaakceptowana"])
        st.warning(f"Suma obejmuje formatki **niezaakceptowane** ({len(nz)}): {', '.join(nz)}. "
                   f"Wynik tylko z zaakceptowanych: {zl(tylko['wynik'])}.")


def _tabela_okresow(d, rodzaj):
    d = d.assign(okres=ag.okres(d, rodzaj))
    rows = []
    for o, g in d.groupby("okres"):
        z = ag.zestawienie(g)
        rows.append({"okres": o, **{k: v for k, v in z.items()}})
    return pd.DataFrame(rows)


def _metryki(z):
    c = st.columns(5)
    c[0].metric("Przychody", zl(z["przychody"]))
    c[1].metric("Marża brutto", zl(z["marza_brutto"]), f"{z['marza_proc']:.1f}%".replace(".", ","), delta_color="off")
    c[2].metric("Koszty bezpośrednie", zl(z["koszty_bezposrednie"]))
    c[3].metric("Koszty operacyjne", zl(z["koszty_operacyjne"]))
    c[4].metric("Wynik operacyjny", zl(z["wynik"]))


def widok_prezes(conn):
    st.header("Widok Prezesa")
    wersja, rodzaj, d, d_pelne = _filtry(conn, "prezes")
    _naglowek_budzetu(conn, wersja, d_pelne)
    st.subheader("Wolumeny")
    if wersja == "budżet 2027":
        w = ag.wolumeny_2027(conn).pivot(index="miesiac", columns="linia", values="wolumen")
        st.dataframe(w.round(0), width="stretch")
    else:
        rok = wersja[-4:] if wersja[-4:].isdigit() else "2026"
        st.dataframe(ag.wolumeny_historia(conn, f"{rok}-01", f"{rok}-12"), hide_index=True, width="stretch")
    st.subheader("Przychody")
    t = _tabela_okresow(d[d["typ"] == "przychod"], rodzaj)
    st.bar_chart(t.set_index("okres")["przychody"])
    _metryki(ag.zestawienie(d))
    st.caption("Udział w rynku — poza zakresem (brak danych rynkowych, D30).")
    _kontrolka(d_pelne)


def widok_cfo(conn):
    st.header("Widok CFO")
    wersja, rodzaj, d, d_pelne = _filtry(conn, "cfo")
    _naglowek_budzetu(conn, wersja, d_pelne)
    _metryki(ag.zestawienie(d))
    st.subheader("Marża brutto i wynik linii (dwa poziomy)")
    st.dataframe(ag.wyniki_linii(d).round(0), hide_index=True, width="stretch")
    st.caption("Klucz podziału kosztów wspólnych (MPK 100, 200, 300, 500): udział w marży brutto (D21).")
    st.subheader("Koszty operacyjne wg MPK")
    st.dataframe(ag.koszty_mpk(d).round(0), hide_index=True, width="stretch")
    if wersja != "budżet 2027":
        st.caption("Uwaga: koszty transportu do 06.2025 na MPK 410, od 07.2025 na MPK 440 — porównuj sumę 410+440 (D23).")
    st.subheader("Wynik w okresach")
    st.dataframe(_tabela_okresow(d, rodzaj).round(0), hide_index=True, width="stretch")
    if wersja == "budżet 2027":
        st.subheader("Scenariusze ±10% — wpływ na wynik")
        st.dataframe(ag.scenariusze(d).round(0), hide_index=True, width="stretch")
        st.subheader("Udział kwot wg źródła liczby")
        st.dataframe(ag.udzial_zrodel(d).round(1), hide_index=True, width="stretch")
    _kontrolka(d_pelne)


def widok_do(conn):
    st.header("Widok Dyrektora Operacyjnego")
    wersja, rodzaj, d, d_pelne = _filtry(conn, "do")
    _naglowek_budzetu(conn, wersja, d_pelne)
    t = ag.wyniki_linii(d)[["linia", "przychody", "koszty_bezposrednie", "marza_brutto", "marza_proc",
                            "koszty_MPK_linii", "wynik_linii"]]
    st.subheader("Marża linii i koszty MPK operacyjnych (bez kosztów wspólnych)")
    st.dataframe(t.round(0), hide_index=True, width="stretch")
    k = ag.koszty_mpk(d)
    st.dataframe(k[k["mpk"].isin([410, 420, 430, 440, 450])].round(0), hide_index=True, width="stretch")
    if wersja == "budżet 2027":
        st.subheader("Transport: kursy własne i obce")
        w = ag.wskazniki_transportu(conn, d)
        c = st.columns(3)
        c[0].metric("Łączny koszt kursów", zl(w["koszt_kursow_lacznie"]))
        c[1].metric("Koszt na kurs własny", zl(w["koszt_na_kurs_wlasny"]))
        c[2].metric("Koszt na kurs obcy", zl(w["koszt_na_kurs_obcy"]))
    _kontrolka(d_pelne)


def tabela_rady(conn) -> pd.DataFrame:
    """Jedna strona dla Rady: budżet 2027, przewidywane 2026 (szacunek), wykonanie 2025."""
    kolumny = {"Budżet 2027": ag.budzet_2027(conn), "Przewidywane wykonanie 2026 (szacunek)": ag.przewidywane_2026(conn),
               "Wykonanie 2025": ag.wykonanie(conn, "2025-01", "2025-12")}
    miary = {"przychody": "Przychody", "koszty_bezposrednie": "Koszty bezpośrednie", "marza_brutto": "Marża brutto",
             "koszty_operacyjne": "Koszty operacyjne", "wynik": "Wynik operacyjny"}
    t = pd.DataFrame({k: ag.zestawienie(v) for k, v in kolumny.items()}).loc[list(miary)]
    t.index = list(miary.values())
    t["Zmiana 2027 vs 2026"] = t["Budżet 2027"] - t["Przewidywane wykonanie 2026 (szacunek)"]
    return t


def widok_rada(conn):
    st.header("Rada Nadzorcza — zestawienie")
    d = ag.budzet_2027(conn)
    _naglowek_budzetu(conn, "budżet 2027", d)
    st.dataframe(tabela_rady(conn).round(0), width="stretch")
    st.subheader("Ryzyka (scenariusze ±10%)")
    st.dataframe(ag.scenariusze(d).round(0), hide_index=True, width="stretch")
    b = ag.budzet_2026(conn)
    st.subheader("Porównanie z budżetem 2026 (tylko rok i I–IX, D29)")
    if b.empty:
        st.info("Brak danych budżetu 2026 w pliku data/budzet_2026.csv.")
    else:
        st.dataframe(b, hide_index=True, width="stretch")
    _kontrolka(d)


def widok_kontroler(conn, data):
    st.header("Kontroler — postęp formatek")
    proces.aktualizuj_terminy(conn, data)
    f = baza.df(conn, "SELECT formatka_id, typ_formatki, status, flaga_spozniona, czeka_na, termin_zlozenia,"
                      " termin_akceptacji FROM formatka ORDER BY formatka_id")
    f["wypelnia"] = [proces.wypelniajacy(conn, x, data) or "(wakat)" for x in f["formatka_id"]]
    f["akceptuje"] = [proces.akceptujacy(conn, x, data)["osoba"] for x in f["formatka_id"]]
    f["spozniona"] = f["flaga_spozniona"].map({1: "SPÓŹNIONA", 0: ""})
    st.dataframe(f.drop(columns="flaga_spozniona"), hide_index=True, width="stretch")
    for r in f[f["flaga_spozniona"] == 1].itertuples():
        st.error(f"Formatka {r.formatka_id} spóźniona, czeka na: {r.czeka_na}")
    st.subheader("Historia akcji")
    st.dataframe(proces.historia(conn), hide_index=True, width="stretch")
    _kontrolka(ag.budzet_2027(conn))


WIDOKI = {"Prezes": widok_prezes, "CFO": widok_cfo, "Dyrektor Operacyjny": widok_do, "Rada": widok_rada}


def ekran(conn, kod, data):
    dostepne = konfig.uprawnienia()["widoki"].get(kod, ["Prezes"])
    w = st.radio("Widok", dostepne, horizontal=True)
    if w == "Kontroler":
        widok_kontroler(conn, data)
    else:
        WIDOKI[w](conn)
