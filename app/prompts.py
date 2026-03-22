"""
Prompt builders for the three Claude CLI pipeline steps.

Each function accepts runtime data and returns a ready-to-send prompt string.
All prompts are in English — Step 3 instructs Claude to translate the output
to the requested language; Steps 1 and 2 are internal pipeline data only.
"""


def build_news_prompt(
    symbol: str,
    today: str,
    news_days_back: int,
    tier1_sources: list[str],
    tier2_sources: list[str],
    blocked_sources: list[str],
) -> str:
    """
    Build the Step 1 prompt: web news search for a cryptocurrency symbol.

    Args:
        symbol: Cryptocurrency ticker (e.g. "BTC").
        today: Current date string (YYYY-MM-DD).
        news_days_back: How many days back to search for news.
        tier1_sources: High-trust domains to prioritise with site: operator.
        tier2_sources: Supplementary domains requiring cross-check.
        blocked_sources: Domains to discard immediately.

    Returns:
        Prompt string for Claude CLI with WebSearch/WebFetch tools.
    """
    tier1_site_query = " OR ".join(f"site:{d}" for d in tier1_sources)
    tier2_site_query = " OR ".join(f"site:{d}" for d in tier2_sources)
    tier1_list = ", ".join(tier1_sources)
    tier2_list = ", ".join(tier2_sources)
    blocked_list = ", ".join(blocked_sources)
    today_year = today[:4]

    return f"""\
Today is {today}. Search the web for recent news about the {symbol} cryptocurrency \
from the last {news_days_back} days, and separately look up the current Fed / FOMC macro backdrop.

=== SEARCH STRATEGY ===
Execute ALL three searches below — searches 1 and 2 are for crypto news, search 3 is always required:

1. Primary crypto search (Tier 1 sources only):
   Query: "{symbol} cryptocurrency news" ({tier1_site_query})

2. Supplementary crypto search (Tier 2 sources) ONLY if search 1 yields fewer than 3 relevant events:
   Query: "{symbol} crypto news" ({tier2_site_query})

3. FOMC / Fed macro search (always execute, independent of crypto news results):
   Goal: find the next scheduled FOMC meeting date, the current Fed Funds rate, and any
   recent Fed statements, dot-plot updates, or minutes published in the last {news_days_back} days.
   Recommended sources: federalreserve.gov (official), finance.yahoo.com, coindesk.com.
   Queries to try (use whichever returns results):
     a) "FOMC meeting schedule {today_year}" site:federalreserve.gov
     b) "Federal Reserve rate decision {today_year}"
     c) "Fed FOMC next meeting date {today_year}"

=== SOURCE RELIABILITY RULES ===
TIER 1 — HIGH TRUST: {tier1_list}
  These sites provide analyst-attributed content with verifiable data. Prefer these.

TIER 2 — MODERATE TRUST: {tier2_list}
  Use only as supplementary. MANDATORY: cross-check any Tier 2 claim against a Tier 1 source.
  If a Tier 2 article cannot be corroborated, do NOT include the claim.

BLOCKED — NEVER USE: {blocked_list}
  These domains publish AI-generated price-prediction content with zero analytical value.
  Discard any result from these domains immediately, regardless of headline.

OFFICIAL / MACRO SOURCES (search 3 only — not subject to Tier rules):
  federalreserve.gov — official Fed calendar and statements; treat as highest trust.
  finance.yahoo.com, coindesk.com — acceptable for FOMC date confirmation.

=== CRITICAL VERIFICATION REQUIREMENTS ===
Before including any piece of information you MUST verify:
  1. FRESHNESS: Check the article publication date. Only include events from the last \
{news_days_back} days (after {today} minus {news_days_back} days).
     Reject any article without a visible publication date.
     EXCEPTION: FOMC meeting dates are future events — include them regardless of when
     the calendar was published, as long as the meeting date itself is upcoming.
  2. SOURCE CREDIBILITY: Confirm the domain matches a Tier 1, Tier 2, or Official/Macro entry.
     Do not trust a site just because it appears in search results.
  3. SPECIFICITY: The event must name a concrete catalyst (a regulator, institution,
     fund, or protocol). Vague headlines like 'Bitcoin may rise' are not market-moving events.
  4. CORROBORATION: If only one source reports an event, mark it as
     '(unconfirmed — single source)' in your output.

=== FOCUS ===
Crypto events: regulatory actions, major partnerships, exchange listings, ETF inflows/outflows,
protocol upgrades, exchange hacks, on-chain catalysts.
Macro (search 3): next FOMC meeting date, current Fed Funds rate, recent rate decisions,
Fed statements or minutes, market expectations for the next decision (cut / hold / hike).
Skip: educational articles, price predictions without catalysts, general explanations.

=== OUTPUT FORMAT ===
## Market Events
- [event description] (Source: domain.com, Date: YYYY-MM-DD, Tier: 1|2)
(3-5 bullet points only)

## Sentiment
Positive / Negative / Mixed — one sentence explanation.

## News Tendency
1-2 sentences describing the directional tendency from the news events. \
No binary label. Describe which direction the events collectively point toward \
and why — or state that signals are mixed if no clear tendency emerges.

## Fed / Macro Backdrop
- Current Fed Funds rate: [X.XX%] (if found)
- Next FOMC meeting: [YYYY-MM-DD] — [X days away] (if found; state "not found" if search failed)
- Expected rate action: [cut / hold / hike] based on current market consensus (if found)
- Recent Fed statement: [key sentence or decision] (only if published within the last \
{news_days_back} days; omit this line if nothing recent)

Respond in English."""


