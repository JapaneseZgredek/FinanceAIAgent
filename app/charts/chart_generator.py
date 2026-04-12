"""Generowanie statycznych wykresów PNG dla raportów Finance AI Agent.

Produkuje dwa wykresy na run:
  1. Wykres cenowy z nakładką średnich kroczących (SMA20 / SMA50 / SMA200)
  2. Wykres kroczącej zmienności (30-dniowe rolling std dziennych zwrotów)

Wykresy są zapisywane jako pliki PNG i zwracane jako lista ścieżek.
Caller (main.py) przekazuje je do export_report() jako base64 embed.

Dlaczego SMA liczone jest na pełnym df, a nie na oknie wyświetlania?
  Każda MA ma swój "warmup period" — SMA200 potrzebuje 200 poprzednich dni
  żeby dać poprawną wartość. Gdybyśmy liczyli SMA na wyciętym oknie (np. 120d),
  SMA200 byłoby w całości NaN, a SMA50 niekompletne przez pierwsze 50 wierszy.
  Liczymy SMA na pełnej historii z Alpha Vantage (4000+ dni dla BTC), a potem
  wybieramy `.loc[df_display.index]` żeby pokazać tylko żądany zakres na osi X.
  Dla ostatnich 120 dni SMA200 ma zawsze poprawne wartości — NaN pojawia się
  tylko na początku całej historii, nie na końcu.

Standalone usage::

    from pathlib import Path
    from app.charts.chart_generator import generate_price_charts

    # Domyślnie PRICE_WINDOW_DAYS (spójne z oknem analizy)
    paths = generate_price_charts(df, "BTC", Path("reports"))

    # Własne okno
    paths = generate_price_charts(df, "BTC", Path("reports"), window_days=365)

Wymagania:
    matplotlib>=3.8.0 — opcjonalna zależność.
    Jeśli brak, generate_price_charts() zwraca [] z ostrzeżeniem.
"""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from app import config
from app.utils.indicators import sma, rsi, macd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Opcjonalna zależność — jeden import na poziomie modułu
# ---------------------------------------------------------------------------

try:
    import matplotlib
    import matplotlib.pyplot as plt
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False

# ---------------------------------------------------------------------------
# Paleta kolorów — dopasowana do dark-navy z report.css
# ---------------------------------------------------------------------------

_BG_COLOR = "#0d1b2a"
_PRICE_COLOR = "#e8c547"    # ciepły złoty — cena
_SMA20_COLOR = "#4fc3f7"    # jasny błękit — SMA20
_SMA50_COLOR = "#81c784"    # zieleń — SMA50
_SMA200_COLOR = "#ef9a9a"   # łososiowy czerwień — SMA200
_VOL_COLOR = "#ce93d8"      # fiolet — zmienność
_RSI_COLOR = "#f59e0b"      # bursztyn — linia RSI
_MACD_COLOR = "#14b8a6"     # morski — linia MACD
_SIGNAL_COLOR = "#fb923c"   # pomarańcz — linia Signal
_HIST_POS = "#4ade80"       # zieleń — histogram MACD dodatni
_HIST_NEG = "#f87171"       # czerwień — histogram MACD ujemny
_GRID_COLOR = "#1e3050"     # przyciemniony niebieski — siatka
_TEXT_COLOR = "#c8d8e8"     # jasny niebieski-szary — napisy
_AXIS_COLOR = "#2a4060"     # ramki osi


# ---------------------------------------------------------------------------
# Konfiguracja stylu matplotlib
# ---------------------------------------------------------------------------

