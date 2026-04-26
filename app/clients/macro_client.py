"""
Macro context client — fetches global market indicators from FRED API.

Data sources (all via api.stlouisfed.org/fred):
  SP500            — S&P 500 index, daily
  VIXCLS           — CBOE VIX, daily
  DGS10            — 10-Year Treasury yield, daily
  DTWEXBGS         — Trade-Weighted USD Index (broad), weekly
  CPIAUCSL         — CPI All Urban Consumers, monthly
  FEDFUNDS         — Effective Fed Funds Rate, monthly

A free FRED API key is required (https://fred.stlouisfed.org/docs/api/api_key.html).
If FRED_API_KEY is not set, get_snapshot() returns an empty MacroSnapshot and the
pipeline continues without macro context — no exception is raised.
"""

import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import requests

from app.clients.cache import CacheManager
from app.config import CACHE_DIR

logger = logging.getLogger(__name__)

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_MACRO_CACHE_TTL_HOURS = 6.0


@dataclass
class MacroSnapshot:
    """Point-in-time snapshot of macro indicators relevant to financial markets."""

    # S&P 500
    sp500: float | None = None
    sp500_chg_1w_pct: float | None = None
    sp500_chg_ytd_pct: float | None = None

    # VIX
    vix: float | None = None

    # 10-Year Treasury Yield (%)
    yield_10y: float | None = None
    yield_10y_chg_1w_bp: float | None = None  # change in basis points

    # USD Index (trade-weighted broad, weekly — DTWEXBGS)
    dxy: float | None = None
    dxy_chg_1m_pct: float | None = None

    # CPI
    cpi_yoy_pct: float | None = None
    cpi_date: str | None = None  # YYYY-MM of latest observation

    # Fed Funds Rate
    fed_funds_rate: float | None = None

    def is_empty(self) -> bool:
        """Return True if no fields were populated."""
        return all(
            v is None for v in [
                self.sp500, self.vix, self.yield_10y,
                self.dxy, self.cpi_yoy_pct, self.fed_funds_rate,
            ]
        )


