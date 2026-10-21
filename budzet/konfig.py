"""Wczytanie plików konfiguracyjnych."""
import os
from pathlib import Path

import yaml

KATALOG_APP = Path(__file__).resolve().parent.parent
KATALOG_DANYCH = KATALOG_APP / "data"
KATALOG_KONFIG = KATALOG_APP / "config"
PLIK_BAZY = Path(os.environ.get("BUDZET_DB", KATALOG_APP / "budzet.db"))


def wczytaj_yaml(nazwa: str) -> dict:
    with open(KATALOG_KONFIG / nazwa, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parametry() -> dict:
    return wczytaj_yaml("parametry.yaml")


def uprawnienia() -> dict:
    return wczytaj_yaml("uprawnienia.yaml")


def miesiace_budzetu(p: dict | None = None) -> list[str]:
    p = p or parametry()
    rok = p["rok_budzetu"]
    return [f"{rok}-{m:02d}" for m in range(1, 13)]
