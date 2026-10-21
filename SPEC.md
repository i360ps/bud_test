# Specyfikacja: aplikacja do budżetowania 2027 — Nordmare Spedycja

## 0. Instrukcja dla agenta (zapisz jako CLAUDE.md)
- Stos: Python, Streamlit (interfejs i dashboardy), SQLite (jeden plik bazy), pandas, scikit-learn. Uruchamianie lokalne jednym poleceniem (`streamlit run app.py`). Logowania nie ma: rolę i osobę wybiera się z listy w panelu bocznym. Dane fikcyjne wczytujesz z folderu `data/`.
- Buduj etapami (sekcja 11). Po każdym etapie uruchom aplikację i opisz, co działa, a czego jeszcze nie ma.
- Wszystkie reguły uprawnień, przypisań formatek i zastępstw trzymaj w jednym pliku `config/uprawnienia.yaml`. Parametry liczbowe trzymaj w `config/parametry.yaml`.
- Gdy specyfikacja jest niejasna, zapytaj, nie zgaduj. Nie dodawaj funkcji spoza specyfikacji.
- Interfejs po polsku; kwoty w PLN, chyba że pole ma `usd` w nazwie.

## 1. Cel aplikacji
Aplikacja zastępuje pliki Excel przy budżecie 2027. Kierownicy wypełniają jednakowe miesięczne formatki (linii, MPK, floty) z podpowiedziami z danych historycznych. Przełożeni akceptują formatki, a każda akceptacja zostaje w historii. Budżet konsoliduje się automatycznie, a dashboardy pokazują marżę brutto, czyli główny miernik firmy. Na końcu aplikacja tworzy projekt opisu budżetu dla Zarządu i Rady Nadzorczej, a każda liczba w opisie zgadza się z tabelami.

## 2. Role i uprawnienia
| Rola (stanowisko) | Może |
|---|---|
| Kierownik linii lub działu (FCL, LCL, celny, dowozów, Dyrektor Handlowy, Kierownik IT) | wypełnia i składa swoje formatki linii i MPK, zmienia podpowiedzi, wpisuje uzasadnienia |
| Osoba wyznaczona | wypełnia formatkę wakatu (LCL od 31.10.2026, flota do zatrudnienia Kierownika Floty), wyznaczana przez Dyrektora Operacyjnego (D5) |
| Kierownik Floty (od 02.2027) | przejmuje formatkę floty |
| Dyrektor Operacyjny | akceptuje lub odrzuca formatki linii, MPK 410–440 i floty, wyznacza osoby do wakatów |
| CFO | akceptuje lub odrzuca formatki MPK 100, 200, 300 i 500; ustala kurs USD/PLN i stawki frachtu; zatwierdza opis |
| Kontroler Finansowy | widzi status wszystkich formatek, uruchamia predykcję, poprawia opis i pisze wnioski; w sprawach budżetu zastępuje CFO (D6), ale nie zatwierdza własnej konsolidacji ani opisu (D7) |
| Prezes | akceptuje formatki, gdy akceptujący byłby ich autorem (Z2-R6); zatwierdza opis w zastępstwie CFO (D13); ma swój widok |
| Zarząd, Rada Nadzorcza | tylko odczyt widoków i opisu |

Przypisanie formatek (`config/uprawnienia.yaml`):

| Formatka | Wypełnia | Akceptuje |
|---|---|---|
| Linia FCL + MPK 410 | Kierownik Działu Spedycji Pełnokontenerowej | Dyrektor Operacyjny → Prezes, gdy to ta sama osoba |
| Linia LCL + MPK 420 | Kierownik Działu Drobnicy, a przy wakacie osoba wyznaczona | Dyrektor Operacyjny |
| Linia CEL + MPK 430 | Kierownik Działu Celnego | Dyrektor Operacyjny |
| Linia TRN + MPK 440 | Kierownik Działu Dowozów | Dyrektor Operacyjny |
| Flota (MPK 450) | osoba wyznaczona, potem Kierownik Floty | Dyrektor Operacyjny (D1) |
| MPK 100 | Prezes [DOMYŚLNE] | CFO |
| MPK 200 | Kontroler Finansowy [DOMYŚLNE] | CFO |
| MPK 300 | Dyrektor Handlowy | CFO |
| MPK 500 | Kierownik IT | CFO |

