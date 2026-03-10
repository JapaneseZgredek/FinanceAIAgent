# ADR-001: Redesign outputu agenta — z predykcji na analizę sygnałów

**Status:** Proponowane
**Data:** 2026-03-10

---

## Kontekst

Obecny output agenta zwraca jedną etykietę kierunkową: `UP`, `DOWN` lub `NEUTRAL`.
Taka forma sugeruje precyzję, której system nie posiada:

- Model językowy nie jest statystycznie skalibrowanym predyktorem cen.
- Jeden symbol nie opisuje złożonego, wielowymiarowego stanu rynku.
- Etykieta bez horyzontu czasowego jest semantycznie pusta — rynek może być jednocześnie
  „UP" w perspektywie tygodnia i „DOWN" w perspektywie miesiąca.

To tzw. **fałszywa precyzja**: output sprawia wrażenie pewności, której nie ma, co może
prowadzić użytkownika do błędnych decyzji.

---

## Problem

Konkretne failure modes obecnego podejścia:

1. **Brak horyzontu czasowego.** Ten sam układ techniczny (np. złoty krzyż SMA50/200)
   ma inne implikacje w perspektywie 3 dni vs. 3 miesięcy.
2. **Brak kontekstu reżimu makro.** Bullish sygnał techniczny w środowisku podwyżek stóp
   i odpływu kapitału z ryzykownych aktywów oznacza co innego niż w środowisku luzowania.
3. **Brak kalibracji pewności.** Model nie dysponuje danymi historycznymi własnych predykcji,
   więc nie może wyliczyć % trafności. Podawanie procentowej pewności byłoby fikcją.
4. **Korelacja wewnętrzna sygnałów.** News i RSI mogą wskazywać w tym samym kierunku,
   ale wynikać z tej samej przyczyny — agregacja ich jako niezależnych sygnałów zawyża
   pozorną pewność.

---

## Decyzja

Zmieniamy filozofię systemu z **"prediction engine"** na **"analytical intelligence"**.

Agent przestaje wydawać jednoznaczną predykcję. Zamiast tego dostarcza wielowymiarowy
obraz stanu rynku: **sygnały per horyzont czasowy**, z opisem stanu każdego wymiaru.

### Horyzonty i źródła sygnałów

Tabela pokazuje co jest dostępne **teraz** (v1: indykatory + newsy) vs. plany:

| Horyzont | Okres | Źródła — teraz | Źródła — przyszłość |
|---|---|---|---|
| Krótki | 1–7 dni | Newsy (Step 1) + momentum: RSI, MACD, wolumen | — |
| Średni | 2–6 tygodni | Technikalia: SMA20/50, EMA, ATR | Sentyment on-chain |
| Długi | 3–6 miesięcy | SMA200, struktura techniczna | Makro API (DXY, stopy, płynność), dominacja BTC |

### Nowy format outputu (przykładowa struktura raportu końcowego)

Każdy horyzont zawiera trzy obowiązkowe sekcje + jedną warunkową:
- **Stan sygnałów** — fakty i liczby
- **Kierunek sygnałów** — tendencja, nie binarna etykieta
- **Dlaczego?** — mechanika edukacyjna (co te sygnały razem oznaczają)
- **Co obserwować?** — *tylko gdy kierunek niejednoznaczny*: co konkretnie rozstrzyga

Raport kończy sekcja **Perspektywa tradingowa** z decyzją wejścia, kierunkiem
(long/short) i sugerowaną dźwignią skalibrowaną do siły sygnałów i zmienności.