def _configure_style() -> None:
    """Ustaw globalne rcParams matplotliba na ciemny motyw premium."""
    matplotlib.rcParams.update({
        "figure.facecolor": _BG_COLOR,
        "axes.facecolor": _BG_COLOR,
        "axes.edgecolor": _AXIS_COLOR,
        "axes.labelcolor": _TEXT_COLOR,
        "axes.grid": True,
        "grid.color": _GRID_COLOR,
        "grid.linestyle": "--",
        "grid.linewidth": 0.5,
        "xtick.color": _TEXT_COLOR,
        "ytick.color": _TEXT_COLOR,
        "text.color": _TEXT_COLOR,
        "legend.facecolor": "#11263a",
        "legend.edgecolor": _AXIS_COLOR,
        "legend.labelcolor": _TEXT_COLOR,
        "figure.dpi": 150,
        "figure.figsize": (11, 4.5),
        "font.size": 10,
        "lines.linewidth": 1.6,
    })


# ---------------------------------------------------------------------------
# Wykres 1 — Cena + nakładka MA
# ---------------------------------------------------------------------------

def _plot_price_with_ma(
    df: pd.DataFrame,
    df_display: pd.DataFrame,
    symbol: str,
) -> "matplotlib.figure.Figure":
    """Rysuj wykres cenowy z liniami SMA20 / SMA50 / SMA200.

    SMA liczone na pełnym df (właściwy kontekst historyczny — każda MA ma
    kompletny warmup period), ale oś X wykresu obejmuje tylko df_display.
    Linia MA jest pomijana jeśli seria jest całkowicie NaN w oknie wyświetlania
    (dotyczy wyłącznie bardzo młodych coinów z < 200 dniami historii).

    Args:
        df: Pełny DataFrame z kolumną ``price`` i datetime index.
        df_display: Fragment do wyświetlenia na osi X.
        symbol: Symbol kryptowaluty, np. ``"BTC"``.

    Returns:
        ``matplotlib.figure.Figure`` gotowa do zapisania.
    """
    price_series = df["price"]
    display_idx = df_display.index

    # MA liczone na pełnej historii, przycięte do okna wyświetlania przez .loc
    mas: list[tuple[str, pd.Series, str, str, float]] = [
        ("SMA 20",  sma(price_series, 20).loc[display_idx],  _SMA20_COLOR,  "-",  1.4),
        ("SMA 50",  sma(price_series, 50).loc[display_idx],  _SMA50_COLOR,  "-",  1.4),
        ("SMA 200", sma(price_series, 200).loc[display_idx], _SMA200_COLOR, "--", 1.2),
    ]

    fig, ax = plt.subplots()
    ax.set_title(
        f"{symbol} — Cena i średnie kroczące ({len(df_display)}d)",
        color=_TEXT_COLOR, fontsize=12, fontweight="bold", pad=10,
    )
    ax.plot(display_idx, df_display["price"], color=_PRICE_COLOR, linewidth=2.0, label="Cena", zorder=5)

    for label, series, color, style, width in mas:
        if not series.isna().all():
            ax.plot(display_idx, series, color=color, linewidth=width, linestyle=style, label=label)

    ax.set_xlabel("Data", color=_TEXT_COLOR)
    ax.set_ylabel("Cena (USD)", color=_TEXT_COLOR)
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Wykres 2 — Krocząca zmienność
# ---------------------------------------------------------------------------

def _plot_volatility(
    df: pd.DataFrame,
    df_display: pd.DataFrame,
    symbol: str,
) -> "matplotlib.figure.Figure":
    """Rysuj wykres kroczącej zmienności (30-dniowe rolling std dziennych zwrotów).

    Zmienność wyrażona w procentach (dzienna std × 100).
    Rolling liczone na pełnym df, wyświetlane tylko okno df_display.

    Args:
        df: Pełny DataFrame z kolumną ``price`` i datetime index.
        df_display: Fragment do wyświetlenia na osi X.
        symbol: Symbol kryptowaluty, np. ``"BTC"``.

    Returns:
        ``matplotlib.figure.Figure`` gotowa do zapisania.
    """
    vol30 = df["price"].pct_change().rolling(window=30, min_periods=10).std() * 100
    vol_display = vol30.loc[df_display.index]
    display_idx = df_display.index

    fig, ax = plt.subplots()
    ax.set_title(
        f"{symbol} — Zmienność krocząca 30d ({len(df_display)}d okno)",
        color=_TEXT_COLOR, fontsize=12, fontweight="bold", pad=10,
    )
    ax.plot(display_idx, vol_display, color=_VOL_COLOR, linewidth=1.6, label="Zmienność 30d")
    ax.fill_between(display_idx, vol_display, alpha=0.15, color=_VOL_COLOR)
    ax.set_xlabel("Data", color=_TEXT_COLOR)
    ax.set_ylabel("Odch. std dziennych zwrotów (%)", color=_TEXT_COLOR)
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Wykres 3 — RSI (Relative Strength Index)
# ---------------------------------------------------------------------------