Nieobecność akceptującego (tabela `nieobecnosc`) przekazuje akceptację zastępcy z wpisem „w zastępstwie” w historii.

## 3. Model danych (SQLite)
| Tabela | Pola (typ) | Opis | Źródło |
|---|---|---|---|
| stanowisko | kod (tekst), nazwa, osoba, przelozony_kod | struktura organizacyjna | Z2 |
| nieobecnosc | stanowisko_kod, data_od (data), data_do (data) | np. CFO 2–13.11.2026 | Z2 |
| zastepstwo | stanowisko_kod, zastepca_kod, zakres | CFO → Kontroler (budżet) | Z2, D6 |
| mpk | mpk (liczba), nazwa, linia | 100, 200, 300, 410→FCL, 420→LCL, 430→CEL, 440→TRN, 450 Flota→TRN, 500 | Z1, D2, D22 |
| pozycja | pozycja_id, typ (przychod/koszt_bezposredni/koszt_operacyjny), linia, mpk, kategoria, jednostka, wolumenowa (bool), frachtowa_usd (bool), jednorazowa (bool) | lista pozycji z ewidencji plus pozycje floty | Z1 |
| formatka | formatka_id, typ_formatki (linia/mpk/flota), linia, mpk, stanowisko_wypelnia, osoba_wyznaczona, stanowisko_akceptuje, status, flaga_spozniona (bool), czeka_na, termin_zlozenia, termin_akceptacji | nagłówek formatki | Z1, Z2 |
| wiersz_formatki | formatka_id, pozycja_id, miesiac (RRRR-MM), wolumen, stawka, stawka_usd, kwota_usd, kwota_pln, podpowiedz_kwota, podpowiedz_wolumen, podpowiedz_stawka, metoda, blad_mape, wartosc_rok_poprzedni, wartosc_2026, zrodlo_liczby, uzasadnienie | wiersz miesięczny | Z1, Z3 |
| flota_miesiac | formatka_id, miesiac, liczba_zestawow, rata_leasingu, przebieg_km, liczba_etatow, kursy_wlasne, kursy_podwykonawcow, udzial_kursow_wlasnych | dane floty | Z1, D4 |
| historia | formatka_id, akcja, osoba, stanowisko, w_zastepstwie_kogo, data_czas, komentarz | ślad złożeń, akceptacji, odrzuceń | Z2 |
| zalozenia | nazwa, miesiac, wartosc, ustalil, data, domyslne (bool) | kurs_usd_pln_budzet, stawka_centralna_usd (każda pozycja frachtowa) | Z1, Z3, D14–D17 |
| wykonanie | miesiac, typ, linia, mpk, kategoria, kwota_pln, wylaczone_z_uczenia (bool), powod | z `dane_finansowe_miesieczne.csv` | plik |
| wolumeny | miesiac, fcl_teu, lcl_m3, zgloszenia_celne, kursy_transport, kurs_usd_pln | z `wolumeny_miesieczne.csv` | plik |
| test_wsteczny | pozycja_id, metoda, mape | wyniki testu | Z3 |
| prognoza | pozycja_id, miesiac, metoda, kwota_pln, wolumen, stawka, mape, wersja_danych (prognoza_2026/podpowiedz_2027) | wynik predykcji | Z3, Z4 |
| budzet_2026 | okres (rok/I–IX), miara, kwota_pln | z opisu przypadku Z4 (`data/budzet_2026.csv`) | plik, D29 |
| opis | opis_id, wersja, sekcja, tresc, status_opisu (projekt/poprawiony/zatwierdzony), zatwierdzil, data_zatwierdzenia, zgodnosc_liczb (bool), lista_ostrzezen | opis budżetu | Z5 |

Słowniki:
- `zrodlo_liczby`: z_modelu, zmienione_przez_kierownika, wpisane_recznie, z_modelu_niesprawdzone (D18).
- `status`: w_przygotowaniu, zlozona, zaakceptowana, odrzucona (D8).