```
## Analiza rynkowa: BTC/USD — 2026-03-10

### Horyzont krótki (1–7 dni)
**Stan sygnałów:** RSI 42, MACD poniżej linii sygnałowej, wolumen -18% vs. 30d
średnia. Newsy neutralne — brak wyraźnych katalizatorów.
**Kierunek sygnałów:** Niedźwiedzi / boczny
**Dlaczego?** RSI poniżej 50 oznacza, że popyt jest słabszy od podaży. MACD pod
linią sygnałową potwierdza brak impetu kupujących. Niski wolumen przy konsolidacji
to klasyczny brak przekonania rynku — ruchy bez wolumenu często nie mają trwałości.
Przy neutralnych newsach scenariusz bazowy to dalsza kompresja.

### Horyzont średni (2–6 tygodni)
**Stan sygnałów:** RSI 54, MACD wciąż pod linią sygnałową. Cena powyżej SMA20
i SMA50, poniżej SMA200. ATR w trendzie spadkowym — kompresja zmienności.
**Kierunek sygnałów:** Niejednoznaczny — presja na opór przy SMA200
**Dlaczego?** RSI powyżej 50 sugeruje, że popyt zaczyna dominować, ale MACD pod
linią sygnałową mówi, że impet trendu jeszcze nie potwierdził zmiany. Cena między
SMA50 a SMA200 to strefa przejściowa. Kompresja ATR często poprzedza silny ruch —
kierunek rozstrzyga się przy kluczowym oporze.
**Co obserwować?** Przebicie MACD powyżej linii sygnałowej potwierdziłoby bycze
momentum. Powrót RSI poniżej 50 przy wzroście wolumenu sygnalizowałby powrót
presji niedźwiedziej.

### Horyzont długi (3–6 miesięcy)
**Stan sygnałów:** SMA200 w trendzie bocznym od 90 dni. Brak danych makro
(API w planach) — ocena oparta wyłącznie na strukturze technicznej.
**Kierunek sygnałów:** Neutralny — brak potwierdzenia trendu długoterminowego
**Dlaczego?** SMA200 to najważniejsza linia podziału rynek bycze/niedźwiedzie.
Boczny SMA200 oznacza brak wyraźnego kierunku. Bez danych makro (stopy, DXY,
płynność) ocena tego horyzontu jest niepełna — należy traktować ją jako wstępną.

---

### Perspektywa tradingowa
**Wejście w rynek:** Czekaj na potwierdzenie
**Kierunek:** Long (warunkowo)
**Sugerowana dźwignia:** 2x–3x
**Dlaczego ta dźwignia?** Tylko jeden horyzont (krótki) wykazuje wyraźny kierunek
(niedźwiedzi), średni jest niejednoznaczny, długi neutralny. Brak zbieżności sygnałów
nie uzasadnia wyższej ekspozycji. Wyższa dźwignia = mniejszy rozmiar pozycji.
**Warunek wejścia:** Zamknięcie świecy dziennej powyżej SMA200 przy wolumenie
powyżej 30d średniej oraz potwierdzenie MACD crossover.

---
*Raport ma charakter analityczny. Nie stanowi porady inwestycyjnej.*
```

---

## Czego NIE robimy (świadome ograniczenia)

- **Brak jednej etykiety predykcji** (UP/DOWN/NEUTRAL) — usunięta celowo.
- **Brak wag liczbowych i procentowej pewności** — nie mamy danych historycznych
  do ich kalibracji; liczby bez kalibracji byłyby fikcją.
- **Brak kontekstu historycznego własnych predykcji** — odłożone na późniejszą fazę
  (wymaga bazy danych SQLite i mechanizmu weryfikacji ex-post).
- **Brak danych makro jako inputu** w bieżącej wersji — makro jest analizowane
  przez model na podstawie wiedzy i newsów, nie z dedykowanego API.

---

## Wpływ na pipeline

### Zmiany natychmiastowe (bieżąca faza)
- **Step 1 (`_get_news_analysis`):** Sekcja `## News Forecast: UP/DOWN/NEUTRAL`
  zastąpiona sekcją `## News Tendency` — opis tendencji bez binarnej etykiety.
- **Step 2 (`_get_price_analysis`):** Linia `Forecast: UP/DOWN/NEUTRAL`
  zastąpiona strukturą per horyzont: sygnały krótko-, średnio- i długoterminowe.
  Ułatwia Step 3 przypisanie wskaźników do właściwych horyzontów.
- **Step 3 (`_get_final_report`):** Kompletne przepisanie promptu — nowy format
  z sekcjami Stan/Kierunek/Dlaczego/Co obserwować per horyzont oraz sekcją
  Perspektywa tradingowa z kalibracją dźwigni.
- Nie ma breaking changes w interfejsie CLI (`main.py`).

### Przyszłe rozszerzenia (planowane, nie w scope tej decyzji)
- **Krok 0b:** Dodanie danych makro (np. DXY, stopy Fed) jako lokalnego inputu
  do pipeline — analogicznie do danych Alpha Vantage w Kroku 0.
- **SQLite:** Archiwizacja raportów do lokalnej bazy — umożliwi weryfikację ex-post
  i ewentualną kalibrację sygnałów w przyszłości.

---

## Konsekwencje

**Pozytywne:**
- Output lepiej odzwierciedla rzeczywistą wiedzę i niepewność modelu.
- Użytkownik otrzymuje więcej kontekstu do samodzielnej oceny sytuacji.
- System jest odporniejszy na krytykę "złych predykcji" — bo nie predykuje.

**Negatywne / do zaakceptowania:**
- Output jest dłuższy i wymaga więcej uwagi od użytkownika.
- Brak jednej liczby/etykiety utrudnia szybkie porównanie raportów.
- Zmiana wymaga aktualizacji dokumentacji i oczekiwań użytkowników.
