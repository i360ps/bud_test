"""Ekran opisu budżetu (moduł 5): projekt → poprawki Kontrolera → kontrola → zatwierdzenie CFO."""
import streamlit as st

from . import konfig, opis, proces


def ekran(conn, kod: str, data: str) -> None:
    st.header("Opis budżetu dla Zarządu i Rady Nadzorczej")
    upr = konfig.uprawnienia()["uprawnienia"]
    w = opis.ostatnia_wersja(conn)
    if kod in upr["poprawia_opis"] and st.button("Wygeneruj nowy projekt opisu z tabel"):
        w = opis.generuj(conn)
        st.rerun()
    if not w:
        st.info("Projekt opisu jeszcze nie powstał (generuje go Kontroler po konsolidacji).")
        return
    status = opis.status(conn, w)
    k = opis.kontrola(conn, w)
    c = st.columns(3)
    c[0].metric("Wersja / status", f"{w} / {status}")
    c[1].metric("Słowa", f"{k['slowa']} / {k['limit']}")
    c[2].metric("Zgodność liczb z tabelami", "TAK" if k["zgodnosc_liczb"] else "NIE")
    if not k["zgodnosc_liczb"]:
        st.error("Kwoty spoza tabel: " + ", ".join(k["niezgodne"]))
    if not k["w_limicie"]:
        st.error("Opis przekracza limit słów.")
    edycja = kod in upr["poprawia_opis"] and status != "zatwierdzony"
    for s in opis.sekcje(conn, w):
        st.subheader(s["sekcja"])
        if edycja:
            nowy = st.text_area(s["sekcja"], s["tresc"], key=f"op_{w}_{s['sekcja']}", label_visibility="collapsed",
                                height=150)
            if nowy != s["tresc"] and st.button("Zapisz sekcję", key=f"zs_{w}_{s['sekcja']}"):
                opis.popraw(conn, s["sekcja"], nowy, kod, w)
                st.rerun()
        else:
            st.markdown(s["tresc"].replace("\n", "  \n"))
    if edycja and st.button("Wyślij do CFO", type="primary"):
        try:
            opis.wyslij_do_cfo(conn, kod, w)
            st.success("Wysłano do zatwierdzenia.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    zatw = proces.zatwierdzajacy_opis(conn, data)
    if status == "poprawiony":
        st.info(f"Opis czeka na zatwierdzenie: {proces.osoba(conn, zatw)}.")
        if kod == zatw and st.button("Zatwierdź opis", type="primary"):
            try:
                opis.zatwierdz(conn, kod, data, w)
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))
    if status == "zatwierdzony":
        r = opis.sekcje(conn, w)[0]
        st.success(f"Zatwierdzony: {r['zatwierdzil']} ({r['data_zatwierdzenia']}).")