Parametry (`config/parametry.yaml`):
- prog_uzasadnienia_proc = 10% [DOMYŚLNE], prog_uzasadnienia_kwota = 50 000 zł [DOMYŚLNE];
- dni_eskalacji = 2 [DOMYŚLNE];
- klucz_podzialu = marza_brutto (D21);
- mpk_floty = 450 [DOMYŚLNE];
- flota_koszt_bezposredni = tak (D3);
- rata_leasingu = 9 400 zł; zestawy_docelowe = 14; dostawy zestawów 01: 6, 02: 4, 03: 4; cel_kursow_wlasnych = 60%; przebieg_km_na_zestaw = 9 000;
- scenariusz_proc = 10%;
- limit_slow_opisu = 900 [DOMYŚLNE];
- harmonogram: 30.10, 13.11, 20.11, 27.11, 4.12, 15.12.2026;
- data_symulacji (data „dzisiejsza” do testów terminów) [SPÓJNOŚĆ].

## 4. Proces budżetowy
1. **Przygotowanie (Kontroler, CFO).** Kontroler importuje dane i uruchamia predykcję. CFO wpisuje kurs i stawki frachtu. Dopóki tego nie zrobi, obowiązuje kurs z 09.2026 i ostatnia stawka z historii, oznaczone jako domyślne (D17).
2. **Rozesłanie (30.10).** Aplikacja tworzy formatki w statusie `w_przygotowaniu` z podpowiedziami. Wiersze mają znacznik `z_modelu_niesprawdzone`. Dyrektor Operacyjny wyznacza osoby do formatek LCL i floty (formatkę floty po zatrudnieniu przejmuje Kierownik Floty).
3. **Wypełnianie (do 13.11).** Wypełniający przyjmuje podpowiedź (znacznik zmienia się na `z_modelu`), zmienia ją (`zmienione_przez_kierownika`) albo wpisuje własną wartość (`wpisane_recznie`). Złożenie zmienia status na `zlozona`, ale tylko gdy walidacja przejdzie (Z1-R5).
4. **Akceptacja (do 20.11).** Akceptujący, wyznaczony według sekcji 2, widzi uzasadnienia i odchylenia. Akceptacja daje status `zaakceptowana`. Odrzucenie wymaga komentarza i ustawia `odrzucona`, a formatka wraca do edycji (`w_przygotowaniu`). Każda akcja trafia do `historia`.
5. **Spóźnienie.** Po terminie aplikacja ustawia `flaga_spozniona`, a `czeka_na` wskazuje osobę, która ma następny ruch (D9). W dniu terminu aplikacja pokazuje komunikat, a po `dni_eskalacji` informuje przełożonego i Kontrolera (D10).
6. **Konsolidacja (ciągła, do 27.11).** Sumy liczą się automatycznie z formatek w każdym statusie (Z4-R6).
7. **Opis (do 27.11).** Aplikacja tworzy projekt, Kontroler go poprawia i pisze wnioski, potem następuje kontrola zgodności liczb. Zatwierdza CFO, a w zastępstwie Prezes.
8. **Zarząd (4.12) i Rada (15.12).** Odczytują widoki i opis. Formatki niezaakceptowane są oznaczone (D11).

## 5. Moduły i reguły

