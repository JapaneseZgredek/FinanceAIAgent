"""
Report comparison module — deterministic field-level diff + optional LLM narrative drift.

Two modes depending on available report formats:
  Mode A (structured): both reports loaded as JSON → per-field FieldDiff tables + ListDiff for
                       events/risk_factors/sources.
  Mode B (markdown fallback): at least one report only has .md → section-based unified_diff via
                               difflib; same narrative drift LLM step appended.

Auto-generation: if today's report is missing and auto_generate_today=True, the full pipeline
(claude_runner.run()) is triggered silently before diffing. Past dates cannot be regenerated.
"""

import difflib
import json
import logging
import re
import time
from collections.abc import Callable, Hashable
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from app import config
from app.utils.errors import FinanceAgentError

logger = logging.getLogger(__name__)

_CLAUDE_TIMEOUT = 180

# Ordered list of metric keys to diff — defines display order, ignores unexpected JSON keys
_METRIC_KEYS = [
    "rsi",
    "macd_position",
    "price_vs_sma20",
    "price_vs_sma50",
    "price_vs_sma200",
    "atr_direction",
    "volatility_regime",
    "volume_vs_30d_avg",
]

_MACRO_KEYS = ["fed_funds_rate", "fomc_days_away", "expected_action"]

_HORIZON_KEYS = ["short_term", "medium_term", "long_term"]

_TRADING_KEYS = ["direction", "leverage_min", "leverage_max"]

# Leaf-level JSON values that can appear in a report field — used for type-safe FieldDiff.
_ScalarValue = str | int | float | bool | None


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class FieldDiff:
    """Diff result for a single scalar field (e.g. RSI, sentiment label, final_decision).

    Attributes:
        field:   Human-readable field name used in rendered tables (e.g. "rsi", "sentiment.label").
        base:    Value from the older (base) report.
        compare: Value from the newer (compare) report.
        changed: True when base != compare. Renderer uses this to highlight rows.
        delta:   Numeric difference (compare - base) for int/float fields; None for categorical
                 fields like "above"/"below" or "ENTER"/"WAIT" where subtraction is meaningless.
    """

    field: str
    base: _ScalarValue
    compare: _ScalarValue
    changed: bool
    delta: float | None = None


@dataclass
class ListDiff:
    """Diff result for a list of dicts compared by a key function (events, risk_factors, sources).

    Items are matched by a semantic key (e.g. (description, source) for events,
    (category, severity) for risk_factors) — not by list position.

    Attributes:
        added:     Items present in compare but absent in base (new since last report).
        removed:   Items present in base but absent in compare (resolved/dropped).
        unchanged: Items present in both (same key matched in both reports).
    """

    added: list[dict]
    removed: list[dict]
    unchanged: list[dict]