def build_price_analysis_prompt(
    symbol: str,
    price_data: str,
    macro_context: str | None = None,
) -> str:
    """
    Build the Step 2 prompt: technical and macro analysis of pre-computed data.

    Args:
        symbol: Cryptocurrency ticker.
        price_data: Formatted string from get_formatted_price_data().
        macro_context: Formatted macro snapshot from MacroClient, or None if unavailable.

    Returns:
        Prompt string for Claude CLI (no web access).
    """
    macro_section = ""
    if macro_context:
        macro_section = f"""
=== MACRO CONTEXT ===
{macro_context}

Macro interpretation guidelines:
- DXY rising (USD strengthening): historically bearish headwind for risk assets including crypto
- S&P 500 declining: risk-off environment — watch for correlation-driven crypto weakness
- VIX > 25: elevated fear — institutional selling likely across risk assets
- 10Y yield rising: tighter financial conditions — compresses valuations of yield-less assets
- CPI above 3%: inflationary pressure → potentially hawkish Fed → USD strength risk
- Gold rising alongside crypto: broad dollar weakness / store-of-value demand
- Gold rising while crypto falls: risk-off rotation to traditional safe haven
"""

    return f"""\
You are a quantitative market analyst. \
Analyze the following data for {symbol}.

=== PRICE DATA AND INDICATORS ===
{price_data}{macro_section}
Produce a structured signal report grouped by time horizon. \
For each horizon, report the specific indicator values and what they indicate.

## Short-term signals (1–7 days)
Momentum: RSI value and zone (oversold <40 / neutral 40–60 / overbought >60), \
MACD position relative to signal line (above = bullish momentum / below = bearish), \
volume vs. 30-day average (above = strong conviction / below = weak conviction).

## Medium-term signals (2–6 weeks)
Trend structure: price vs. SMA20 / SMA50 / SMA200 (above or below each), \
ATR trend (expanding = volatility rising / contracting = compression before breakout), \
key support/resistance levels from moving averages.

## Long-term signals (3–6 months)
SMA200 direction and slope (rising / flat / falling), \
overall market structure (bullish above SMA200 / bearish below / transitional).

## Macro backdrop
Only include this section if macro context was provided above. \
In 2–3 sentences: how do the current macro conditions (DXY, VIX, yields, gold, CPI, Fed rate) \
frame the risk environment for {symbol}? Name the dominant macro force and whether it \
reinforces or conflicts with the technical picture. \
If no macro context was provided, omit this section entirely.

Do NOT search the web. Use only the provided data. Respond in English."""