### Moduł 1 — Schemat i formatki
- Z1-R1 Układ: linia × MPK × pozycja × miesiąc 2027; tylko miesięcznie. [ZESPÓŁ]
- Z1-R2 Główna miara to marża brutto = przychody − koszty bezpośrednie. [PLIK]
- Z1-R3 Pozycje wolumenowe: `kwota_pln = wolumen × stawka`. Dla pozycji frachtowych `kwota_usd = wolumen × stawka_usd`, a `kwota_pln = kwota_usd × kurs_usd_pln_budzet`. [ZESPÓŁ] [DECYZJA PROWADZĄCEGO D15]
- Z1-R4 Kurs USD/PLN ustala CFO, a w zastępstwie Kontroler. Kierownik go nie zmienia. [ZESPÓŁ] [D16]
- Z1-R5 Złożenie formatki jest zablokowane, gdy wiersz odchyla się od podpowiedzi albo od `wartosc_2026` o więcej niż próg (oba warunki: procentowy i kwotowy), a nie ma uzasadnienia. [ZESPÓŁ] [D19, D20]
- Z1-R6 Każdy wiersz ma `zrodlo_liczby`. [ZESPÓŁ] [D18]
- Z1-R7 Typy formatek: linia, MPK, flota. Jedna osoba może mieć kilka formatek. [ZESPÓŁ]
- Z1-R8 Formatka floty ma pola `flota_miesiac`. Plan zestawów: 6 w styczniu, 10 w lutym, 14 od marca. [PLIK]
- Z1-R9 `rata_leasingu = liczba_zestawow × 9 400 zł`; pole liczone, nieedytowalne. [ZESPÓŁ]
- Z1-R10 Flota ma osobne MPK 450 i osobne pozycje (leasing, paliwo, opony, serwis, ubezpieczenia, opłaty drogowe, wynagrodzenia kierowców i dyspozytorów). Koszty floty są kosztem bezpośrednim linii TRN. [ZESPÓŁ] [PLIK] [D2, D3]
- Z1-R11 `udzial_kursow_wlasnych = zestawy w miesiącu / 14 × 60%`; wartość można zmienić (D4). Wtedy `kursy_wlasne = kursy TRN × udzial`, a `kursy_podwykonawcow = kursy TRN − kursy_wlasne`. Koszty floty poza leasingiem wpisuje się ręcznie albo jako kursy × koszt na kurs. [ZESPÓŁ] [D4]
- Z1-R12 Formatka TRN na 2027 bez kursów własnych pokazuje ostrzeżenie. [ZESPÓŁ]
- Z1-R13 Koszty MPK 100, 200, 300 i 500 nie wchodzą do marży brutto. Wynik linii po podziale liczymy kluczem z parametru. [ZESPÓŁ] [D21]
- Z1-R14 Licencja IT to osobna pozycja na MPK 500 w styczniu. [PLIK]
- Z1-R15 Porównania lat kosztów operacyjnych transportu liczymy na sumie MPK 410+440, z adnotacją. [ZESPÓŁ] [D23]

### Moduł 2 — Decydenci
- Z2-R1 Formatkę przygotowuje kierownik działu. [PLIK §2]
- Z2-R2 Formatki operacyjne akceptuje Dyrektor Operacyjny, pozostałe CFO. [PLIK §3]
- Z2-R3 Kontroler konsoliduje, Zarząd przyjmuje uchwałą, Rada zatwierdza. [PLIK §4–5]
- Z2-R4 Opis poprawia Kontroler, zatwierdza CFO. [PLIK] [D13]
- Z2-R5 Progi z polityki zakupowej nie dotyczą formatek. [D12]
- Z2-R6 Nikt nie akceptuje własnej formatki; akceptacja idzie do przełożonego akceptującego. [ZESPÓŁ]
- Z2-R7 W sprawach budżetu CFO zastępuje Kontroler (bez własnej konsolidacji i opisu). [PLIK, opis stanowisk] [D6, D7]
- Z2-R8 Wakat: wypełnia osoba wyznaczona przez Dyrektora Operacyjnego, akceptuje przełożony wakatu. [ZESPÓŁ] [D5]
- Z2-R9 Formatka bez kierownika startuje z podpowiedzi oznaczonych `z_modelu_niesprawdzone`; flota nie ma podpowiedzi. [ZESPÓŁ]
- Z2-R10 Stawki frachtu ustala CFO, a kierownik może je zmienić z uzasadnieniem. [D14]
- Z2-R11 Akceptujący widzi uzasadnienia i odchylenia. [ZESPÓŁ]
- Z2-R12 Spóźnienie: komunikat → eskalacja → w sumach etykieta „niezaakceptowana”. [ZESPÓŁ] [D9–D11]
- Z2-R13 Reguły są przypisane do stanowisk. [ZESPÓŁ]

### Moduł 3 — Predykcja (szczegóły w sekcji 6)
- Z3-R1 Test wsteczny i MAPE. [PLIK]
- Z3-R2 Model czynnikowy dla pozycji wolumenowych. [PLIK] [ZESPÓŁ]
- Z3-R3 Dla pozycji frachtowych stawka centralna CFO. [ZESPÓŁ] [D14]
- Z3-R4 Pozycje jednorazowe (licencja): powtórka roku w styczniu. [ZESPÓŁ]
- Z3-R5 Anomalie wyłączone z uczenia. [D24]
- Z3-R6 MPK 410+440 łączone w uczeniu. [ZESPÓŁ]
- Z3-R7 Koszt podwykonawców TRN = kursy_podwykonawcow × stawka podwykonawcy. [ZESPÓŁ]
- Z3-R8 Pola floty pokazują napis „brak podpowiedzi — wpisz sam”. [ZESPÓŁ]
- Z3-R9 Obok podpowiedzi formatka pokazuje: wolumen, stawkę, rok poprzedni i ± MAPE. [ZESPÓŁ] [D26]
- Z3-R10 Prognoza X–XII 2026 liczona tą samą metodą. [ZESPÓŁ]