@dataclass
class ComparisonResult:
    """Full diff between two reports for the same symbol.

    Attributes:
        symbol:           Ticker, e.g. "BTC".
        base_date:        Date of the older report.
        compare_date:     Date of the newer report.
        mode:             "structured" when both reports were JSON (full field-level diff);
                          "markdown_fallback" when at least one was only .md (section diff only).
        auto_generated:   True if today's missing report was generated on-the-fly during this run.
                          At most one report can ever be auto-generated (past dates can't be
                          regenerated, and base==compare is rejected at validation).
        sentiment:        Diff of sentiment.label (Positive/Negative/Mixed). None in markdown mode.
        final_decision:   Diff of prediction.final_decision (ENTER/WAIT/NO). None in markdown mode.
        pre_decision:     Diff of prediction.pre_decision — the deterministic signal from
                          compute_pre_decision() before any LLM override. None in markdown mode.
        override_applied: Diff of prediction.override_applied — True when Claude overrode
                          pre_decision via FOMC proximity or HIGH risk factor rules. None in markdown mode.
        metrics:          Ordered list of FieldDiffs for RSI, MACD, price vs SMA20/50/200, ATR,
                          volatility regime, volume. Order follows _METRIC_KEYS. None in markdown mode.
        horizons:         Dict keyed by "short_term"/"medium_term"/"long_term", each holding
                          FieldDiffs for signal_state and direction. Empty dict in markdown mode.
        macro:            FieldDiffs for fed_funds_rate, fomc_days_away, expected_action. Empty in markdown mode.
        risk_factors:     ListDiff by (category, severity) key. None in markdown mode.
        events:           ListDiff by (normalized_description, source) key. None in markdown mode.
        trading:          FieldDiffs for direction, leverage_min, leverage_max. Empty in markdown mode.
        sources:          ListDiff by (domain, tier) key. None in markdown mode.
        section_diff_text: Raw unified diff output per markdown section. Populated in markdown mode only.
        narrative_drift:  4–7 sentence LLM summary of *why* things changed. None when
                          include_narrative=False or LLM call failed (graceful degradation).
    """

    symbol: str
    base_date: date
    compare_date: date
    mode: Literal["structured", "markdown_fallback"]
    auto_generated: bool
    sentiment: FieldDiff | None
    final_decision: FieldDiff | None
    pre_decision: FieldDiff | None
    override_applied: FieldDiff | None
    metrics: list[FieldDiff]
    horizons: dict[str, list[FieldDiff]]
    macro: list[FieldDiff]
    risk_factors: ListDiff | None
    events: ListDiff | None
    trading: list[FieldDiff]
    sources: ListDiff | None
    section_diff_text: str | None
    narrative_drift: str | None


@dataclass
class LoadedReport:
    """A report loaded from disk (or freshly auto-generated) for one symbol+date.

    Attributes:
        date:           The report date parsed from the filename (YYYY-MM-DD_SYMBOL).
        format:         "json" if a .json file was found; "markdown" if only .md existed.
                        Determines which diff mode (Mode A vs Mode B) is used.
        data:           Parsed dict when format="json"; raw text string when format="markdown".
        auto_generated: True if the file did not exist and was created by running the pipeline
                        during this comparison call (only possible for date.today()).
    """

    date: date
    format: Literal["json", "markdown"]
    data: dict | str
    auto_generated: bool


# =============================================================================
# Loading + auto-generation
# =============================================================================


async def _load_report_data(
    symbol: str,
    target_date: date,
    *,
    auto_generate_today: bool,
    auto_generate_format: Literal["json", "markdown"] = "json",
    reports_dir: Path,
    language: str,
    alpha_client,
    claude_client,
    macro_client,
) -> LoadedReport:
    json_path = reports_dir / f"{target_date.isoformat()}_{symbol}.json"
    md_path = reports_dir / f"{target_date.isoformat()}_{symbol}.md"

    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return LoadedReport(date=target_date, format="json", data=data, auto_generated=False)

    if md_path.exists():
        data = md_path.read_text(encoding="utf-8")
        return LoadedReport(date=target_date, format="markdown", data=data, auto_generated=False)

    if target_date == date.today() and auto_generate_today:
        # Generate in the same format as the base report so both sides end up in the same
        # diff mode — avoids landing in markdown_fallback with a raw JSON string on one side.
        logger.info(
            "Auto-generating today's report for diff… (symbol=%s, format=%s)",
            symbol, auto_generate_format,
        )
        from app.claude_runner import run
        result = await run(
            symbol,
            language=language,
            output_format=auto_generate_format,
            alpha_client=alpha_client,
            claude_client=claude_client,
            macro_client=macro_client,
        )
        reports_dir.mkdir(exist_ok=True)
        if auto_generate_format == "json":
            json_path.write_text(result, encoding="utf-8")
            return LoadedReport(date=target_date, format=auto_generate_format, data=json.loads(result), auto_generated=True)
        else:
            md_path.write_text(result, encoding="utf-8")
            return LoadedReport(date=target_date, format=auto_generate_format, data=result, auto_generated=True)

    raise FinanceAgentError(
        message=f"No report found for {symbol} on {target_date.isoformat()}",
        hint="Past reports cannot be regenerated retroactively. Only today's missing report can be auto-generated.",
    )


# =============================================================================
# Deterministic diff helpers
# =============================================================================