def build_final_report_prompt(
    symbol: str,
    news_analysis: str,
    price_analysis: str,
    language: str,
    today: str,
) -> str:
    """
    Build the Step 3 prompt: synthesise news + price analysis into the final report.

    Args:
        symbol: Cryptocurrency ticker.
        news_analysis: Output from Step 1 (English).
        price_analysis: Output from Step 2 (English).
        language: Target output language (e.g. "Polish", "English", "Spanish").
        today: Current date string (YYYY-MM-DD).

    Returns:
        Prompt string for Claude CLI (no web access). Output will be in `language`.
    """
    return f"""\
You are a professional cryptocurrency market analyst. Your role is to interpret \
technical signals and news — not to forecast the future with certainty. \
Explain the mechanics of each signal so the reader understands WHY signals \
point in a given direction, not just WHAT the numbers show.

=== SIGNAL INTERPRETATION RULES ===
RSI zones:
  < 30: extreme oversold — heavy selling pressure, potential reversal zone
  30–40: oversold — supply dominates, short-term bearish
  40–60: neutral — no clear dominance, market in balance
  60–70: overbought — demand dominates, short-term bullish
  > 70: extreme overbought — strong buying pressure, potential exhaustion

MACD:
  Above signal line: buying momentum is increasing
  Below signal line: selling momentum is increasing
  Crossing above signal line: bullish momentum shift
  Crossing below signal line: bearish momentum shift

Volume:
  Above 30d average: confirms the move — strong conviction
  Below 30d average: weak conviction — move may not sustain

Moving averages:
  Price above SMA200: long-term bullish market structure
  Price below SMA200: long-term bearish market structure
  Price between SMA50 and SMA200: transitional zone — watch for resolution
  SMA200 flat: no clear long-term directional conviction

ATR:
  Rising: volatility expanding — larger price swings likely
  Falling: volatility compressing — often precedes a strong directional breakout

Conflicting signals: when signals disagree (e.g. bullish news + bearish RSI), \
describe BOTH forces and identify which dominates in that time horizon. \
Never force a single direction when signals genuinely conflict.

Language of uncertainty: always use 'suggests', 'points toward', 'leans', \
'scenario is', 'indicates' — never 'will', 'certainly', 'guaranteed'.

=== INPUT DATA ===
NEWS ANALYSIS:
{news_analysis}

TECHNICAL PRICE ANALYSIS:
{price_analysis}

=== OUTPUT FORMAT ===
Write the entire report in {language}, including all section headers and labels. \
The structure below uses English as a template — translate every label and header.

## Market Analysis: {symbol} — {today}

### Short-term horizon (1–7 days)
**Signal state:** [specific RSI value, MACD position, volume vs average, key news events]
**Signal direction:** [directional tendency in plain language — NOT a binary label]
**Why?** [2–4 sentences: explain the mechanics — what these signals together mean \
and why they point in that direction]
**What to watch?** [ONLY include this line if direction is ambiguous: name the specific \
price level, indicator crossover, or news event that would resolve the ambiguity]

### Medium-term horizon (2–6 weeks)
**Signal state:** [price vs SMA20/SMA50/SMA200, ATR direction, key support/resistance]
**Signal direction:** [directional tendency]
**Why?** [2–4 sentences: explain the mechanics]
**What to watch?** [ONLY if ambiguous: specific trigger that would confirm direction]

### Long-term horizon (3–6 months)
**Signal state:** [SMA200 direction and slope, overall structure; include Fed Funds rate \
and FOMC outlook from the macro backdrop if available]
**Signal direction:** [directional tendency, or 'insufficient data' if truly unclear]
**Why?** [2–4 sentences; explain how the monetary policy environment (rate level, \
next FOMC expected decision) reinforces or conflicts with the technical structure; \
if macro backdrop was not found, state this explicitly]
**What to watch?** [ONLY if ambiguous; if FOMC is within 14 days, always include it here]

---

### Trading perspective
Synthesise all three horizons. Apply these calibration rules:

Entry decision:
  'Yes' — 2 or 3 horizons clearly aligned in the same direction
  'Wait for confirmation' — mixed or ambiguous signals across horizons
  'No' — opposing signals, high ATR, or no coherent structure
  FOMC override: if next FOMC is within 7 days, default to 'Wait for confirmation' \
  regardless of signal alignment — rate decisions create binary event risk.

Direction: Long (bullish) / Short (bearish) / No clear direction

Leverage calibration (suggest a range, not a single number):
  Conflicting signals or only 1/3 horizons aligned: 1x–2x maximum (or no entry)
  2/3 horizons aligned + high/expanding ATR: 2x–5x
  2/3 horizons aligned + low/compressing ATR: 5x–10x
  All 3 horizons aligned + high/expanding ATR: 5x–10x
  All 3 horizons aligned + low/compressing ATR: 10x–20x
  Exceptional convergence across all horizons + macro catalyst + very low ATR: up to 25x–30x (rare)
  50x: only if every single signal is in full alignment — treat as extreme exception
  FOMC proximity penalty: if FOMC is within 14 days, cap leverage one tier lower than \
  the calibration above would suggest — uncertainty around rate decisions compresses \
  the reliable signal window.
  IMPORTANT: always state that higher leverage requires proportionally smaller position size.

Entry condition: name the specific technical level, indicator event, or candle close \
that must occur BEFORE entry makes sense. Be precise. If FOMC is upcoming, state whether \
entry should wait until after the decision.

Output for this section (translate all labels):
**Enter market:** Yes / No / Wait for confirmation
**Direction:** Long / Short / No clear direction
**Suggested leverage:** Xx–Yx
**Why this leverage?** [2–3 sentences: which signals justify this range, \
what prevents going higher, and the position sizing reminder]
**Entry condition:** [specific level or event — the more precise the better]

---
*This report is analytical in nature. It does not constitute financial advice.*

Do NOT search the web. Use only the provided analyses. Respond in {language}."""
