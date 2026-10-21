# Budżet 2027 — Nordmare Spedycja (aplikacja testowa)

Aplikacja do budżetowania zbudowana na podstawie specyfikacji z warsztatu „Przypadki wdrażania AI w Finansach”.
Dane są fikcyjne. Stos: Python, Streamlit, SQLite, pandas, scikit-learn.

## Uruchomienie (Windows, cmd)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py --server.headless true
```

Otwórz `http://localhost:8501`. Przy pierwszym uruchomieniu aplikacja tworzy bazę `budzet.db` (kilka sekund).
Rolę i datę symulacji wybiera się w panelu bocznym (bez logowania).

Testy: `python -m pytest -q tests`

## Dokumenty

- `SPEC.md` — specyfikacja (z orkiestratora), `CLAUDE.md` — instrukcja dla agenta
- `RAPORT-BUDOWY.md` — odbiór: kryteria akceptacji, weryfikacja liczb
- `LUKI-SPECYFIKACJI.md` — niejasności specyfikacji i przyjęte rozwiązania