class MacroClient:
    """
    Fetches macro indicators from the FRED API with file-based caching.

    Each series is fetched and cached independently — a failure in one
    does not prevent the others from being collected.

    Args:
        api_key: FRED API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._cache = CacheManager.with_ttl_hours(
            f"{CACHE_DIR}/macro", _MACRO_CACHE_TTL_HOURS
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _fetch(self, series_id: str, limit: int = 30) -> list[dict]:
        """
        Fetch FRED observations for a series, most recent first.

        Args:
            series_id: FRED series identifier (e.g. "SP500").
            limit: Maximum number of observations to retrieve.

        Returns:
            List of dicts with 'date' (YYYY-MM-DD) and 'value' (str) keys.
            Observations where value == "." (FRED missing-data marker) are excluded.
        """
        cache_id = f"fred_{series_id}"
        cached, is_fresh = self._cache.get(cache_id)
        if is_fresh and cached:
            logger.debug("Macro cache hit: %s", series_id)
            return cached

        resp = requests.get(
            _FRED_BASE,
            params={
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        observations = [
            o for o in resp.json().get("observations", [])
            if o.get("value") not in (".", "", None)
        ]
        self._cache.set(cache_id, observations)
        logger.info("Fetched %d observations for %s from FRED", len(observations), series_id)
        return observations

    @staticmethod
    def _val(obs: list[dict], idx: int) -> float | None:
        """Safely return float value at index, or None."""
        try:
            return float(obs[idx]["value"])
        except (IndexError, ValueError, KeyError):
            return None

    @staticmethod
    def _pct_change(new: float | None, old: float | None) -> float | None:
        """Return percentage change, or None if either value is missing."""
        if new is None or old is None or old == 0:
            return None
        return (new / old - 1) * 100

    @staticmethod
    def _bp_change(new: float | None, old: float | None) -> float | None:
        """Return change in basis points, or None if either value is missing."""
        if new is None or old is None:
            return None
        return (new - old) * 100

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_snapshot(self) -> MacroSnapshot:
        """
        Fetch all macro indicators and return a point-in-time snapshot.

        All 7 FRED series are fetched in parallel via ThreadPoolExecutor — total
        wall time is max(individual fetch) instead of sum(all fetches).

        Returns:
            MacroSnapshot with available fields populated; failed fetches
            leave their fields as None — the pipeline continues regardless.
        """
        snap = MacroSnapshot()

        # S&P 500 — daily
        # limit=260: ~1 trading year, needed to find the first observation of the current
        # calendar year for the YTD (year-to-date, i.e. change since Jan 1) calculation.
        def fetch_sp500() -> None:
            sp = self._fetch("SP500", limit=260)
            snap.sp500 = self._val(sp, 0)
            # 1-week change: index 5 = ~5 trading days ago
            snap.sp500_chg_1w_pct = self._pct_change(snap.sp500, self._val(sp, 5))
            # YTD: first (earliest) observation dated in the current calendar year.
            # reversed(sp) = ascending order (oldest first), so next() returns the
            # earliest match and stops immediately — no need to scan the full list.
            if sp:
                current_year = sp[0]["date"][:4]
                ytd_base = next(
                    (float(o["value"]) for o in reversed(sp) if o["date"].startswith(current_year)),
                    None,
                )
                snap.sp500_chg_ytd_pct = self._pct_change(snap.sp500, ytd_base)

        # VIX — daily, only the latest value needed
        def fetch_vix() -> None:
            vix = self._fetch("VIXCLS", limit=1)
            snap.vix = self._val(vix, 0)

        # 10-Year Treasury Yield — daily
        # limit=6: latest + ~5 trading days back for 1-week change in basis points
        def fetch_yield_10y() -> None:
            y10 = self._fetch("DGS10", limit=6)
            snap.yield_10y = self._val(y10, 0)
            snap.yield_10y_chg_1w_bp = self._bp_change(snap.yield_10y, self._val(y10, 5))

        # USD Index broad trade-weighted — weekly
        # limit=5: 4 weekly intervals + 1 baseline = ~1 month of data
        # index -1 = oldest of the 5 fetched = ~4 weeks ago
        def fetch_dxy() -> None:
            dxy = self._fetch("DTWEXBGS", limit=5)
            snap.dxy = self._val(dxy, 0)
            snap.dxy_chg_1m_pct = self._pct_change(snap.dxy, self._val(dxy, -1))

        # CPI — monthly
        # YoY (year-over-year) = percentage change vs the same month 12 months ago.
        # Example: CPI Jan 2026 vs CPI Jan 2025 = annual inflation rate.
        # limit=14: gives 14 months, so index 0 = latest, index 12 = same month last year.
        # (2 extra months as buffer in case of data revisions or missing values)
        def fetch_cpi() -> None:
            cpi = self._fetch("CPIAUCSL", limit=14)
            snap.cpi_yoy_pct = self._pct_change(self._val(cpi, 0), self._val(cpi, 12))
            snap.cpi_date = cpi[0]["date"][:7] if cpi else None  # YYYY-MM

        # Fed Funds Rate — monthly, only the latest value needed
        def fetch_fed_funds() -> None:
            ff = self._fetch("FEDFUNDS", limit=1)
            snap.fed_funds_rate = self._val(ff, 0)

        tasks: list[tuple[str, Callable[[], None]]] = [
            ("S&P 500",        fetch_sp500),
            ("VIX",            fetch_vix),
            ("10Y yield",      fetch_yield_10y),
            ("USD Index",      fetch_dxy),
            ("CPI",            fetch_cpi),
            ("Fed Funds Rate", fetch_fed_funds),
        ]

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {executor.submit(fn): name for name, fn in tasks}
            for future in as_completed(futures):
                name = futures[future]
                exc = future.exception()
                if exc:
                    logger.warning("%s fetch failed: %s", name, exc)

        indicators = {
            "SP500": snap.sp500,
            "VIX": snap.vix,
            "10Y yield": snap.yield_10y,
            "USD Index": snap.dxy,
            "CPI YoY": snap.cpi_yoy_pct,
            "Fed Funds Rate": snap.fed_funds_rate,
        }
        populated = sum(1 for v in indicators.values() if v is not None)
        logger.info("Macro snapshot: %d/6 indicators populated", populated)
        if populated < 6:
            missing = [name for name, v in indicators.items() if v is None]
            logger.warning("Missing macro indicators: %s", ", ".join(missing))
        return snap

    def format_for_llm(self, snap: MacroSnapshot) -> str:
        """
        Render a MacroSnapshot as a compact, structured string for LLM prompts.

        Args:
            snap: MacroSnapshot from get_snapshot().

        Returns:
            Multi-line string, or empty string if no data is available.
        """
        if snap.is_empty():
            return ""

        lines: list[str] = []

        if snap.sp500 is not None:
            changes: list[str] = []
            if snap.sp500_chg_1w_pct is not None:
                changes.append(f"{snap.sp500_chg_1w_pct:+.1f}% WoW")
            if snap.sp500_chg_ytd_pct is not None:
                changes.append(f"{snap.sp500_chg_ytd_pct:+.1f}% YTD")
            suffix = f"  ({', '.join(changes)})" if changes else ""
            lines.append(f"S&P 500:         {snap.sp500:>8,.0f}{suffix}")

        if snap.vix is not None:
            zone = (
                "low — risk-on" if snap.vix < 15
                else "moderate" if snap.vix < 25
                else "elevated — caution" if snap.vix < 30
                else "high — risk-off"
            )
            lines.append(f"VIX:             {snap.vix:>8.1f}  ({zone})")

        if snap.yield_10y is not None:
            suffix = f"  ({snap.yield_10y_chg_1w_bp:+.0f}bp WoW)" if snap.yield_10y_chg_1w_bp is not None else ""
            lines.append(f"10Y Yield:       {snap.yield_10y:>7.2f}%{suffix}")

        if snap.dxy is not None:
            suffix = f"  ({snap.dxy_chg_1m_pct:+.1f}% vs last month)" if snap.dxy_chg_1m_pct is not None else ""
            lines.append(f"USD Index (DXY): {snap.dxy:>8.1f}{suffix}")

        if snap.cpi_yoy_pct is not None:
            lines.append(f"CPI YoY:         {snap.cpi_yoy_pct:>7.1f}%  ({snap.cpi_date})")

        if snap.fed_funds_rate is not None:
            lines.append(f"Fed Funds Rate:  {snap.fed_funds_rate:>7.2f}%")

        return "\n".join(lines)
