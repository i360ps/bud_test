"""Ekrany założeń (kurs, stawki — CFO) i predykcji (Kontroler)."""
import streamlit as st

from . import baza, formatki as fm, predykcja, proces


def ekran_zalozen(conn, kod: str, data: str) -> None:
    st.header("Założenia: kurs USD/PLN i stawki frachtu")
    moze = proces.moze_ustalac_zalozenia(conn, kod, data)
    if not moze:
        st.info("Kurs i stawki ustala CFO (w jego zastępstwie Kontroler). Masz podgląd.")
    elif kod != "CFO":
        st.info("Ustalasz założenia w zastępstwie CFO.")
    z = baza.df(conn, "SELECT z.nazwa, z.wartosc, z.ustalil, z.data, z.domyslne FROM zalozenia z ORDER BY nazwa")
    poz = baza.df(conn, "SELECT pozycja_id, typ, linia, kategoria FROM pozycja WHERE frachtowa_usd=1")
    opis = {fm.nazwa_stawki(r.pozycja_id): f"stawka USD/jedn. — {r.linia} · {r.typ} · {r.kategoria}" for r in poz.itertuples()}
    opis[fm.KURS] = "kurs USD/PLN do budżetu"
    z.insert(0, "opis", z["nazwa"].map(opis))
    z["domyslne"] = z["domyslne"].map({1: "tak [DOMYŚLNE]", 0: "nie"})
    st.dataframe(z, hide_index=True, width="stretch")
    if moze:
        nazwa = st.selectbox("Założenie", z["nazwa"].tolist(), format_func=lambda n: opis.get(n, n))
        wart = st.number_input("Nowa wartość", value=float(z.loc[z.nazwa == nazwa, "wartosc"].iloc[0]), format="%.4f")
        if st.button("Zapisz założenie", type="primary"):
            fm.ustaw_zalozenie(conn, nazwa, wart, kod, data)
            st.success("Zapisano; wiersze frachtowe przeliczone.")
            st.rerun()


def ekran_predykcji(conn, kod: str) -> None:
    st.header("Predykcja: test wsteczny i wybór metody")
    st.caption("Uczenie do 09.2025, test 10.2025–09.2026, miara MAPE (%). Metoda wybierana osobno dla każdej pozycji "
               "(najniższy MAPE); pozycje jednorazowe — powtórka roku; flota — brak podpowiedzi.")
    t = predykcja.wyniki_testu(conn)
    t = t.rename(columns=predykcja.NAZWY_METOD)
    t["wybrana"] = t["wybrana"].map(predykcja.NAZWY_METOD)
    st.dataframe(t.round(1), hide_index=True, width="stretch")
    st.subheader("Punkt kontrolny: przychody FCL razem (dane bez wyłączeń)")
    st.write({predykcja.NAZWY_METOD[k]: round(v, 1) for k, v in predykcja.test_linii(conn, "FCL").items()})
    if kod == "KONTROLER":
        zlozone = conn.execute("SELECT COUNT(*) FROM formatka WHERE status!='w_przygotowaniu'").fetchone()[0]
        if zlozone:
            st.caption("Ponowne rozesłanie jest zablokowane: część formatek została już złożona.")
        elif st.button("Uruchom predykcję i roześlij formatki od nowa"):
            predykcja.uruchom(conn)
            fm.rozeslij(conn)
            st.success("Predykcja przeliczona, formatki rozesłane.")
