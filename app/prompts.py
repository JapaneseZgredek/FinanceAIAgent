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

    return f"""\
Today is {today}. Search the web for recent news about the {symbol} cryptocurrency \
from the last {news_days_back} days.

=== SEARCH STRATEGY ===
Execute searches in this order:
1. Primary search (Tier 1 sources only):
   Query: "{symbol} cryptocurrency news" ({tier1_site_query})
2. Supplementary search (Tier 2 sources) ONLY if Tier 1 yields fewer than 3 relevant events:
   Query: "{symbol} crypto news" ({tier2_site_query})

=== SOURCE RELIABILITY RULES ===
TIER 1 — HIGH TRUST: {tier1_list}
  These sites provide analyst-attributed content with verifiable data. Prefer these.

TIER 2 — MODERATE TRUST: {tier2_list}
  Use only as supplementary. MANDATORY: cross-check any Tier 2 claim against a Tier 1 source.
  If a Tier 2 article cannot be corroborated, do NOT include the claim.

BLOCKED — NEVER USE: {blocked_list}
  These domains publish AI-generated price-prediction content with zero analytical value.
  Discard any result from these domains immediately, regardless of headline.

=== CRITICAL VERIFICATION REQUIREMENTS ===
Before including any piece of information you MUST verify:
  1. FRESHNESS: Check the article publication date. Only include events from the last \
{news_days_back} days (after {today} minus {news_days_back} days).
     Reject any article without a visible publication date.
  2. SOURCE CREDIBILITY: Confirm the domain matches a Tier 1 or Tier 2 entry above.
     Do not trust a site just because it appears in search results.
  3. SPECIFICITY: The event must name a concrete catalyst (a regulator, institution,
     fund, or protocol). Vague headlines like 'Bitcoin may rise' are not market-moving events.
  4. CORROBORATION: If only one source reports an event, mark it as
     '(unconfirmed — single source)' in your output.

=== FOCUS ===
Include ONLY market-moving events: regulatory actions, major partnerships, exchange listings,
ETF inflows/outflows, protocol upgrades, exchange hacks, macro events (Fed, CPI, tariffs).
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

Respond in English."""


def build_price_analysis_prompt(symbol: str, price_data: str) -> str:
    """
    Build the Step 2 prompt: technical analysis of pre-computed indicator data.

    Args:
        symbol: Cryptocurrency ticker.
        price_data: Formatted string from get_formatted_price_data().

    Returns:
        Prompt string for Claude CLI (no web access).
    """
    return f"""\
You are a quantitative cryptocurrency analyst. \
Analyze the following technical indicator data for {symbol}.

=== PRICE DATA AND INDICATORS ===
{price_data}

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
**Signal state:** [SMA200 direction and slope, overall structure; \
if macro data is unavailable, state this explicitly]
**Signal direction:** [directional tendency, or 'insufficient data' if truly unclear]
**Why?** [2–4 sentences; if data is incomplete, name what is missing and why it matters]
**What to watch?** [ONLY if ambiguous]

---

### Trading perspective
Synthesise all three horizons. Apply these calibration rules:

Entry decision:
  'Yes' — 2 or 3 horizons clearly aligned in the same direction
  'Wait for confirmation' — mixed or ambiguous signals across horizons
  'No' — opposing signals, high ATR, or no coherent structure

Direction: Long (bullish) / Short (bearish) / No clear direction

Leverage calibration (suggest a range, not a single number):
  Conflicting signals or only 1/3 horizons aligned: 1x–2x maximum (or no entry)
  2/3 horizons aligned + high/expanding ATR: 2x–5x
  2/3 horizons aligned + low/compressing ATR: 5x–10x
  All 3 horizons aligned + high/expanding ATR: 5x–10x
  All 3 horizons aligned + low/compressing ATR: 10x–20x
  Exceptional convergence across all horizons + macro catalyst + very low ATR: up to 25x–30x (rare)
  50x: only if every single signal is in full alignment — treat as extreme exception
  IMPORTANT: always state that higher leverage requires proportionally smaller position size.

Entry condition: name the specific technical level, indicator event, or candle close \
that must occur BEFORE entry makes sense. Be precise.

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