### Moduł 4 — Agregacja i dashboardy (szczegóły w sekcji 7)
- Z4-R1 Dwie ścieżki: formatki linii → linia → firma oraz formatki MPK → MPK → firma. [ZESPÓŁ]
- Z4-R2 Jedno źródło liczb dla ekranów i opisu. [ZESPÓŁ]
- Z4-R3 Dwa poziomy wyniku linii: marża brutto minus MPK operacyjne linii oraz wynik po podziale kosztów wspólnych. [ZESPÓŁ] [D21, D22]
- Z4-R4 Suma wszystkich formatek z etykietą „niezaakceptowana” oraz obok suma „tylko zaakceptowane”. [ZESPÓŁ] [D27]
- Z4-R5 Kontrolka zgodności na każdym ekranie: Σ marża linii − Σ koszty MPK = wynik firmy, a Σ MPK = koszty operacyjne razem. Każda różnica świeci na czerwono. [ZESPÓŁ] [SPÓJNOŚĆ]
- Z4-R6 Transport porównywany łącznym kosztem kursów (podwykonawcy + flota) i kosztem na kurs, osobno dla kursów własnych i obcych. [ZESPÓŁ]
- Z4-R7 Scenariusze USD, fracht i wolumen ±10%. [PLIK] [D28]
- Z4-R8 Przewidywane wykonanie 2026 = wykonanie I–IX + prognoza X–XII z etykietą „szacunek”. [ZESPÓŁ] [D27]

### Moduł 5 — Opis budżetu (szczegóły w sekcji 8)
- Z5-R1 Projekt powstaje po konsolidacji z szablonu regułowego, bez modelu językowego. [PLIK] [D31]
- Z5-R2 Maks. `limit_slow_opisu`, zaczyna się od wniosków. [PLIK] [D33]
- Z5-R3 Opis nie wprowadza liczb spoza tabel; niezgodność choćby o 1 zł blokuje wysłanie do CFO. [PLIK]
- Z5-R4 Założenia jawne, każde z wpływem na wynik ze scenariuszy. [PLIK] [ZESPÓŁ]
- Z5-R5 Liczby z modelu i z decyzji kierowników są rozróżnione, przy prognozie podany jest MAPE. [PLIK]
- Z5-R6 Ryzyka podane w liczbach. [PLIK]
- Z5-R7 Osobny akapit o flocie. [PLIK]
- Z5-R8 Ostrzeżenia według sekcji 8. [ZESPÓŁ] [PLIK]
- Z5-R9 Wnioski pisze Kontroler. [D32]

## 6. Predykcja
- **Dane:** `wykonanie` i `wolumeny` 01.2023–09.2026, bez wierszy `wylaczone_z_uczenia`. MPK 410 i 440 sumowane.
- **Metody do porównania:** (1) powtórka roku, (2) średnia z 12 mies., (3) trend liniowy z sezonowością miesięczną (scikit-learn), (4) model czynnikowy: wolumen × stawka, gdzie wolumen i stawkę prognozujemy osobno metodami 1–3.
- **Test:** uczenie do 09.2025, prognoza 10.2025–09.2026, miara MAPE. Wyniki w `test_wsteczny`, widoczne dla Kontrolera. Punkt kontrolny dla przychodów FCL razem: powtórka 26,7%, średnia 29,1%.
- **Wybór metody:** dla każdej pozycji osobno metoda o najniższym MAPE (D25). Wyjątki: pozycje jednorazowe biorą powtórkę roku (Z3-R4), a flota nie ma podpowiedzi.
- **Podpowiedź 2027:** model uczony do 09.2026. Dla pozycji frachtowych stawka pochodzi z `zalozenia`, a nie z modelu. Dla TRN koszt podwykonawców liczymy tylko od kursów obcych (Z1-R11).
- **Prognoza 2026:** X–XII 2026 wybraną metodą, przy czym stawka pochodzi z historii.
- **Niepewność:** podpowiedź ± MAPE wybranej metody (D26).