def _plot_rsi(
    df: pd.DataFrame,
    df_display: pd.DataFrame,
    symbol: str,
) -> "matplotlib.figure.Figure":
    """Rysuj wykres RSI (14) z liniami overbought (70) i oversold (30).

    RSI liczone na pełnym df (właściwy warmup Wildera — EMA z alpha=1/14),
    wyświetlane tylko okno df_display. Strefy overbought/oversold zaznaczone
    jako wypełniony obszar dla lepszej czytelności.

    Args:
        df: Pełny DataFrame z kolumną ``price`` i datetime index.
        df_display: Fragment do wyświetlenia na osi X.
        symbol: Symbol kryptowaluty, np. ``"BTC"``.

    Returns:
        ``matplotlib.figure.Figure`` gotowa do zapisania.
    """
    rsi_series = rsi(df["price"], period=14).loc[df_display.index]
    display_idx = df_display.index

    fig, ax = plt.subplots()
    ax.set_title(
        f"{symbol} — RSI (14) ({len(df_display)}d okno)",
        color=_TEXT_COLOR, fontsize=12, fontweight="bold", pad=10,
    )

    ax.plot(display_idx, rsi_series, color=_RSI_COLOR, linewidth=1.6, label="RSI 14")

    # Linie poziome overbought / oversold
    ax.axhline(70, color="#ef4444", linewidth=0.8, linestyle="--", alpha=0.7, label="Overbought (70)")
    ax.axhline(30, color="#22c55e", linewidth=0.8, linestyle="--", alpha=0.7, label="Oversold (30)")
    ax.axhline(50, color=_AXIS_COLOR, linewidth=0.6, linestyle=":", alpha=0.5)

    # Kolorowe strefy — delikatne wypełnienie
    ax.fill_between(display_idx, 70, 100, alpha=0.06, color="#ef4444")
    ax.fill_between(display_idx, 0, 30,  alpha=0.06, color="#22c55e")

    ax.set_ylim(0, 100)
    ax.set_xlabel("Data", color=_TEXT_COLOR)
    ax.set_ylabel("RSI", color=_TEXT_COLOR)
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Wykres 4 — MACD
# ---------------------------------------------------------------------------

