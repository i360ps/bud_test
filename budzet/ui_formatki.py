"""Ekrany formatek (moduły 1–2): wypełnianie, złożenie, akceptacja."""
import pandas as pd
import streamlit as st

from . import formatki as fm
from . import proces

ETYKIETY_ZRODLA = {
    "z_modelu": "z modelu", "zmienione_przez_kierownika": "zmienione przez kierownika",
    "wpisane_recznie": "wpisane ręcznie", "z_modelu_niesprawdzone": "z modelu – niesprawdzone",
}


def zl(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:,.0f} zł".replace(",", " ")


def _opis_formatki(conn, fid):
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    return f"{fid} ({f['status']})"


def ekran_moje_formatki(conn, kod: str, data: str) -> None:
    st.header("Moje formatki")
    lista = proces.formatki_do_wypelnienia(conn, kod, data)
    if not lista:
        st.info("Nie masz formatek do wypełnienia.")
        return
    fid = st.selectbox("Formatka", lista, format_func=lambda f: _opis_formatki(conn, f))
    ekran_formatki(conn, fid, kod, data, edycja=True)


def ekran_formatki(conn, fid: str, kod: str, data: str, edycja: bool) -> None:
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    edytowalna = edycja and f["status"] in fm.EDYTOWALNE
    a = proces.akceptujacy(conn, fid, data)
    st.caption(f"Status: **{f['status']}** · wypełnia: {proces.wypelniajacy(conn, fid, data) or '(wakat — brak osoby)'}"
               f" · akceptuje: {a['osoba']}" + (f" (w zastępstwie {a['w_zastepstwie']})" if a["w_zastepstwie"] else ""))
    for o in fm.ostrzezenia(conn, fid):
        st.warning(o)

    if f["typ_formatki"] == "linia":
        s = fm.podsumowanie(conn, fid)
        c = st.columns(3)
        c[0].metric("Przychody 2027", zl(s["przychod"]))
        c[1].metric("Koszty bezpośrednie 2027", zl(s["koszt_bezposredni"]))
        c[2].metric("Marża brutto 2027", zl(s["marza_brutto"]))

    if f["typ_formatki"] == "flota":
        _ekran_floty(conn, fid, edytowalna)

    d = fm.wiersze(conn, fid)
    pozycje = d[["pozycja_id", "typ", "kategoria"]].drop_duplicates()
    pid = st.selectbox("Pozycja", pozycje["pozycja_id"].tolist(),
                       format_func=lambda p: " · ".join(pozycje.loc[pozycje.pozycja_id == p, ["typ", "kategoria"]].iloc[0]),
                       key=f"poz_{fid}")
    w = d[d.pozycja_id == pid].copy()
    usd = bool(w["frachtowa_usd"].iloc[0])
    wolumenowa = bool(w["wolumenowa"].iloc[0])
    pokaz = pd.DataFrame({
        "miesiac": w["miesiac"],
        "wolumen": w["wolumen"],
        ("stawka_usd" if usd else "stawka"): w["stawka_usd"] if usd else w["stawka"],
        "kwota_pln": w["kwota_pln"],
        "podpowiedz_kwota": w["podpowiedz_kwota"],
        "blad_mape_%": w["blad_mape"],
        "wartosc_2026": w["wartosc_2026"],
        "zrodlo": w["zrodlo_liczby"].map(ETYKIETY_ZRODLA),
    })
    if w["podpowiedz_kwota"].isna().all() and not w["flotowa"].iloc[0]:
        st.caption("Brak podpowiedzi z historii.")
    if w["flotowa"].iloc[0]:
        st.caption("Pola floty: brak podpowiedzi — wpisz sam.")
    miesiac_podp = st.selectbox("Podpowiedź dla miesiąca", w["miesiac"].tolist(), key=f"mp_{fid}_{pid}")
    txt = fm.opis_podpowiedzi(conn, fid, pid, miesiac_podp)
    if txt:
        st.info(f"Podpowiedź {miesiac_podp}: {txt}")
    edytowane = st.data_editor(
        pokaz, hide_index=True, width="stretch", key=f"ed_{fid}_{pid}",
        disabled=not edytowalna,
        column_config={c: st.column_config.Column(disabled=True) for c in
                       ["miesiac", "podpowiedz_kwota", "blad_mape_%", "wartosc_2026", "zrodlo"]
                       + (["kwota_pln"] if wolumenowa else [])
                       + ([] if wolumenowa else ["wolumen", "stawka", "stawka_usd"])},
    )
    uzas = st.text_input("Uzasadnienie (dla całej pozycji)", value=w["uzasadnienie"].dropna().iloc[0]
                         if w["uzasadnienie"].notna().any() else "", key=f"uz_{fid}_{pid}", disabled=not edytowalna)
    if edytowalna:
        c1, c2, c3 = st.columns(3)
        if c1.button("Zapisz pozycję", key=f"zap_{fid}_{pid}"):
            kol_st = "stawka_usd" if usd else "stawka"
            for (_, nowy), (_, stary) in zip(edytowane.iterrows(), pokaz.iterrows()):
                zmiana = any(not _rowne(nowy[k], stary[k]) for k in ("wolumen", kol_st, "kwota_pln"))
                if zmiana:
                    if wolumenowa:
                        fm.zapisz_wiersz(conn, fid, pid, nowy["miesiac"], wolumen=_f(nowy["wolumen"]), stawka=_f(nowy[kol_st]))
                    else:
                        fm.zapisz_wiersz(conn, fid, pid, nowy["miesiac"], kwota=_f(nowy["kwota_pln"]))
            fm.ustaw_uzasadnienie(conn, fid, pid, uzas)
            st.rerun()
        if c2.button("Przyjmij wszystkie podpowiedzi", key=f"prz_{fid}"):
            fm.przyjmij_podpowiedzi(conn, fid)
            st.rerun()
        if c3.button("Złóż formatkę", type="primary", key=f"zl_{fid}"):
            try:
                proces.zloz(conn, fid, kod, data)
                st.success("Formatka złożona.")
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))
        bl = fm.bledy_walidacji(conn, fid)
        if bl:
            st.error(f"Wymagane uzasadnienia ({len(bl)}): " + "; ".join(bl[:5]) + (" …" if len(bl) > 5 else ""))
    with st.expander("Historia formatki"):
        st.dataframe(proces.historia(conn, fid), hide_index=True, width="stretch")


