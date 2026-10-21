"""Aplikacja budżetowa 2027 — Nordmare Spedycja. Uruchom: streamlit run app.py"""
from datetime import date

import streamlit as st

from budzet import baza, konfig, proces, ui_dashboard, ui_formatki, ui_opis, ui_predykcja

st.set_page_config(page_title="Budżet 2027 — Nordmare", layout="wide")


@st.cache_resource
def polaczenie(sciezka: str):
    from pathlib import Path
    if not Path(sciezka).exists():
        return baza.inicjalizuj(sciezka)
    return baza.polacz(sciezka)


conn = polaczenie(str(konfig.PLIK_BAZY))
upr = konfig.uprawnienia()
par = konfig.parametry()

# --- panel boczny: wybór roli (bez logowania) ---
st.sidebar.title("Budżet 2027")
stanowiska = upr["stanowiska"]
kod = st.sidebar.selectbox("Rola (stanowisko)", list(stanowiska), format_func=lambda k: stanowiska[k]["nazwa"])
st.sidebar.caption(f"Osoba: {stanowiska[kod].get('osoba') or '(wakat)'}")
data = st.sidebar.date_input("Data symulacji", value=date.fromisoformat(str(par["data_symulacji"])),
                             help="„Dzisiejsza” data do sprawdzania terminów i zastępstw.").isoformat()
proces.aktualizuj_terminy(conn, data)

for k in conn.execute("SELECT tresc FROM komunikat WHERE do_kogo=?", (stanowiska[kod].get("osoba"),)).fetchall():
    st.sidebar.warning(k[0])

tylko_odczyt = kod in upr["uprawnienia"]["tylko_odczyt"]
strony = []
if not tylko_odczyt:
    strony += ["Moje formatki", "Do akceptacji"]
if kod == upr["wyznacza_osoby_wakatow"]:
    strony.append("Wakaty")
if kod in ("CFO", "KONTROLER"):
    strony += ["Założenia", "Predykcja"]
strony.insert(0, "Dashboard")
strony.append("Opis budżetu")
strony.append("Dane")
strona = st.sidebar.radio("Ekran", strony)

if strona == "Dashboard":
    ui_dashboard.ekran(conn, kod, data)
elif strona == "Moje formatki":
    ui_formatki.ekran_moje_formatki(conn, kod, data)
elif strona == "Do akceptacji":
    ui_formatki.ekran_akceptacji(conn, kod, data)
elif strona == "Wakaty":
    ui_formatki.ekran_wakatow(conn, kod, data)
elif strona == "Założenia":
    ui_predykcja.ekran_zalozen(conn, kod, data)
elif strona == "Predykcja":
    ui_predykcja.ekran_predykcji(conn, kod)
elif strona == "Opis budżetu":
    ui_opis.ekran(conn, kod, data)
elif strona == "Dane":
    st.header("Dane i konfiguracja")
    st.subheader("Sumy roczne wykonania (tys. zł)")
    st.dataframe(baza.sumy_roczne(conn).round(0), width="stretch")
    st.subheader("MPK")
    st.dataframe(baza.df(conn, "SELECT * FROM mpk"), width="stretch", hide_index=True)
    st.subheader("Wiersze wyłączone z uczenia (anomalie)")
    st.dataframe(baza.df(conn, "SELECT * FROM wykonanie WHERE wylaczone_z_uczenia=1"), width="stretch", hide_index=True)
