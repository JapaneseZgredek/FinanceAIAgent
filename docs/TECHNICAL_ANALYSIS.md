# Technical Analysis Guide

Ten dokument opisuje wszystkie wskaźniki techniczne używane w Finance AI Agent, ich matematyczne podstawy, sposób obliczania oraz interpretację wyników.

---

## Spis treści

1. [Podstawowe pojęcia](#podstawowe-pojęcia)
2. [Moving Averages (Średnie kroczące)](#moving-averages-średnie-kroczące)
   - [SMA — Simple Moving Average](#sma--simple-moving-average)
   - [EMA — Exponential Moving Average](#ema--exponential-moving-average)
   - [Interpretacja i sygnały](#interpretacja-i-sygnały-ma)
3. [RSI — Relative Strength Index](#rsi--relative-strength-index)
4. [MACD — Moving Average Convergence Divergence](#macd--moving-average-convergence-divergence)
5. [ATR — Average True Range](#atr--average-true-range)
6. [Volatility Regime (Reżimy zmienności)](#volatility-regime-reżimy-zmienności)
7. [Trend Summary (Podsumowanie trendu)](#trend-summary-podsumowanie-trendu)
8. [Przykłady użycia](#przykłady-użycia)

---

## Podstawowe pojęcia

### Cena zamknięcia (Close Price)
W analizie technicznej najczęściej używamy **ceny zamknięcia** danego dnia. Jest to ostatnia cena transakcyjna w danym okresie (np. dzień). Uważana jest za najważniejszą cenę, bo reprezentuje finalną wycenę rynkową.

### Okres (Period)
Liczba świec/dni używana do obliczenia wskaźnika. Np. RSI(14) oznacza RSI obliczone na podstawie ostatnich 14 dni.

### Trend
Kierunek ruchu ceny w czasie:
- **Uptrend (trend wzrostowy):** seria wyższych szczytów i wyższych dołków
- **Downtrend (trend spadkowy):** seria niższych szczytów i niższych dołków
- **Sideways (konsolidacja):** brak wyraźnego kierunku

---

## Moving Averages (Średnie kroczące)

Średnie kroczące wygładzają dane cenowe, eliminując szum i pokazując kierunek trendu.

### SMA — Simple Moving Average

**Definicja:** Prosta średnia arytmetyczna cen zamknięcia z ostatnich N okresów.

**Wzór:**
```
SMA(N) = (P₁ + P₂ + P₃ + ... + Pₙ) / N
```

gdzie:
- `P₁, P₂, ... Pₙ` — ceny zamknięcia z ostatnich N dni
- `N` — okres (liczba dni)

**Przykład obliczenia SMA(5):**
```
Ceny: 100, 102, 101, 103, 105
SMA(5) = (100 + 102 + 101 + 103 + 105) / 5 = 102.2
```

**Zalety:**
- Prosta w obliczeniu i interpretacji
- Wszystkie ceny mają równą wagę

**Wady:**
- Reaguje wolno na zmiany cen
- Starsze dane mają taką samą wagę jak najnowsze

**Popularne okresy:**
| Okres | Zastosowanie |
|-------|--------------|
| SMA(20) | Krótkoterminowy trend (ok. 1 miesiąc handlowy) |
| SMA(50) | Średnioterminowy trend (ok. 2-3 miesiące) |
| SMA(200) | Długoterminowy trend (ok. 1 rok) |

---

### EMA — Exponential Moving Average

**Definicja:** Średnia wykładnicza, która nadaje większą wagę nowszym cenom.

**Wzór:**
```
EMA_today = (Price_today × k) + (EMA_yesterday × (1 - k))
```

gdzie:
- `k = 2 / (N + 1)` — współczynnik wygładzania (smoothing factor)
- `N` — okres

**Przykład współczynników k:**
| Okres | k (współczynnik) |
|-------|------------------|
| EMA(20) | 2/21 = 0.095 (9.5%) |
| EMA(50) | 2/51 = 0.039 (3.9%) |
| EMA(200) | 2/201 = 0.01 (1%) |

**Zalety:**
- Szybciej reaguje na zmiany cen niż SMA
- Nowsze dane mają większy wpływ

**Wady:**
- Bardziej podatna na fałszywe sygnały (szum)

---

### Interpretacja i sygnały (MA)

#### Cena vs Średnia
| Sytuacja | Interpretacja |
|----------|---------------|
| Cena > MA | **Bullish** — trend wzrostowy, kupujący dominują |
| Cena < MA | **Bearish** — trend spadkowy, sprzedający dominują |
| Cena ≈ MA | **Neutral** — niezdecydowanie rynku |

#### Złote i Martwe Krzyże
| Sygnał | Opis | Interpretacja |
|--------|------|---------------|
| **Golden Cross** | Krótka MA przecina długą od dołu | Silny sygnał kupna (bullish) |
| **Death Cross** | Krótka MA przecina długą od góry | Silny sygnał sprzedaży (bearish) |

**Przykład:**
- SMA(50) przecina SMA(200) od dołu → Golden Cross → potencjalny początek trendu wzrostowego

#### Układ średnich
```
Bullish:     Cena > EMA(20) > EMA(50) > EMA(200)
Bearish:     Cena < EMA(20) < EMA(50) < EMA(200)
Mixed:       Średnie przeplatają się — brak wyraźnego trendu
```

---

## RSI — Relative Strength Index

**Definicja:** Oscylator momentum mierzący szybkość i zmianę ruchów cenowych. Wartość od 0 do 100.

**Wzór:**
```
RSI = 100 - (100 / (1 + RS))

RS = Average Gain / Average Loss
```

gdzie:
- `Average Gain` — średnia ze wzrostów cen w okresie
- `Average Loss` — średnia ze spadków cen w okresie

**Szczegółowe obliczenie RSI(14):**

**Ważne:** RSI to **seria wartości** — jedna na każdy dzień. Nie jest to pojedyncza liczba obliczona raz. Każdego dnia średnie (Avg Gain, Avg Loss) są aktualizowane za pomocą EMA Wildera, co daje nową wartość RSI.

1. Oblicz zmiany cen dzień do dnia:
```
Dzień 1→2: +2%  (gain)
Dzień 2→3: -1%  (loss)
Dzień 3→4: +3%  (gain)
...
```

2. Rozdziel na gains i losses (seria — jedna wartość na każdy dzień):
```
Gains:  [2, 0, 3, 1, 0, 2, 0, 0, 1, 0, 2, 0, 1, 0, ...]
Losses: [0, 1, 0, 0, 2, 0, 1, 3, 0, 1, 0, 2, 0, 1, ...]
```

3. Oblicz bieżące średnie (używając EMA Wildera, alpha = 1/14):

Każdego dnia średnia jest aktualizowana rekurencyjnie:
```
Avg Gain_today = (Gain_today × 1/14) + (Avg Gain_yesterday × 13/14)
Avg Loss_today = (Loss_today × 1/14) + (Avg Loss_yesterday × 13/14)
```

Przykład ewolucji w czasie:
```
Dzień    Gain   Loss   Avg Gain   Avg Loss   RS      RSI
──────────────────────────────────────────────────────────
  14      1.0    0.0     1.20       0.85     1.41    58.5    ← pierwsza wartość (po 14 dniach)
  15      0.0    2.0     1.11       0.93     1.19    54.4
  16      3.0    0.0     1.25       0.87     1.44    59.0
  17      0.0    1.5     1.16       0.91     1.27    56.0
  18      2.5    0.0     1.26       0.84     1.49    59.9
  ...
```

4. Dla każdego dnia oblicz RS i RSI:
```
RS = Avg Gain / Avg Loss
RSI = 100 - (100 / (1 + RS))
```

W kodzie używamy **tylko ostatniej wartości** z tej serii do interpretacji, ale cała seria jest potrzebna do wykrywania dywergencji (porównanie lokalnych minimów/maksimów RSI w czasie).

**Interpretacja:**

| RSI | Interpretacja | Akcja |
|-----|---------------|-------|
| > 70 | **OVERBOUGHT** (wykupiony) | Potencjalny sygnał sprzedaży, cena może spaść |
| 60-70 | Bullish | Momentum wzrostowe |
| 40-60 | **NEUTRAL** | Brak wyraźnego sygnału |
| 30-40 | Bearish | Momentum spadkowe |
| < 30 | **OVERSOLD** (wyprzedany) | Potencjalny sygnał kupna, cena może wzrosnąć |

**Dywergencje RSI:**

| Typ | Cena | RSI | Znaczenie |
|-----|------|-----|-----------|
| Bullish Divergence | Niższe dno | Wyższe dno | Potencjalne odwrócenie w górę |
| Bearish Divergence | Wyższy szczyt | Niższy szczyt | Potencjalne odwrócenie w dół |

**Uwaga:** W silnych trendach RSI może pozostawać w strefie wykupienia/wyprzedania przez długi czas!

---

## MACD — Moving Average Convergence Divergence

**Definicja:** Wskaźnik momentum oparty na różnicy dwóch EMA. Pokazuje siłę, kierunek i momentum trendu.

**Komponenty:**

```
MACD Line    = EMA(12) - EMA(26)
Signal Line  = EMA(9) of MACD Line
Histogram    = MACD Line - Signal Line
```

**Wizualizacja:**
```
        MACD Line (szybka)
              ↓
    ~~~~~~~~~/\~~~~~/\~~~~~
            /  \   /  \
    -------/----\-/----\---  ← Zero Line
          /      X      \
    ~~~~~/ Signal Line   \~~
         (wolna)
    
    Histogram:
    ▓▓▓▓                    ← dodatni (bullish)
        ▒▒▒▒                ← malejący
            ░░░░░░          ← ujemny (bearish)
```

**Interpretacja:**

| Sytuacja | Znaczenie |
|----------|-----------|
| MACD > Signal | **Bullish** — momentum wzrostowe |
| MACD < Signal | **Bearish** — momentum spadkowe |
| MACD crosses Signal (od dołu) | Sygnał kupna |
| MACD crosses Signal (od góry) | Sygnał sprzedaży |
| Histogram > 0 i rośnie | Silne momentum wzrostowe |
| Histogram < 0 i maleje | Silne momentum spadkowe |
| MACD > 0 | Cena powyżej średnioterminowej średniej |
| MACD < 0 | Cena poniżej średnioterminowej średniej |

**Ważne:** Wszystkie komponenty MACD (MACD Line, Signal Line, Histogram) to **serie wartości** — jedna na każdy dzień. Nie są to pojedyncze liczby.

**Przykład liczbowy (seria):**
```
Dzień   EMA(12)     EMA(26)     MACD Line   Signal Line  Histogram
──────────────────────────────────────────────────────────────────────
  30    103,200     102,800       +400         +250         +150
  31    103,800     102,900       +900         +322         +578
  32    104,500     103,100     +1,400         +442         +958
  33    105,000     103,400     +1,600         +571       +1,029
  34    105,234     103,500     +1,734         +700       +1,034
```

Jak to czytać:
- EMA(12) i EMA(26) to serie — każdego dnia obliczana jest nowa wartość
- MACD Line to seria różnic: `EMA(12) - EMA(26)` dla każdego dnia
- Signal Line to EMA(9) obliczana **z serii MACD Line** (nie z jednej wartości)
- Histogram to seria różnic: `MACD Line - Signal Line` dla każdego dnia

W kodzie używamy **tylko ostatnich wartości** z tych serii do oceny trendu (`get_macd_result()`).

---

## ATR — Average True Range

**Definicja:** Miara zmienności (volatility) rynku. Wyższa wartość = większa zmienność.

**True Range (TR):**
```
TR = max of:
  1. High - Low (zakres dnia)
  2. |High - Previous Close| (gap up)
  3. |Low - Previous Close| (gap down)
```

**ATR:**
```
ATR(N) = EMA(TR, N)  — lub SMA w klasycznej wersji
```

**Uwaga:** W naszej implementacji używamy przybliżenia opartego tylko na cenach zamknięcia:
```
Approximate TR = |Close_today - Close_yesterday|
ATR = EMA(Approximate TR, 14)  ← Wilder's smoothing (alpha = 1/14)
```

**Ważne:** Zarówno TR jak i ATR to **serie wartości** — jedna na każdy dzień. ATR jest obliczany rekurencyjnie (tak samo jak RSI):
```
ATR_today = (TR_today × 1/14) + (ATR_yesterday × 13/14)
```

**Przykład ewolucji ATR w czasie:**
```
Dzień   Close      TR (|zmiana|)   ATR(14)
────────────────────────────────────────────
  14    $98,000     $1,200         $2,100    ← pierwsza wartość (po 14 dniach)
  15    $99,500     $1,500         $2,057
  16    $97,000     $2,500         $2,089
  17    $97,800     $800           $1,997
  18    $100,300    $2,500         $2,033
  ...
```

**ATR%** — znormalizowana zmienność (również seria, jedna wartość dziennie):
```
ATR%_today = (ATR_today / Close_today) × 100
```

**Przykład:**
```
Dzień 18:
  ATR(14) = $2,033
  Close   = $100,300
  ATR%    = (2,033 / 100,300) × 100 = 2.03%
```

W kodzie używamy **ostatniej wartości** z serii ATR% do klasyfikacji reżimu zmienności, ale **cała seria historyczna** jest potrzebna do obliczenia percentyli.

**Zastosowania:**

| Użycie | Opis |
|--------|------|
| **Stop Loss** | SL = Entry - (2 × ATR) |
| **Position Sizing** | Mniejsza pozycja przy wysokim ATR |
| **Volatility Filter** | Unikaj tradingu przy ekstremalnym ATR |
| **Breakout Confirmation** | Ruch > 1.5 × ATR = prawdziwy breakout |

---

## Volatility Regime (Reżimy zmienności)

Klasyfikujemy aktualną zmienność względem historycznej dystrybucji ATR%.

**Metoda:** Porównanie aktualnego ATR% z percentylami obliczonymi z **całej historycznej serii ATR%**.

ATR% to seria dzienna (np. 120+ wartości przy `PRICE_WINDOW_DAYS=120`). Percentyle są obliczane z tej pełnej serii:

```
Historyczna seria ATR% (przykład — fragment ze 120 dni):
Dzień 14: 2.1%
Dzień 15: 2.0%
Dzień 16: 2.5%
...
Dzień 80: 1.5%
...
Dzień 120: 3.2%  ← aktualna wartość

Z całej serii obliczamy percentyle:
Percentile 25 (P25) = 1.9%
Percentile 75 (P75) = 3.2%
Percentile 90 (P90) = 5.5%

Aktualna wartość (3.2%) porównywana jest z tymi progami.
```

**Klasyfikacja:**

| ATR% | Reżim | Opis | Implikacje |
|------|-------|------|------------|
| < P25 | **LOW** | Niska zmienność | Konsolidacja, możliwy breakout wkrótce |
| P25 - P75 | **NORMAL** | Typowa zmienność | Normalne warunki tradingowe |
| P75 - P90 | **HIGH** | Podwyższona zmienność | Większe ryzyko, większe możliwości |
| > P90 | **EXTREME** | Ekstremalna zmienność | Panika/euforia, bardzo ryzykowne |

**Wizualizacja:**
```
        LOW        NORMAL         HIGH      EXTREME
    |---------|---------------|---------|----------|
    0%       P25            P75       P90        ∞
         ←konsolidacja→  ←trend→  ←silny trend→  ←panika→
```

---

## Trend Summary (Podsumowanie trendu)

Algorytm łączy wszystkie wskaźniki w jedną ocenę trendu.

**System punktowy:**

| Wskaźnik | Bullish (+1) | Bearish (+1) |
|----------|--------------|--------------|
| Cena vs SMA(20) | Cena > SMA(20) | Cena < SMA(20) |
| Cena vs SMA(50) | Cena > SMA(50) | Cena < SMA(50) |
| Cena vs SMA(200) | Cena > SMA(200) | Cena < SMA(200) |
| RSI(14) | RSI > 50 | RSI < 50 |
| MACD | MACD > Signal | MACD < Signal |

**Maksymalny wynik:** 5 punktów na stronę

**Klasyfikacja końcowa:**

| Bullish | Bearish | Ocena |
|---------|---------|-------|
| ≥ 4 | ≤ 1 | **BULLISH** — silny trend wzrostowy |
| ≥ 3 | ≤ 2 | **SLIGHTLY BULLISH** — lekka przewaga byków |
| 2-3 | 2-3 | **NEUTRAL** — brak wyraźnego trendu |
| ≤ 2 | ≥ 3 | **SLIGHTLY BEARISH** — lekka przewaga niedźwiedzi |
| ≤ 1 | ≥ 4 | **BEARISH** — silny trend spadkowy |

**Przykład:**
```
Cena: $105,000
SMA(20): $103,000  → Cena > SMA(20) → Bullish +1
SMA(50): $100,000  → Cena > SMA(50) → Bullish +1
SMA(200): $85,000  → Cena > SMA(200) → Bullish +1
RSI(14): 62        → RSI > 50 → Bullish +1
MACD: 1500 > Signal: 1200 → Bullish +1

Bullish: 5, Bearish: 0
→ TREND SUMMARY: BULLISH - price above key MAs with positive momentum
```

---

## Przykłady użycia

### Przykład 1: Silny trend wzrostowy (BTC Bull Run)

```
=== TECHNICAL INDICATORS ===

MOVING AVERAGES:
  SMA(20):   102,345.67  (price above)
  SMA(50):    95,123.45  (price above)
  SMA(200):   72,456.78  (price above)
  EMA(20):   103,234.56
  EMA(50):    96,543.21
  EMA(200):   74,321.09

MOMENTUM:
  RSI(14): 68.5 → bullish
  MACD: 2,345.67 | Signal: 1,890.12 | Histogram: 455.55
  MACD Trend: bullish

VOLATILITY:
  ATR(14): 3,456.78 (3.25% of price)
  Regime: NORMAL

TREND SUMMARY: BULLISH - price above key MAs with positive momentum
```

**Interpretacja:**
- Wszystkie średnie kroczące poniżej ceny → silny uptrend
- RSI 68.5 → momentum wzrostowe, ale jeszcze nie wykupiony
- MACD pozytywny z rosnącym histogramem → kontynuacja trendu
- Zmienność normalna → stabilny trend

---

### Przykład 2: Początek korekty

```
=== TECHNICAL INDICATORS ===

MOVING AVERAGES:
  SMA(20):   105,000.00  (price below)  ← UWAGA
  SMA(50):    98,000.00  (price above)
  SMA(200):   75,000.00  (price above)

MOMENTUM:
  RSI(14): 42.3 → bearish
  MACD: 1,200.00 | Signal: 1,500.00 | Histogram: -300.00
  MACD Trend: bearish  ← UWAGA

VOLATILITY:
  ATR(14): 4,500.00 (4.50% of price)
  Regime: HIGH  ← UWAGA

TREND SUMMARY: SLIGHTLY BEARISH - mixed signals with bearish bias
```

**Interpretacja:**
- Cena przebiła SMA(20) od góry → krótkoterminowe osłabienie
- RSI spadł poniżej 50 → momentum przechodzi na stronę niedźwiedzi
- MACD histogram ujemny → siła sprzedających
- Wysoka zmienność → rynek nerwowy
- Długoterminowy trend (SMA 50/200) wciąż wzrostowy

---

### Przykład 3: Oversold bounce setup

```
=== TECHNICAL INDICATORS ===

MOVING AVERAGES:
  SMA(20):    45,000.00  (price below)
  SMA(50):    48,000.00  (price below)
  SMA(200):   42,000.00  (price below)

MOMENTUM:
  RSI(14): 22.5 → OVERSOLD  ← SYGNAŁ
  MACD: -1,500.00 | Signal: -1,200.00 | Histogram: -300.00
  MACD Trend: bearish

VOLATILITY:
  ATR(14): 3,200.00 (8.00% of price)
  Regime: EXTREME  ← UWAGA

TREND SUMMARY: BEARISH - price below key MAs with negative momentum
```

**Interpretacja:**
- RSI < 30 → **OVERSOLD** — potencjalny sygnał odbicia
- Ale: wszystkie MA powyżej ceny + MACD bearish → trend spadkowy wciąż silny
- Ekstremalna zmienność → możliwy kapitulacyjny dołek LUB dalsze spadki
- **Wniosek:** Czekać na potwierdzenie odbicia (RSI > 30, MACD histogram się zawęża)

---

## Podsumowanie

| Wskaźnik | Co mierzy | Bullish | Bearish |
|----------|-----------|---------|---------|
| SMA/EMA | Trend | Cena > MA | Cena < MA |
| RSI | Momentum | > 50 (overbought > 70) | < 50 (oversold < 30) |
| MACD | Momentum + Trend | MACD > Signal, Hist > 0 | MACD < Signal, Hist < 0 |
| ATR | Zmienność | - | - |
| Regime | Ryzyko | LOW/NORMAL = stabilność | HIGH/EXTREME = ostrożność |

**Zasada:** Nigdy nie podejmuj decyzji na podstawie jednego wskaźnika! Szukaj **konfluencji** — sytuacji gdy wiele wskaźników wskazuje ten sam kierunek.

---

*Dokument wygenerowany dla Finance AI Agent v1.0*
