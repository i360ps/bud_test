# Raport z budowy aplikacji budżetowej

Aplikacja powstała etapami według sekcji 11 specyfikacji. Stos: Python 3.12, Streamlit 1.66, SQLite, pandas, scikit-learn. Po każdym etapie uruchamiałem testy (pytest) i start aplikacji w trybie bez przeglądarki (strona odpowiadała kodem 200). Na koniec: **65 testów, wszystkie przechodzą**. Obejmują one test renderowania każdego ekranu i widoku dla każdej z 13 ról oraz test klikania głównych ścieżek.

## Etapy

| Etap | Gotowe, gdy… | Wynik |
|---|---|---|
| 1 Dane i konfiguracja | import CSV, tabele, 2 pliki konfiguracji, wybór roli, sumy zgodne | ✔ 1605 + 45 wierszy; przychody 2025 = 166 469 tys. zł (spec. podaje 166 470 — zaokrąglenie) |
| 2 Formatki | formatki linii, MPK, floty z obliczeniami, walidacją, ostrzeżeniami | ✔ 13 formatek × 12 miesięcy |
| 3 Proces i uprawnienia | statusy, akceptacje, zastępstwa, eskalacje, historia | ✔ |
| 4 Predykcja | test wsteczny, wybór metody, podpowiedzi, prognoza 2026, punkt kontrolny | ✔ punkt kontrolny: 26,7% / 29,1% |
| 5 Dashboardy | 5 widoków, scenariusze, kontrolka, automatyczna konsolidacja | ✔ kontrolka wykryła przy budowie prawdziwy błąd (brak MPK 500 w konfiguracji) |
| 6 Opis budżetu | projekt opisu, kontrola zgodności, obieg Kontroler → CFO | ✔ projekt ma 638 słów (limit 900) |

## 5.1 Kryteria akceptacji (sekcja 10)

| Kryterium | Wynik | Dowód |
|---|---|---|
| Z1-K1 TEU i stawka dają przychód, koszt, marżę | spełnione | `test_z1_k1_…`: 3000 TEU × 700 USD = 2 100 000 USD × kurs; marża = przychód − koszt |
| Z1-K2 transport bez kursów własnych → ostrzeżenie | spełnione | `test_z1_k2_…`: udział 0 we wszystkich miesiącach → komunikat |
| Z1-K3 odchylenie bez uzasadnienia blokuje złożenie | spełnione | `test_z1_k3_…`, `test_zlozenie_blokowane_przez_walidacje` |
| Z1-K4 akceptacja od razu zmienia sumy | spełnione | `test_z1_k4_…`: suma „tylko zaakceptowane” rośnie po akceptacji MPK_500 |
| Z2-K1 formatka FCL Dyrektora (p.o.) → Prezes | spełnione | `test_z2_k1_…`: Dyrektor nie może zaakceptować, Prezes akceptuje |
| Z2-K2 urlop CFO → Kontroler „w zastępstwie CFO” | spełnione | `test_z2_k2_…`: wpis w historii, `w_zastepstwie_kogo = CFO` |
| Z2-K3 formatka niezłożona do 13.11 → flaga i „czeka na” | spełnione | `test_z2_k3_…`: 14.11 → spóźniona, czeka na Kierownika Działu Celnego |
| Z3-K1 „X TEU × Y USD/TEU (stawka centralna) × kurs, rok temu Z, błąd ± M%” | spełnione | `test_z3_k1_…`; tekst widoczny w formatce |
| Z3-K2 więcej kursów własnych → mniejszy koszt podwykonawców; flota „brak podpowiedzi” | spełnione | `test_z3_k2_…`, `test_flota_bez_podpowiedzi` |
| Z3-K3 kwota dużo wyższa → uzasadnienie i „(decyzja kierownika)” w opisie | spełnione | `test_z3_k3_…` + `test_z3_k3_decyzja_kierownika_w_opisie` |
| Z4-K1 sztuczna niezgodność sum → kontrolka czerwona | spełnione | `test_z4_k1_…` (dopisany koszt na nieistniejące MPK 999) |
| Z4-K2 „formatka LCL spóźniona, czeka na: [osoba]” | spełnione | `test_z4_k2_…`; komunikat w widoku Kontrolera |
| Z4-K3 przewidywane 2026 z etykietą „szacunek”, kwoty ze znacznikiem źródła | spełnione | `test_z4_k3_…` |
| Z5-K1 różnica 1 zł blokuje wysłanie do CFO | spełnione | `test_z5_k1_…`: zmiana kwoty o 1 zł → odmowa; po cofnięciu → wysłano |
| Z5-K2 LCL tylko z modelu i niezaakceptowana → ostrzeżenie i etykieta | spełnione | `test_z5_k2_…` |
| Z5-K3 pierwszy akapit: wynik, kurs, stawki, wolumeny | spełnione | `test_z5_k3_…` |

**16 z 16 spełnionych.** Żadne kryterium nie było „nie do sprawdzenia”.

Uwaga: wszystkie kryteria przechodzą, a mimo to liczby budżetu 2027 są niewiarygodne, dopóki ktoś nie wpisze kosztów floty (luka nr 1). Marża transportu wychodzi 53,6%, a wynik firmy 13,8 mln zł wobec ok. 2,3 mln przewidywanych w 2026. Kryteria sprawdzają mechanikę aplikacji, a nie sensowność liczb.

## 5.2 Trzy losowe liczby z dashboardu sprawdzone ręcznie z CSV

Wybór losowy (wersja danych, rodzaj liczby, linia lub MPK). Ręczne liczenie zrobiłem osobnym skryptem prosto z CSV, bez kodu aplikacji.

| Liczba na dashboardzie | Aplikacja | Ręcznie z CSV | Różnica |
|---|---|---|---|
| Wykonanie 2023 — marża brutto linii CEL (widok CFO / DO) | 3 461 319,10 zł | 3 461 319,10 zł | 0,00 |
| Wykonanie 2023 — marża brutto linii TRN | 2 330 280,22 zł | 2 330 280,22 zł | 0,00 |
| Wykonanie 2024 — marża brutto linii LCL | 2 779 299,65 zł | 2 779 299,65 zł | 0,00 |

Dodatkowo (pułapka P1): aplikacja pokazuje marżę FCL za I–IX 2026 = **8 492 tys. zł**, czyli wartość z danych. Tabela w pliku Zespołu 1 podaje 8 792 tys. Aplikacja liczy z danych, więc błąd tabeli nie przenosi się do budżetu. Nikt jednak nie dostał sygnału, że raport zarządczy był błędny.

## 5.3 Uruchomienie (Windows, cmd)

1. Otwórz folder `test X180\app` w Eksploratorze Windows, kliknij pasek adresu, wpisz `cmd` i naciśnij Enter.
2. Wpisz: `.venv\Scripts\activate` i naciśnij Enter. Na początku wiersza pojawi się `(.venv)`.
3. Wpisz: `streamlit run app.py` i naciśnij Enter.
4. Przeglądarka otworzy się sama. Jeśli nie, wejdź na `http://localhost:8501`.
5. Przy pierwszym uruchomieniu aplikacja przez kilka sekund buduje bazę (`budzet.db`): import danych, predykcja, rozesłanie formatek.
6. W panelu bocznym wybierz rolę (np. „Dyrektor Operacyjny”) i datę symulacji (np. 5.11.2026, żeby zobaczyć zastępstwo CFO).
7. Żeby zacząć od nowa, zamknij aplikację (Ctrl+C w oknie cmd), usuń plik `budzet.db` i uruchom ponownie.

Testy: w tym samym oknie `python -m pytest -q tests`.