## 7. Dashboardy
- **Prezes:** wolumeny (TEU, m³, zgłoszenia, kursy) i przychody na pierwszym ekranie.
- **CFO:** marża brutto linii, koszty według MPK, wynik, wynik linii po podziale kosztów wspólnych, scenariusze ±10% (USD, fracht, wolumen).
- **Dyrektor Operacyjny:** marża linii i koszty MPK 410–450, bez kosztów wspólnych.
- **Rada:** jedna strona: budżet 2027, przewidywane wykonanie 2026 („szacunek”), wykonanie 2025, zmiany, ryzyka; porównanie z budżetem 2026 tylko rocznie i za I–IX (D29).
- **Kontroler:** tabela formatek: status, flaga spóźnienia, `czeka_na`, akceptujący, historia.
- **Wskaźniki:** przychody, koszty bezpośrednie, marża brutto (zł i %), koszty operacyjne, wynik, wynik na jednostkę wolumenu, koszt na kurs (własny i obcy), udział kwot według `zrodlo_liczby`.
- **Filtry:** okres (miesiąc, kwartał, rok), linia, MPK, wersja danych, „tylko zaakceptowane”.
- Na każdym ekranie kontrolka zgodności (Z4-R5).

## 8. Opis budżetu
- **Struktura:** wnioski (wynik operacyjny, marża; sekcja na tekst Kontrolera z wstawionymi liczbami) → założenia (kurs, stawki, wolumeny, wpływ ±10% na wynik) → linie → flota (dlaczego, łączny koszt kursów, koszt na kurs wobec 2026) → koszty operacyjne według MPK → ryzyka (liczbowo, ze scenariuszy) → ostrzeżenia.
- **Dane:** wyłącznie tabele modułu 4 i `zalozenia`. Przy kwotach z modelu dopisek „(prognoza, ± X%)”, przy zmienionych „(decyzja kierownika)” z uzasadnieniem.
- **Ostrzeżenia:** formatka niezaakceptowana; założenie z flagą `domyslne`; wiersze `z_modelu_niesprawdzone`.
- **Kontrola przed wysłaniem do CFO:** porównanie liczb z tabelami (`zgodnosc_liczb`) i limitu słów.

## 9. Jakość danych
| Problem | Obsługa |
|---|---|
| Koszty transportu na MPK 410 do 06.2025, potem na 440 | sumowanie w uczeniu i porównaniach, adnotacja w widokach |
| Usługi dodatkowe FCL 05.2025 = 3,63 mln zł (zwykle ok. 0,3–0,4 mln) | `wylaczone_z_uczenia`, oznaczenie na wykresach |
| Podwykonawcy TRN 03.2026 = 2,67 mln, 04.2026 = 1,51 mln zł | jak wyżej |
| Brak `lcl_m3` za 08.2024 | miesiąc pominięty w uczeniu wolumenu LCL |
| Licencja MPK 500 w styczniu, wyższe koszty w grudniu | osobna pozycja jednorazowa; sezonowość w metodach |
| Tylko średni kurs miesięczny (księgowość liczy po kursie z dnia faktury) | stawka USD z historii liczona po kursie średnim, z adnotacją w założeniach |
| Rok 2024 nietypowy (stawki frachtu) | adnotacja w porównaniach rok do roku; stawka frachtu z założeń |
| MPK 440 ma historię od 07.2025 | sumowanie z 410 |
| Flota bez historii | brak podpowiedzi |
| Budżet 2026 tylko rocznie i za I–IX | porównania tylko na tych poziomach |
| Opis 2026 podał 15,8% zamiast 14,8% | odsetki zawsze liczone z danych, nigdy przepisywane |