def _diff_scalar(field_name: str, base_val: _ScalarValue, compare_val: _ScalarValue) -> FieldDiff:
    changed = base_val != compare_val
    delta: float | None = None
    if changed and isinstance(base_val, (int, float)) and isinstance(compare_val, (int, float)):
        delta = float(compare_val) - float(base_val)
    return FieldDiff(field=field_name, base=base_val, compare=compare_val, changed=changed, delta=delta)


def _diff_list_by_keyfn(
    base_list: list[dict],
    compare_list: list[dict],
    key_fn: Callable[[dict], Hashable],
) -> ListDiff:
    base_index = {key_fn(item): item for item in base_list}
    compare_index = {key_fn(item): item for item in compare_list}

    added = [compare_index[k] for k in compare_index if k not in base_index]
    removed = [base_index[k] for k in base_index if k not in compare_index]
    unchanged = [base_index[k] for k in base_index if k in compare_index]

    return ListDiff(added=added, removed=removed, unchanged=unchanged)


def _diff_dict_by_keys(base: dict, compare: dict, keys: list[str]) -> list[FieldDiff]:
    return [_diff_scalar(k, base.get(k), compare.get(k)) for k in keys]


def _diff_horizons(base_horizons: dict, compare_horizons: dict) -> dict[str, list[FieldDiff]]:
    result: dict[str, list[FieldDiff]] = {}
    for horizon in _HORIZON_KEYS:
        base_h = base_horizons.get(horizon, {}) or {}
        compare_h = compare_horizons.get(horizon, {}) or {}
        diffs = [
            _diff_scalar("signal_state", base_h.get("signal_state"), compare_h.get("signal_state")),
            _diff_scalar("direction", base_h.get("direction"), compare_h.get("direction")),
        ]
        result[horizon] = diffs
    return result


def _event_key(event: dict) -> tuple[str, str]:
    desc = event.get("description", "").lower().strip()
    for prefix in ("breaking: ", "update: ", "breaking:", "update:"):
        if desc.startswith(prefix):
            desc = desc[len(prefix):].strip()
    source = event.get("source", "").lower().strip()
    return (desc, source)


def _risk_key(risk: dict) -> tuple[str, str]:
    return (risk.get("category", ""), risk.get("severity", ""))


def _source_key(source: dict) -> tuple[str, int]:
    return (source.get("domain", "").lower(), source.get("tier", 0))


# =============================================================================
# Mode A — structured JSON diff
# =============================================================================


def _diff_json_reports(base: dict, compare: dict) -> dict:
    sentiment = _diff_scalar(
        "sentiment.label",
        (base.get("sentiment") or {}).get("label"),
        (compare.get("sentiment") or {}).get("label"),
    )

    base_pred = base.get("prediction") or {}
    compare_pred = compare.get("prediction") or {}
    final_decision = _diff_scalar("final_decision", base_pred.get("final_decision"), compare_pred.get("final_decision"))
    pre_decision = _diff_scalar("pre_decision", base_pred.get("pre_decision"), compare_pred.get("pre_decision"))
    override_applied = _diff_scalar("override_applied", base_pred.get("override_applied"), compare_pred.get("override_applied"))

    # dict diffs — fixed key lists, preserve display order
    metrics = _diff_dict_by_keys(base.get("metrics") or {}, compare.get("metrics") or {}, _METRIC_KEYS)
    horizons = _diff_horizons(base.get("horizons") or {}, compare.get("horizons") or {})
    macro = _diff_dict_by_keys(base.get("macro") or {}, compare.get("macro") or {}, _MACRO_KEYS)
    trading = _diff_dict_by_keys(base.get("trading") or {}, compare.get("trading") or {}, _TRADING_KEYS)

    # list diffs — matched by semantic key function, not by position
    risk_factors = _diff_list_by_keyfn(base.get("risk_factors") or [], compare.get("risk_factors") or [], _risk_key)
    events = _diff_list_by_keyfn(base.get("events") or [], compare.get("events") or [], _event_key)
    sources = _diff_list_by_keyfn(base.get("sources") or [], compare.get("sources") or [], _source_key)

    return dict(
        sentiment=sentiment,
        final_decision=final_decision,
        pre_decision=pre_decision,
        override_applied=override_applied,
        metrics=metrics,
        horizons=horizons,
        macro=macro,
        risk_factors=risk_factors,
        events=events,
        trading=trading,
        sources=sources,
    )