def _plot_macd(
    df: pd.DataFrame,
    df_display: pd.DataFrame,
    symbol: str,
) -> "matplotlib.figure.Figure":
    """Rysuj wykres MACD (12, 26, 9): linia MACD, Signal i histogram.

    Histogram wyświetlany jako słupki — zielone gdy dodatni (momentum rośnie),
    czerwone gdy ujemny (momentum spada). Crossover linii MACD/Signal widoczny
    jako punkt przecięcia dwóch linii.

    Args:
        df: Pełny DataFrame z kolumną ``price`` i datetime index.
        df_display: Fragment do wyświetlenia na osi X.
        symbol: Symbol kryptowaluty, np. ``"BTC"``.

    Returns:
        ``matplotlib.figure.Figure`` gotowa do zapisania.
    """
    macd_line, signal_line, histogram = macd(df["price"])
    display_idx = df_display.index

    macd_w    = macd_line.loc[display_idx]
    signal_w  = signal_line.loc[display_idx]
    hist_w    = histogram.loc[display_idx]

    fig, ax = plt.subplots()
    ax.set_title(
        f"{symbol} — MACD (12, 26, 9) ({len(df_display)}d okno)",
        color=_TEXT_COLOR, fontsize=12, fontweight="bold", pad=10,
    )

    # Histogram jako słupki (zielony/czerwony w zależności od znaku)
    colors = [_HIST_POS if v >= 0 else _HIST_NEG for v in hist_w]
    ax.bar(display_idx, hist_w, color=colors, alpha=0.5, label="Histogram", width=1.0)

    # Linie MACD i Signal
    ax.plot(display_idx, macd_w,   color=_MACD_COLOR,   linewidth=1.5, label="MACD")
    ax.plot(display_idx, signal_w, color=_SIGNAL_COLOR,  linewidth=1.5, label="Signal", linestyle="--")

    # Linia zerowa
    ax.axhline(0, color=_AXIS_COLOR, linewidth=0.6, linestyle=":")

    ax.set_xlabel("Data", color=_TEXT_COLOR)
    ax.set_ylabel("MACD", color=_TEXT_COLOR)
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def generate_price_charts(
    df: pd.DataFrame,
    symbol: str,
    output_dir: Path,
    export_date: date | None = None,
    window_days: int = config.PRICE_WINDOW_DAYS,
) -> list[Path]:
    """Generuj wykresy PNG dla danego symbolu i zapisz je na dysk.

    Zawsze próbuje stworzyć cztery pliki:
      - ``YYYY-MM-DD_{SYMBOL}_price.png``      — cena + nakładka SMA20/50/200
      - ``YYYY-MM-DD_{SYMBOL}_volatility.png`` — krocząca zmienność (30d rolling std)
      - ``YYYY-MM-DD_{SYMBOL}_rsi.png``        — RSI (14) z strefami 70/30
      - ``YYYY-MM-DD_{SYMBOL}_macd.png``       — MACD linia + Signal + histogram

    Domyślny zakres wykresu to ``config.PRICE_WINDOW_DAYS`` (spójne z oknem
    analizy tekstowej). SMA liczone jest zawsze na pełnym df — dla ostatnich
    N dni SMA200 ma zawsze poprawne wartości, bez NaN.

    ``export_date=None`` → używa ``date.today()`` w momencie wywołania
    (nie w momencie importu modułu — stąd domyślna wartość to None, nie date.today()).

    Jeśli matplotlib nie jest zainstalowany, loguje ostrzeżenie i zwraca ``[]``.
    Błąd podczas rysowania jednego wykresu nie blokuje drugiego.

    Args:
        df: DataFrame z kolumną ``price`` i datetime index rosnącym (z AlphaVantageClient).
        symbol: Symbol kryptowaluty, np. ``"BTC"``.
        output_dir: Katalog docelowy. Tworzony jeśli nie istnieje.
        export_date: Data użyta w nazwie pliku. Domyślnie: None.
        window_days: Liczba ostatnich dni widocznych na wykresie.
            Domyślnie: ``config.PRICE_WINDOW_DAYS`` (spójne z analizą).

    Returns:
        Lista ścieżek do zapisanych plików PNG.
    """
    if not _HAS_MATPLOTLIB:
        logger.warning("matplotlib nie jest zainstalowany — pomijam generację wykresów.")
        return []

    if export_date is None:
        export_date = date.today()

    _configure_style()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df_display = df.tail(window_days)
    stem = f"{export_date.isoformat()}_{symbol}"
    saved: list[Path] = []

    plots = [
        (f"{stem}_price.png",      _plot_price_with_ma, "wykresu cenowego"),
        (f"{stem}_volatility.png", _plot_volatility,    "wykresu zmienności"),
        (f"{stem}_rsi.png",        _plot_rsi,           "wykresu RSI"),
        (f"{stem}_macd.png",       _plot_macd,          "wykresu MACD"),
    ]

    for filename, plot_fn, label in plots:
        try:
            fig = plot_fn(df, df_display, symbol)
            path = output_dir / filename
            fig.savefig(str(path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            saved.append(path)
            logger.info("%s zapisany → %s", label.capitalize(), path)
        except Exception:
            logger.exception("Błąd podczas generowania %s dla %s", label, symbol)

    return saved
