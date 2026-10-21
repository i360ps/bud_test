"""Etap 5: agregacja, dashboardy, scenariusze, kontrolka (Z1-K4, Z4-K1…K3)."""
import pandas as pd
import pytest

from budzet import agregacja as ag
from budzet import formatki, proces
from budzet.ui_dashboard import tabela_rady


def test_wykonanie_2025_zgodne_z_danymi(conn):
    z = ag.zestawienie(ag.wykonanie(conn, "2025-01", "2025-12"))
    assert round(z["przychody"] / 1000) == 166469
    assert round(z["wynik"] / 1000) == 5550
    assert ag.kontrola_ok(ag.wykonanie(conn, "2025-01", "2025-12"))


def test_kontrola_ok_dla_budzetu(conn):
    assert ag.kontrola_ok(ag.budzet_2027(conn))


def test_z4_k1_sztuczna_niezgodnosc_zapala_kontrolke(conn):
    d = ag.budzet_2027(conn)
    zly = d.iloc[[0]].copy()
    zly["typ"], zly["mpk"], zly["linia"], zly["kwota_pln"] = "koszt_operacyjny", 999, None, 1234.0
    assert not ag.kontrola_ok(pd.concat([d, zly], ignore_index=True))


def test_z1_k4_akceptacja_od_razu_zmienia_sumy(conn):
    przed = ag.zestawienie(ag.budzet_2027(conn, tylko_zaakceptowane=True))["koszty_operacyjne"]
    formatki.przyjmij_podpowiedzi(conn, "MPK_500")
    for pid in {r[0] for r in conn.execute("SELECT pozycja_id FROM wiersz_formatki WHERE formatka_id='MPK_500'")}:
        formatki.ustaw_uzasadnienie(conn, "MPK_500", pid, "test")
    proces.zloz(conn, "MPK_500", "K_IT", "2026-11-12")
    proces.akceptuj(conn, "MPK_500", "CFO", "2026-11-16")
    po = ag.zestawienie(ag.budzet_2027(conn, tylko_zaakceptowane=True))["koszty_operacyjne"]
    assert po > przed
    assert "MPK_500" not in ag.niezaakceptowane(ag.budzet_2027(conn))


def test_z4_k2_kontroler_widzi_spozniona_lcl(conn):
    proces.wyznacz_osobe(conn, "LINIA_LCL", "Kierownik Działu Celnego", "DO")
    proces.aktualizuj_terminy(conn, "2026-11-14")
    r = conn.execute("SELECT flaga_spozniona, czeka_na FROM formatka WHERE formatka_id='LINIA_LCL'").fetchone()
    assert r[0] == 1 and r[1] == "Kierownik Działu Celnego"


def test_z4_k3_przewidywane_2026_szacunek_i_znaczniki(conn):
    p = ag.przewidywane_2026(conn)
    assert set(p.loc[p["miesiac"] >= "2026-10", "status"]) == {"szacunek"}
    assert set(p.loc[p["miesiac"] <= "2026-09", "status"]) == {"wykonanie"}
    b = ag.budzet_2027(conn)
    assert b["zrodlo_liczby"].notna().all()


def test_dwa_poziomy_wyniku_linii(conn):
    d = ag.budzet_2027(conn)
    t = ag.wyniki_linii(d)
    z = ag.zestawienie(d)
    assert t["wynik_po_podziale"].sum() == pytest.approx(z["wynik"], abs=1)
    assert t["marza_brutto"].sum() == pytest.approx(z["marza_brutto"], abs=1)


def test_scenariusze_usd_fracht_wolumen(conn):
    s = ag.scenariusze(ag.budzet_2027(conn))
    assert list(s["scenariusz"]) == ["kurs USD/PLN", "stawki frachtu (USD)", "wolumen"]
    assert (s["+10%"] != 0).all()


def test_flota_w_marzy_transportu(conn):
    d = ag.budzet_2027(conn)
    fl = d[d["flotowa"] == 1]
    assert set(fl["linia"]) == {"TRN"} and set(fl["typ"]) == {"koszt_bezposredni"}


def test_tabela_rady(conn):
    t = tabela_rady(conn)
    assert list(t.columns)[:3] == ["Budżet 2027", "Przewidywane wykonanie 2026 (szacunek)", "Wykonanie 2025"]
    assert round(t.loc["Wynik operacyjny", "Wykonanie 2025"] / 1000) == 5550