# =============================================================================
# Mode B — markdown section fallback
# =============================================================================


def _parse_markdown_sections(text: str) -> dict[str, str]:
    parts = re.split(r"^##\s+", text, flags=re.MULTILINE)
    sections: dict[str, str] = {}
    for part in parts[1:]:
        newline_pos = part.find("\n")
        if newline_pos == -1:
            heading, body = part.strip(), ""
        else:
            heading = part[:newline_pos].strip()
            body = part[newline_pos + 1:]
        sections[heading] = body
    return sections


def _diff_markdown_reports(base_text: str, compare_text: str) -> str:
    base_sections = _parse_markdown_sections(base_text)
    compare_sections = _parse_markdown_sections(compare_text)

    base_keys = set(base_sections)
    compare_keys = set(compare_sections)
    common_keys = base_keys & compare_keys

    if not common_keys:
        return (
            "_Section-level diff unavailable — base report uses a different heading set than compare "
            "(likely different output languages). See narrative drift below._"
        )

    lines: list[str] = []

    added_headings = compare_keys - base_keys
    removed_headings = base_keys - compare_keys
    if added_headings:
        lines.append(f"**New sections:** {', '.join(sorted(added_headings))}")
    if removed_headings:
        lines.append(f"**Removed sections:** {', '.join(sorted(removed_headings))}")

    for heading in sorted(common_keys):
        diff = list(difflib.unified_diff(
            base_sections[heading].splitlines(),
            compare_sections[heading].splitlines(),
            lineterm="",
            n=1,
        ))
        changed_lines = [l for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        if not changed_lines:
            continue
        lines.append(f"\n### {heading}")
        lines.append("```diff")
        lines.extend(diff)
        lines.append("```")

    if not lines:
        return "_No textual differences found in shared sections._"

    return "\n".join(lines)


# =============================================================================
# Narrative drift (LLM step)
# =============================================================================


def _extract_narrative_excerpt(loaded: LoadedReport) -> str:
    if loaded.format == "json" and isinstance(loaded.data, dict):
        d = loaded.data
        parts: list[str] = []

        sentiment = (d.get("sentiment") or {})
        if sentiment.get("summary"):
            parts.append(f"Sentiment: {sentiment['label']} — {sentiment['summary']}")

        events = d.get("events") or []
        if events:
            parts.append("Events:")
            for e in events:
                parts.append(f"  - {e.get('description', '')} ({e.get('source', '')}, {e.get('date', '')})")

        risks = d.get("risk_factors") or []
        if risks:
            parts.append("Risk factors:")
            for r in risks:
                parts.append(f"  - [{r.get('severity','').upper()}] {r.get('category','')} — {r.get('signal_basis','')}")

        watch = d.get("watch_next") or {}
        watch_items: list[str] = []
        for subcategory in watch.values():
            if isinstance(subcategory, list):
                watch_items.extend(subcategory)
        if watch_items:
            parts.append("Watch next:")
            for item in watch_items:
                parts.append(f"  - {item}")

        return "\n".join(parts)


async def _run_narrative_drift_llm(
    symbol: str,
    base: LoadedReport,
    compare: LoadedReport,
    structural_summary: str,
    language: str,
    claude_client,
    *,
    diff_text: str | None = None,
) -> str | None:
    from app.prompts import build_comparison_narrative_prompt

    if claude_client is None:
        from app.clients.claude_client import ClaudeClient
        claude_client = ClaudeClient(model=config.CLAUDE_MODEL, timeout=_CLAUDE_TIMEOUT)

    if diff_text is not None:
        prompt = build_comparison_narrative_prompt(
            symbol=symbol,
            base_date=base.date,
            compare_date=compare.date,
            structural_summary=structural_summary,
            language=language,
            diff_text=diff_text,
        )
    else:
        prompt = build_comparison_narrative_prompt(
            symbol=symbol,
            base_date=base.date,
            compare_date=compare.date,
            structural_summary=structural_summary,
            language=language,
            base_excerpt=_extract_narrative_excerpt(base),
            compare_excerpt=_extract_narrative_excerpt(compare),
        )

    try:
        t0 = time.perf_counter()
        result = await claude_client.run(prompt, allowed_tools="")
        logger.info("Narrative drift LLM step completed in %.1fs", time.perf_counter() - t0)
        return result
    except Exception as exc:
        logger.warning("Narrative drift LLM step failed — skipping: %s", exc)
        return None


# =============================================================================
# Renderers
# =============================================================================


def _fmt_delta(delta: float | None) -> str:
    if delta is None:
        return "—"
    sign = "+" if delta > 0 else ""
    if isinstance(delta, float) and not delta.is_integer():
        return f"{sign}{delta:.2f}"
    return f"{sign}{int(delta)}"


def _fmt_changed(d: FieldDiff) -> str:
    return "changed" if d.changed else "unchanged"


def _render_markdown(result: ComparisonResult) -> str:
    lines: list[str] = []

    auto_note = " *(auto-generated)*" if result.auto_generated else ""
    lines.append(f"# Report Comparison: {result.symbol}")
    lines.append(f"**Base:** {result.base_date}  →  **Compare:** {result.compare_date}{auto_note}")
    lines.append(f"**Mode:** {result.mode}")
    lines.append("")

    if result.mode == "structured":
        # Sentiment
        lines.append("## Sentiment")
        if result.sentiment:
            s = result.sentiment
            lines.append(f"{s.base} → {s.compare}  *({_fmt_changed(s)})*")
        lines.append("")

        # Decision
        lines.append("## Decision")
        lines.append("| Field | Base | Compare | Status |")
        lines.append("|---|---|---|---|")
        for d in [result.final_decision, result.pre_decision, result.override_applied]:
            if d:
                lines.append(f"| {d.field} | {d.base} | {d.compare} | {_fmt_changed(d)} |")
        lines.append("")

        # Metrics
        lines.append("## Metrics")
        lines.append("| Metric | Before | After | Δ |")
        lines.append("|---|---|---|---|")
        for m in result.metrics:
            lines.append(f"| {m.field} | {m.base} | {m.compare} | {_fmt_delta(m.delta)} |")
        lines.append("")

        # Horizons
        lines.append("## Horizons")
        for horizon, diffs in result.horizons.items():
            lines.append(f"### {horizon.replace('_', ' ').title()}")
            for d in diffs:
                lines.append(f"- {d.field}: {d.base} → {d.compare}  *({_fmt_changed(d)})*")
        lines.append("")

        # Macro
        lines.append("## Macro backdrop")
        lines.append("| Field | Before | After | Δ |")
        lines.append("|---|---|---|---|")
        for m in result.macro:
            lines.append(f"| {m.field} | {m.base} | {m.compare} | {_fmt_delta(m.delta)} |")
        lines.append("")

        # Risk factors
        if result.risk_factors:
            rf = result.risk_factors
            lines.append("## Risk factors")
            if rf.added:
                lines.append(f"**New ({len(rf.added)}):**")
                for r in rf.added:
                    lines.append(f"- [{r.get('severity','').upper()}] {r.get('category','')} — {r.get('signal_basis','')}")
            if rf.removed:
                lines.append(f"**Resolved ({len(rf.removed)}):**")
                for r in rf.removed:
                    lines.append(f"- [{r.get('severity','').upper()}] {r.get('category','')}")
            if rf.unchanged:
                lines.append(f"**Persistent ({len(rf.unchanged)}):**")
                for r in rf.unchanged:
                    lines.append(f"- [{r.get('severity','').upper()}] {r.get('category','')}")
            lines.append("")

        # Events
        if result.events:
            ev = result.events
            lines.append("## News events")
            if ev.added:
                lines.append(f"**New ({len(ev.added)}):**")
                for e in ev.added:
                    lines.append(f"- {e.get('description','')} — {e.get('source','')} ({e.get('date','')})")
            if ev.removed:
                lines.append(f"**Dropped ({len(ev.removed)}):**")
                for e in ev.removed:
                    lines.append(f"- {e.get('description','')} — {e.get('source','')} ({e.get('date','')})")
            lines.append("")

        # Trading
        lines.append("## Trading")
        for d in result.trading:
            lines.append(f"- {d.field}: {d.base} → {d.compare}  *({_fmt_changed(d)})*")
        lines.append("")

    else:
        # Mode B
        lines.append("## Section diff")
        if result.section_diff_text:
            lines.append(result.section_diff_text)
        lines.append("")

    # Narrative drift
    lines.append("## Narrative drift")
    if result.narrative_drift:
        lines.append(result.narrative_drift)
    else:
        lines.append("_(narrative drift not requested or unavailable)_")
    lines.append("")

    lines.append(f"---\n*Generated {result.compare_date}*")

    return "\n".join(lines)


def _render_json(result: ComparisonResult) -> str:
    return json.dumps(asdict(result), indent=2, ensure_ascii=False, default=str)


# =============================================================================
# Persistence
# =============================================================================


def _save_comparison(
    content: str,
    base_date: date,
    compare_date: date,
    symbol: str,
    output_format: str,
    reports_dir: Path,
) -> Path:
    reports_dir.mkdir(exist_ok=True)
    ext = "json" if output_format == "json" else "md"
    path = reports_dir / f"comparison_{base_date}_{compare_date}_{symbol}.{ext}"
    path.write_text(content, encoding="utf-8")
    logger.info("Comparison saved → %s", path)
    return path


# =============================================================================
# Public API
# =============================================================================


async def compare_reports(
    symbol: str,
    base_date: date | None = None,
    compare_date: date | None = None,
    *,
    output_format: Literal["markdown", "json"] = "markdown",
    language: str = "Polish",
    include_narrative: bool = True,
    auto_generate_today: bool = True,
    reports_dir: Path = Path("reports"),
    alpha_client=None,
    claude_client=None,
    macro_client=None,
) -> str:
    """
    Compare two saved reports for the same symbol and return a diff summary.

    Args:
        symbol: Cryptocurrency ticker, e.g. ``"BTC"``.
        base_date: Older report date (default: yesterday).
        compare_date: Newer report date (default: today).
        output_format: ``"markdown"`` or ``"json"``.
        language: Language for narrative drift section.
        include_narrative: If True, run an LLM step to summarise why metrics changed.
        auto_generate_today: If True and today's report is missing, auto-generate it.
        reports_dir: Directory where reports are stored.
        alpha_client: Optional AlphaVantageClient for dependency injection.
        claude_client: Optional ClaudeClient for DI (narrative step + auto-gen).
        macro_client: Optional MacroClient for DI (auto-gen pipeline).

    Returns:
        Formatted comparison string (markdown or JSON).

    Raises:
        FinanceAgentError: If symbol is empty, dates are equal, or a past report is missing.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise FinanceAgentError("Symbol cannot be empty", hint="Enter a ticker like BTC, ETH, or SOL.")

    today = date.today()
    if base_date is None:
        base_date = today - timedelta(days=1)
    if compare_date is None:
        compare_date = today

    if base_date == compare_date:
        raise FinanceAgentError(
            "base_date and compare_date must differ",
            hint="Comparing a report with itself produces no useful output.",
        )

    if base_date > compare_date:
        base_date, compare_date = compare_date, base_date
        logger.info("Dates were swapped — base_date must be earlier than compare_date")

    logger.info(
        "Comparing %s: %s → %s (format=%s, narrative=%s)",
        symbol, base_date, compare_date, output_format, include_narrative,
    )

    shared_kwargs = dict(
        reports_dir=reports_dir,
        language=language,
        alpha_client=alpha_client,
        claude_client=claude_client,
        macro_client=macro_client,
    )

    # Load base first — its format determines what we auto-generate for compare,
    # so both sides end up in the same diff mode.
    base_report = await _load_report_data(
        symbol, base_date, auto_generate_today=False, **shared_kwargs
    )
    compare_report = await _load_report_data(
        symbol, compare_date, auto_generate_today=auto_generate_today,
        auto_generate_format=base_report.format, **shared_kwargs
    )

    auto_generated = base_report.auto_generated or compare_report.auto_generated

    if base_report.format != compare_report.format:
        raise FinanceAgentError(
            message=f"Cannot compare reports with different formats: base is {base_report.format}, compare is {compare_report.format}",
            hint="Both reports must be the same format (.json or .md). Re-generate one of them in the matching format.",
        )

    mode: Literal["structured", "markdown_fallback"]
    if base_report.format == "json" and compare_report.format == "json":
        mode = "structured"
        diff_fields = _diff_json_reports(base_report.data, compare_report.data)

        structural_summary = _build_structural_summary(diff_fields)

        result = ComparisonResult(
            symbol=symbol,
            base_date=base_date,
            compare_date=compare_date,
            mode=mode,
            auto_generated=auto_generated,
            sentiment=diff_fields["sentiment"],
            final_decision=diff_fields["final_decision"],
            pre_decision=diff_fields["pre_decision"],
            override_applied=diff_fields["override_applied"],
            metrics=diff_fields["metrics"],
            horizons=diff_fields["horizons"],
            macro=diff_fields["macro"],
            risk_factors=diff_fields["risk_factors"],
            events=diff_fields["events"],
            trading=diff_fields["trading"],
            sources=diff_fields["sources"],
            section_diff_text=None,
            narrative_drift=None,
        )
    else:
        mode = "markdown_fallback"
        section_diff_text = _diff_markdown_reports(
            base_report.data, compare_report.data  # type: ignore[arg-type]
        )
        structural_summary = "Markdown fallback mode — section-level diff only."

        result = ComparisonResult(
            symbol=symbol,
            base_date=base_date,
            compare_date=compare_date,
            mode=mode,
            auto_generated=auto_generated,
            sentiment=None,
            final_decision=None,
            pre_decision=None,
            override_applied=None,
            metrics=[],
            horizons={},
            macro=[],
            risk_factors=None,
            events=None,
            trading=[],
            sources=None,
            section_diff_text=section_diff_text,
            narrative_drift=None,
        )

    if include_narrative:
        result.narrative_drift = await _run_narrative_drift_llm(
            symbol=symbol,
            base=base_report,
            compare=compare_report,
            structural_summary=structural_summary,
            language=language,
            claude_client=claude_client,
            diff_text=result.section_diff_text,
        )

    rendered = _render_json(result) if output_format == "json" else _render_markdown(result)
    _save_comparison(rendered, base_date, compare_date, symbol, output_format, reports_dir)
    return rendered


def _build_structural_summary(diff_fields: dict) -> str:
    parts: list[str] = []

    sentiment = diff_fields.get("sentiment")
    if sentiment and sentiment.changed:
        parts.append(f"Sentiment: {sentiment.base} → {sentiment.compare}")

    final = diff_fields.get("final_decision")
    if final and final.changed:
        parts.append(f"Decision: {final.base} → {final.compare}")

    changed_metrics = [m for m in (diff_fields.get("metrics") or []) if m.changed]
    for m in changed_metrics:
        delta_str = f" (Δ{_fmt_delta(m.delta)})" if m.delta is not None else ""
        parts.append(f"{m.field}: {m.base} → {m.compare}{delta_str}")

    events_diff = diff_fields.get("events")
    if events_diff:
        if events_diff.added:
            parts.append(f"New events: {len(events_diff.added)}")
        if events_diff.removed:
            parts.append(f"Dropped events: {len(events_diff.removed)}")

    risk_diff = diff_fields.get("risk_factors")
    if risk_diff:
        if risk_diff.added:
            new_rf = [f"{r.get('category')}/{r.get('severity')}" for r in risk_diff.added]
            parts.append(f"New risk factors: {', '.join(new_rf)}")
        if risk_diff.removed:
            res_rf = [f"{r.get('category')}/{r.get('severity')}" for r in risk_diff.removed]
            parts.append(f"Resolved risk factors: {', '.join(res_rf)}")

    return "; ".join(parts) if parts else "No significant structural changes detected."