## 10. Kryteria akceptacji (testy)
- Z1-K1: Wpisanie TEU i stawki w formatce FCL pokazuje przychód, koszt i marżę brutto.
- Z1-K2: Formatka TRN na 2027 bez kursów własnych pokazuje ostrzeżenie.
- Z1-K3: Odchylenie powyżej progu bez uzasadnienia blokuje złożenie.
- Z1-K4: Akceptacja formatki od razu zmienia sumy na dashboardach, bez ręcznej konsolidacji.
- Z2-K1: Formatka FCL złożona przez Dyrektora Operacyjnego (p.o.) trafia do Prezesa.
- Z2-K2: Przy `data_symulacji` w okresie 2–13.11 akceptację formatki MPK wykonuje Kontroler, a w historii jest wpis „w zastępstwie CFO”.
- Z2-K3: Formatka niezłożona do 13.11 ma flagę spóźnienia i pokazuje, na kogo czeka.
- Z3-K1: Formatka FCL pokazuje „X TEU × Y USD/TEU (stawka centralna) × kurs, rok temu Z, błąd ± M%”.
- Z3-K2: Większy udział kursów własnych zmniejsza koszt podwykonawców; pola floty mają napis „brak podpowiedzi”.
- Z3-K3: Kwota dużo wyższa od podpowiedzi wymaga uzasadnienia i ma w opisie dopisek „(decyzja kierownika)”.
- Z4-K1: Sztuczna niezgodność sum zapala kontrolkę na czerwono.
- Z4-K2: Kontroler widzi np. „formatka LCL spóźniona, czeka na: [osoba]”.
- Z4-K3: Przewidywane wykonanie 2026 ma etykietę „szacunek”, a kwoty mają znacznik źródła.
- Z5-K1: Różnica 1 zł między opisem a tabelą blokuje wysłanie do CFO.
- Z5-K2: Formatka LCL wypełniona tylko z modelu i niezaakceptowana daje w opisie ostrzeżenie i etykietę „niezaakceptowana”.
- Z5-K3: Pierwszy akapit opisu podaje wynik, kurs USD, stawki i wolumeny.

## 11. Plan budowy
1. **Dane i konfiguracja.** Gotowe, gdy import obu CSV, tabele z sekcji 3, oba pliki konfiguracyjne i wybór roli w panelu działają, a sumy roczne zgadzają się z danymi (np. przychody 2025 = 166 470 tys. zł).
2. **Formatki.** Gotowe, gdy działają formatki linii, MPK i floty z obliczeniami, walidacją i ostrzeżeniami (Z1-K1–K3).
3. **Proces i uprawnienia.** Gotowe, gdy działają statusy, akceptacje, zastępstwa, eskalacje i historia (Z2-K1–K3).
4. **Predykcja.** Gotowe, gdy działają test wsteczny, wybór metody, podpowiedzi i prognoza 2026, a punkt kontrolny z sekcji 6 się zgadza (Z3-K1–K3).
5. **Dashboardy.** Gotowe, gdy działa pięć widoków, scenariusze, kontrolka i automatyczna konsolidacja (Z1-K4, Z4-K1–K3).
6. **Opis budżetu.** Gotowe, gdy działają projekt opisu, kontrola zgodności, obieg Kontroler → CFO i wszystkie testy z sekcji 10.

## 12. Poza zakresem
Logowanie i hasła; wysyłka e-maili; udział w rynku (D30); model językowy (D31); integracja z systemem księgowym i transportowym; przeliczanie po kursie z dnia faktury; kontroling wykonania 2027; polityka zakupowa (D12); korekta danych źródłowych (tylko oznaczanie).

## 13. Rejestr decyzji (zdecydował prowadzący; wszystkie zgodnie z rekomendacją orkiestratora)
D1 flotę akceptuje Dyrektor Operacyjny; D2 osobne MPK 450; D3 flota to koszt bezpośredni TRN; D4 udział kursów własnych z liczby zestawów; D5 wakaty obsadza Dyrektor Operacyjny; D6 CFO zastępuje Kontroler; D7 Kontroler nie zatwierdza własnej konsolidacji ani opisu; D8 statusy z powrotem po odrzuceniu; D9 „czeka na” = następny ruch; D10 eskalacja po 2 dniach; D11 budżet z oznaczonymi formatkami niezaakceptowanymi; D12 bez progów zakupowych; D13 opis zatwierdza CFO, w zastępstwie Prezes; D14 stawka CFO, zmiana z uzasadnieniem; D15 stawka frachtu w USD; D16 kurs ustala CFO; D17 domyślne kurs i stawki z ostrzeżeniem; D18 cztery znaczniki źródła; D19 próg od podpowiedzi albo 2026; D20 10% i 50 000 zł; D21 klucz: marża; D22 MPK→linia; D23 suma 410+440; D24 anomalie wyłączone; D25 metoda według MAPE; D26 ± MAPE; D27 „szacunek” tylko dla 2026; D28 scenariusze USD, fracht i wolumen; D29 budżet 2026 rocznie i za I–IX; D30 bez udziału w rynku; D31 szablon bez modelu językowego; D32 wnioski pisze Kontroler; D33 limit 900 słów.