def _ekran_floty(conn, fid, edytowalna):
    from . import baza
    st.subheader("Dane floty")
    d = baza.df(conn, "SELECT miesiac, liczba_zestawow, rata_leasingu, przebieg_km, liczba_etatow, kursy_wlasne,"
                      " kursy_podwykonawcow, udzial_kursow_wlasnych FROM flota_miesiac WHERE formatka_id=? ORDER BY miesiac",
                (fid,))
    ed = st.data_editor(d, hide_index=True, width="stretch", key=f"flota_{fid}", disabled=not edytowalna,
                        column_config={c: st.column_config.Column(disabled=True) for c in
                                       ["miesiac", "rata_leasingu", "przebieg_km", "kursy_wlasne", "kursy_podwykonawcow"]})
    if edytowalna and st.button("Zapisz dane floty"):
        for (_, n), (_, s) in zip(ed.iterrows(), d.iterrows()):
            if any(not _rowne(n[k], s[k]) for k in ("liczba_zestawow", "udzial_kursow_wlasnych", "liczba_etatow")):
                fm.ustaw_flote(conn, n["miesiac"], int(n["liczba_zestawow"]), float(n["udzial_kursow_wlasnych"]),
                               _f(n["liczba_etatow"]), fid)
        st.rerun()


def ekran_akceptacji(conn, kod: str, data: str) -> None:
    st.header("Do akceptacji")
    lista = proces.formatki_do_akceptacji(conn, kod, data)
    if not lista:
        st.info("Brak formatek czekających na Twoją akceptację.")
        return
    fid = st.selectbox("Formatka", lista)
    a = proces.akceptujacy(conn, fid, data)
    if a["w_zastepstwie"]:
        st.info(f"Akceptujesz w zastępstwie: {a['w_zastepstwie']}.")
    d = fm.wiersze(conn, fid)
    odch = d[d["uzasadnienie"].notna() | (d["zrodlo_liczby"] == "zmienione_przez_kierownika")]
    st.subheader("Odchylenia i uzasadnienia")
    st.dataframe(odch[["kategoria", "miesiac", "kwota_pln", "podpowiedz_kwota", "wartosc_2026", "zrodlo_liczby",
                       "uzasadnienie"]], hide_index=True, width="stretch")
    ekran_formatki(conn, fid, kod, data, edycja=False)
    c1, c2 = st.columns(2)
    if c1.button("Akceptuj", type="primary"):
        proces.akceptuj(conn, fid, kod, data)
        st.rerun()
    kom = c2.text_input("Komentarz do odrzucenia")
    if c2.button("Odrzuć"):
        try:
            proces.odrzuc(conn, fid, kod, kom, data)
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def ekran_wakatow(conn, kod: str, data: str) -> None:
    st.header("Formatki wakatów")
    from . import konfig
    upr = konfig.uprawnienia()
    osoby = sorted({s["osoba"] for s in upr["stanowiska"].values() if s.get("osoba")} - {"Zarząd", "Rada Nadzorcza"})
    for f in conn.execute("SELECT * FROM formatka").fetchall():
        if proces.jest_wakat(conn, f["stanowisko_wypelnia"], f["termin_zlozenia"]):
            c1, c2 = st.columns([2, 3])
            c1.write(f"**{f['formatka_id']}** — wyznaczona: {f['osoba_wyznaczona'] or 'brak'}")
            wyb = c2.selectbox("Wyznacz osobę", osoby, key=f"wyzn_{f['formatka_id']}")
            if c2.button("Wyznacz", key=f"bw_{f['formatka_id']}"):
                proces.wyznacz_osobe(conn, f["formatka_id"], wyb, kod)
                st.rerun()


def _rowne(a, b) -> bool:
    if (a is None or pd.isna(a)) and (b is None or pd.isna(b)):
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def _f(x):
    return None if x is None or pd.isna(x) else float(x)
