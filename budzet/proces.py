"""Moduł 2 — decydenci, akceptacje, zastępstwa i terminy (Z2-R1…R13, D5–D11).
Reguły (kto wypełnia, kto akceptuje, zastępstwa, nieobecności) pochodzą z config/uprawnienia.yaml."""
from datetime import date, datetime, timedelta

from . import formatki as fm
from . import konfig


def data_symulacji(conn=None) -> str:
    return str(konfig.parametry()["data_symulacji"])


def _d(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def stanowisko(conn, kod: str):
    return conn.execute("SELECT * FROM stanowisko WHERE kod=?", (kod,)).fetchone()


def osoba(conn, kod: str) -> str | None:
    s = stanowisko(conn, kod)
    return None if s is None else s["osoba"]


def jest_wakat(conn, kod: str, data: str | None = None) -> bool:
    """Wakat: brak osoby, osoba już odeszła albo jeszcze nie przyszła."""
    data = data or data_symulacji()
    s = stanowisko(conn, kod)
    if s["osoba"] is None:
        return not (s["data_przyjscia"] and _d(data) >= _d(s["data_przyjscia"]))
    if s["data_odejscia"] and _d(data) > _d(s["data_odejscia"]):
        return True
    return False


def nieobecny(conn, kod: str, data: str | None = None) -> bool:
    data = _d(data or data_symulacji())
    for n in conn.execute("SELECT * FROM nieobecnosc WHERE stanowisko_kod=?", (kod,)):
        if _d(n["data_od"]) <= data <= _d(n["data_do"]):
            return True
    return False


def zastepca(conn, kod: str, zakres: str = "budzet") -> str | None:
    r = conn.execute("SELECT zastepca_kod FROM zastepstwo WHERE stanowisko_kod=? AND zakres=?", (kod, zakres)).fetchone()
    return None if r is None else r[0]


# ---------------------------------------------------------------- kto wypełnia
def wypelniajacy(conn, fid: str, data: str | None = None) -> str | None:
    """Osoba, która wypełnia formatkę: kierownik, a przy wakacie osoba wyznaczona (Z2-R8)."""
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    if not jest_wakat(conn, f["stanowisko_wypelnia"], data):
        return osoba(conn, f["stanowisko_wypelnia"])
    return f["osoba_wyznaczona"]


def wyznacz_osobe(conn, fid: str, osoba_wyzn: str, kto_kod: str) -> None:
    """D5: osobę do formatki wakatu wyznacza Dyrektor Operacyjny.
    Można to zrobić z wyprzedzeniem: liczy się wakat w dniu terminu złożenia (LCL: odejście 31.10)."""
    if kto_kod != konfig.uprawnienia()["wyznacza_osoby_wakatow"]:
        raise PermissionError("Osoby do formatek wakatów wyznacza Dyrektor Operacyjny (D5).")
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    if not jest_wakat(conn, f["stanowisko_wypelnia"], f["termin_zlozenia"]):
        raise ValueError("To stanowisko nie jest wakatem.")
    conn.execute("UPDATE formatka SET osoba_wyznaczona=? WHERE formatka_id=?", (osoba_wyzn, fid))
    _historia(conn, fid, "wyznaczenie osoby", osoba(conn, kto_kod), kto_kod, None, osoba_wyzn)
    conn.commit()


def formatki_do_wypelnienia(conn, kod: str, data: str | None = None) -> list[str]:
    os_ = osoba(conn, kod)
    return [r[0] for r in conn.execute("SELECT formatka_id FROM formatka ORDER BY formatka_id")
            if os_ is not None and wypelniajacy(conn, r[0], data) == os_]


# ---------------------------------------------------------------- kto akceptuje
def akceptujacy(conn, fid: str, data: str | None = None) -> dict:
    """Zwraca {'kod', 'osoba', 'w_zastepstwie'}.
    1) akceptujący z przypisania; 2) nikt nie akceptuje własnej formatki → przełożony (Z2-R6);
    3) nieobecny → zastępca w sprawach budżetu (Z2-R7, D6)."""
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    kod = f["stanowisko_akceptuje"]
    autor = f["zlozyl"] or wypelniajacy(conn, fid, data)
    while autor is not None and osoba(conn, kod) == autor:
        kod = stanowisko(conn, kod)["przelozony_kod"]
    w_zast = None
    if nieobecny(conn, kod, data):
        z = zastepca(conn, kod)
        if z and osoba(conn, z) != autor:
            w_zast, kod = kod, z
    return {"kod": kod, "osoba": osoba(conn, kod), "w_zastepstwie": w_zast}


def formatki_do_akceptacji(conn, kod: str, data: str | None = None) -> list[str]:
    return [r[0] for r in conn.execute("SELECT formatka_id FROM formatka WHERE status='zlozona' ORDER BY formatka_id")
            if akceptujacy(conn, r[0], data)["kod"] == kod]


def moze_ustalac_zalozenia(conn, kod: str, data: str | None = None) -> bool:
    """Kurs i stawki: CFO, w zastępstwie Kontroler (D16)."""
    upr = konfig.uprawnienia()["uprawnienia"]["ustala_kurs_i_stawki"]
    if kod in upr:
        return True
    return any(nieobecny(conn, k, data) and zastepca(conn, k) == kod for k in upr)


def zatwierdzajacy_opis(conn, data: str | None = None) -> str:
    """D13 + D7: opis zatwierdza CFO; gdy nieobecny – Prezes (nie Kontroler, który poprawiał opis)."""
    kod = konfig.uprawnienia()["uprawnienia"]["zatwierdza_opis"][0]
    if nieobecny(conn, kod, data):
        return stanowisko(conn, kod)["przelozony_kod"]
    return kod


# ---------------------------------------------------------------- akcje
def _historia(conn, fid, akcja, osoba_, kod, w_zast, komentarz=None):
    conn.execute("INSERT INTO historia VALUES (?,?,?,?,?,?,?)",
                 (fid, akcja, osoba_, kod, w_zast, datetime.now().isoformat(timespec="seconds") + f" (dzień symulacji {data_symulacji()})",
                  komentarz))


def zloz(conn, fid: str, kod: str, data: str | None = None) -> None:
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    if f["status"] not in fm.EDYTOWALNE:
        raise PermissionError("Formatka jest już złożona.")
    if wypelniajacy(conn, fid, data) != osoba(conn, kod):
        raise PermissionError("Tę formatkę wypełnia inna osoba.")
    bledy = fm.bledy_walidacji(conn, fid)
    if bledy:
        raise ValueError("Nie można złożyć formatki: " + "; ".join(bledy[:5]))
    conn.execute("UPDATE formatka SET status='zlozona', zlozyl=? WHERE formatka_id=?", (osoba(conn, kod), fid))
    _historia(conn, fid, "złożenie", osoba(conn, kod), kod, None)
    conn.commit()
    aktualizuj_terminy(conn, data)


def akceptuj(conn, fid: str, kod: str, data: str | None = None) -> None:
    _decyzja(conn, fid, kod, "zaakceptowana", "akceptacja", None, data)


def odrzuc(conn, fid: str, kod: str, komentarz: str, data: str | None = None) -> None:
    if not komentarz:
        raise ValueError("Odrzucenie wymaga komentarza.")
    _decyzja(conn, fid, kod, "odrzucona", "odrzucenie", komentarz, data)


def _decyzja(conn, fid, kod, status, akcja, komentarz, data):
    f = conn.execute("SELECT * FROM formatka WHERE formatka_id=?", (fid,)).fetchone()
    if f["status"] != "zlozona":
        raise PermissionError("Akceptować lub odrzucać można tylko formatkę złożoną.")
    a = akceptujacy(conn, fid, data)
    if a["kod"] != kod:
        raise PermissionError(f"Tę formatkę akceptuje: {a['osoba']}.")
    conn.execute("UPDATE formatka SET status=? WHERE formatka_id=?", (status, fid))
    if status == "odrzucona":
        conn.execute("UPDATE formatka SET zlozyl=NULL WHERE formatka_id=?", (fid,))
    _historia(conn, fid, akcja, osoba(conn, kod), kod, a["w_zastepstwie"], komentarz)
    conn.commit()
    aktualizuj_terminy(conn, data)


# ---------------------------------------------------------------- terminy i eskalacja (D9, D10)
def aktualizuj_terminy(conn, data: str | None = None) -> None:
    data_s = data or data_symulacji()
    dzis = _d(data_s)
    dni = konfig.parametry()["dni_eskalacji"]
    conn.execute("DELETE FROM komunikat")
    for f in conn.execute("SELECT * FROM formatka").fetchall():
        fid = f["formatka_id"]
        termin, kto = None, None
        if f["status"] in fm.EDYTOWALNE:
            termin, kto = _d(f["termin_zlozenia"]), wypelniajacy(conn, fid, data_s) or "(brak osoby — wyznacz)"
        elif f["status"] == "zlozona":
            termin, kto = _d(f["termin_akceptacji"]), akceptujacy(conn, fid, data_s)["osoba"]
        spozniona = termin is not None and dzis > termin
        conn.execute("UPDATE formatka SET flaga_spozniona=?, czeka_na=? WHERE formatka_id=?",
                     (int(spozniona), kto, fid))
        if termin is None:
            continue
        if dzis == termin:
            conn.execute("INSERT INTO komunikat VALUES (?,?,?,?)",
                         (data_s, kto, f"Dziś mija termin dla formatki {fid}.", fid))
        if dzis >= termin + timedelta(days=dni):
            przel = _przelozony_osoby(conn, kto)
            for odbiorca in {przel, osoba(conn, "KONTROLER")} - {None}:
                conn.execute("INSERT INTO komunikat VALUES (?,?,?,?)",
                             (data_s, odbiorca, f"Eskalacja: formatka {fid} spóźniona, czeka na: {kto}.", fid))
    conn.commit()


def _przelozony_osoby(conn, osoba_):
    r = conn.execute("SELECT przelozony_kod FROM stanowisko WHERE osoba=? ORDER BY kod", (osoba_,)).fetchone()
    return None if r is None or r[0] is None else osoba(conn, r[0])


def historia(conn, fid: str | None = None):
    from . import baza
    if fid:
        return baza.df(conn, "SELECT * FROM historia WHERE formatka_id=? ORDER BY rowid", (fid,))
    return baza.df(conn, "SELECT * FROM historia ORDER BY rowid")
