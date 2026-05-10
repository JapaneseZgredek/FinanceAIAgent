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
    pre_decision: str = "",
) -> str:
    """
    Build the Step 3 prompt: synthesise news + price analysis into the final report.

    Args:
        symbol: Cryptocurrency ticker.
        news_analysis: Output from Step 1 (English).
        price_analysis: Output from Step 2 (English).
        language: Target output language (e.g. "Polish", "English", "Spanish").
        today: Current date string (YYYY-MM-DD).
        pre_decision: Deterministic entry decision from compute_pre_decision().
                      Injected as a hard constraint to prevent non-deterministic
                      LLM decision-making across runs on the same data.

    Returns:
        Prompt string for Claude CLI (no web access). Output will be in `language`.
    """
    pre_decision_block = ""
    if pre_decision:
        pre_decision_block = f"""
=== PRE-COMPUTED ENTRY SIGNAL (PYTHON — DETERMINISTIC) ===
The trading entry decision below was computed in Python from the raw technical
indicators BEFORE this prompt was generated. It uses objective, threshold-based
rules with no subjective interpretation. Treat it as the baseline decision for
the Trading perspective section — you MUST use it unless a specific override
rule applies (listed in the Trading perspective section below).

{pre_decision}

Do NOT override this baseline because of "waning momentum" or "ambiguous short-term
signals". If 2+ horizons are structurally aligned, the baseline stands. The MACD
histogram narrowing while still negative is EXPECTED bearish behavior — it does NOT
make the signal ambiguous. Only FOMC proximity or HIGH risk factors may trigger an override.

"""

    return f"""\
You are a professional cryptocurrency market analyst. Your role is to interpret \
technical signals and news — not to forecast the future with certainty. \
Explain the mechanics of each signal so the reader understands WHY signals \
point in a given direction, not just WHAT the numbers show.
{pre_decision_block}

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

### Risk Factors
For each category below, derive severity from the input data only.
Omit any category where evidence supports only low severity — do NOT write low-severity rows.
If all four categories would be omitted, write one line instead of the table:
"No significant risk factors identified in current data."
Translate all headers, labels, and behavior descriptions into {language}.

Severity rules per category:
  Regulation:
    medium — regulatory scrutiny or investigation mentioned, no active enforcement yet
    high   — active enforcement action, ban, forced exchange delisting by a regulator
  Exchange incidents:
    medium — unconfirmed rumors or single-source reports of exchange problems
    high   — confirmed hack, insolvency, withdrawal halt, or forced delisting
  Liquidity:
    medium — volatility regime HIGH; or ATR rising with volume below 30d average
    high   — volatility regime EXTREME; or explicit critically low volume in price analysis
  Volatility spikes:
    medium — volatility regime HIGH; or ATR rising with NORMAL regime
    high   — volatility regime EXTREME; or ATR rising with HIGH or EXTREME regime

Expected behavior descriptions per severity:
  Regulation medium  → Regulatory pressure may cause elevated selling; watch for
                       sudden sharp moves on new enforcement headlines.
  Regulation high    → Binary event risk: gap moves likely on news — stops may not
                       fill at intended price; exchange outflows possible.
  Exchange medium    → Unconfirmed risk; monitor for withdrawal halt announcement
                       which would trigger panic selling and contagion.
  Exchange high      → Counterparty risk active: correct directional call does not
                       guarantee profit if exchange freezes withdrawals.
  Liquidity medium   → Wider spreads and moderate slippage expected; use limit orders,
                       avoid oversized positions.
  Liquidity high     → High slippage on entry and exit; stop-loss orders may miss
                       target price — reduce position size by 30–50%, limit orders only.
  Volatility medium  → Larger price swings likely; stops may be triggered by noise
                       before real direction emerges — widen stops proportionally.
  Volatility high    → Rapid moves in either direction, cascading liquidations possible;
                       gap risk on stops — smaller position mandatory.

Write one block per qualifying category. Omit categories with low severity entirely.
If no category qualifies, write: "No significant risk factors identified in current data."

**[Risk category name]** — [medium / high]
[One sentence: cite the specific signal — news event with source and date, or regime/ATR values]
[Expected behavior from the rules above — one sentence, plain language]

---

### Trading perspective
Use the PRE-COMPUTED ENTRY SIGNAL (injected above) as the baseline decision.
Apply the override rules below in strict order — stop at the first rule that fires.
If no override fires, the baseline decision stands unchanged.

Override rules (apply in order, stop at first match):
  Override 1 — FOMC event:
      If news analysis shows next FOMC is within 7 days →
      downgrade one level: ENTER → 'Wait for confirmation'; WAIT → 'No'.
      Reason: rate decisions create binary event risk that cannot be hedged technically.

  Override 2 — Two or more HIGH risk factors simultaneously:
      Default to 'No' regardless of horizon alignment.

  Override 3 — Single HIGH risk factor:
      Downgrade one level: ENTER → 'Wait for confirmation'; WAIT → 'No'.
      Exception: 3/3 horizons aligned AND only Liquidity is HIGH (not Regulation or
      Exchange) → baseline stands, but position size must be reduced by 50%.
      - Regulation HIGH → also treat as binary event risk (same as FOMC within 7 days):
        cap leverage one tier below calibration.
      - Exchange incident HIGH → add to output:
        "Counterparty risk active — reduce position size by 50% regardless of leverage tier."
      - Liquidity HIGH → add to output:
        "Use limit orders only; widen stop-loss for spread and slippage."
      - Volatility spike HIGH → add to output:
        "Gap risk on stops — set stop-loss wider than ATR suggests, size down accordingly."

CRITICAL — MEDIUM risk factors: MEDIUM severity does NOT change the entry decision.
Include MEDIUM factors in the Risk Factors section with position-sizing guidance only.
Do NOT use MEDIUM factors as justification for overriding the baseline or for adding
extra conservatism to the trading decision.

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

Output for this section — choose EXACTLY ONE path. Translate all labels.

PATH A — use when entry decision is 'Yes' (conditions met, entering now):
**Decision:** Enter now
**Direction:** Long / Short
**Suggested leverage:** Xx–Yx
**Why this leverage?** [2–3 sentences: which signals justify this range, \
what prevents going higher, and the position sizing reminder]
**How to enter:** [order type (limit or market), specific price level or candle close \
that confirms entry, stop-loss placement]

PATH B — use when entry decision is 'Wait for confirmation' or 'No' (not entering now):
**Decision:** Wait for confirmation / Do not enter
**Direction (anticipated):** Long / Short / Unclear
**Why not now:** [1–2 sentences: what is conflicting, missing, or too risky — \
reference active risk factors if they forced this decision]
**What to watch:** [the exact price level, indicator crossover, candle close, or news event \
that must occur before entry makes sense; if FOMC is upcoming, state whether entry \
should wait until after the decision]
**If triggered — leverage:** [leverage range to apply once the condition is met]
**If triggered — how to enter:** [execution approach once the trigger fires]

---

### What to watch next
Synthesise forward-looking signals from the two input analyses. \
Write 3–6 bullets total, grouped under the subcategories below. \
Omit any subcategory block entirely if the input data contains no relevant signal for it. \
Each bullet must be actionable and forward-looking — use phrasing like \
"watch for", "monitor", "if X then Y". \
Do NOT repeat conclusions already stated in the horizons or Trading perspective. \
Translate all headers and labels into {language}.

**Macro calendar:**
- [Next FOMC meeting date and expected rate action, from the Fed/Macro Backdrop in Step 1 \
news analysis; if within 14 days, flag urgency explicitly]
- [Any forward-looking catalysts implicit in the News Tendency section of Step 1 — \
e.g. "market in wait-and-see mode ahead of halving", "institutional interest building"; \
omit if News Tendency contains no implicit upcoming events]

**Macro environment triggers:**
- [From Step 2 macro backdrop: one actionable VIX or DXY threshold whose breach would \
materially change the risk environment — e.g. "if VIX drops below 20, risk-on conditions \
could accelerate the move"; omit this block entirely if macro backdrop was not available \
or contains no directional VIX/DXY signal]

**ETF & institutional flows:**
- [ETF inflow/outflow signals, new ETF filings, or approval decisions from Step 1 Market Events; \
omit this block entirely if no ETF signals are present in the input]

**On-chain & narrative catalysts:**
- [Protocol upgrades, on-chain metric inflections, or regulatory developments that could \
escalate — sourced from Step 1 Market Events; omit if no relevant signals]

**Technical triggers:**
- [One key price level from Step 2 — SMA cross, resistance, or support — whose breach \
would materially change the signal direction]
- [ATR/volatility regime direction: whether expanding or compressing, and what it implies \
for the next 1–2 weeks]
- [MA cross or RSI divergence from Step 2 if present and unresolved; omit if absent]

---
*This report is analytical in nature. It does not constitute financial advice.*

Do NOT search the web. Use only the provided analyses. Respond in {language}."""


def build_json_report_prompt(
    symbol: str,
    news_analysis: str,
    price_analysis: str,
    today: str,
    pre_decision: str = "",
) -> str:
    """
    Build the Step 3 prompt: synthesise news + price analysis into a structured JSON report.

    Variant of build_final_report_prompt() for machine consumption — always English,
    no markdown, strict JSON schema. Used when output_format="json" is requested.

    Args:
        symbol: Cryptocurrency ticker.
        news_analysis: Output from Step 1 (English).
        price_analysis: Output from Step 2 (English).
        today: Current date string (YYYY-MM-DD).
        pre_decision: Deterministic entry decision from compute_pre_decision().
                      Injected as a hard constraint (same rules as markdown variant).

    Returns:
        Prompt string for Claude CLI (no web access). Output is a single JSON object.
    """
    pre_decision_block = ""
    if pre_decision:
        pre_decision_block = f"""
=== PRE-COMPUTED ENTRY SIGNAL (PYTHON — DETERMINISTIC) ===
The trading entry decision below was computed in Python from the raw technical
indicators BEFORE this prompt was generated. It uses objective, threshold-based
rules with no subjective interpretation. Treat it as the baseline decision for
the "prediction" and "trading" fields — you MUST use it unless a specific override
rule applies (listed below).

{pre_decision}

Do NOT override this baseline because of "waning momentum" or "ambiguous short-term
signals". If 2+ horizons are structurally aligned, the baseline stands. The MACD
histogram narrowing while still negative is EXPECTED bearish behavior — it does NOT
make the signal ambiguous. Only FOMC proximity or HIGH risk factors may trigger an override.

"""

    return f"""\
You are a professional cryptocurrency market analyst. Synthesise the two analyses
below into a single structured JSON object. Output ONLY valid JSON — no markdown,
no code fences, no explanation text before or after.
{pre_decision_block}
=== SIGNAL INTERPRETATION RULES ===
RSI zones:
  < 30: extreme oversold | 30–40: oversold | 40–60: neutral | 60–70: overbought | > 70: extreme overbought

MACD:
  Above signal line: buying momentum increasing ("above_signal")
  Below signal line: selling momentum increasing ("below_signal")

Volume:
  Above 30d average: confirms the move — strong conviction ("above")
  Below 30d average: weak conviction ("below")

Moving averages:
  Price above SMA200: long-term bullish structure ("above")
  Price below SMA200: long-term bearish structure ("below")

ATR:
  Rising: volatility expanding ("expanding")
  Falling: volatility compressing ("contracting")

=== INPUT DATA ===
NEWS ANALYSIS:
{news_analysis}

TECHNICAL PRICE ANALYSIS:
{price_analysis}

=== OVERRIDE RULES FOR prediction.final_decision ===
Apply in order, stop at first match. If none fires, final_decision == pre_decision.

Override 1 — FOMC event:
    If next FOMC is within 7 days → downgrade one level:
    ENTER → WAIT, WAIT → NO.
    Set override_applied=true, override_reason="FOMC within 7 days".

Override 2 — Two or more HIGH risk factors simultaneously:
    final_decision = "NO", override_applied=true,
    override_reason="2+ HIGH risk factors: <categories>".

Override 3 — Single HIGH risk factor:
    Downgrade one level: ENTER → WAIT, WAIT → NO.
    Exception: 3/3 horizons aligned AND only Liquidity is HIGH →
    final_decision unchanged, but note it in override_reason.

MEDIUM risk factors: do NOT change the decision. Do NOT set override_applied=true for MEDIUM.

=== RISK FACTOR SEVERITY RULES ===
Regulation:  medium=scrutiny/investigation, high=active enforcement/ban/delisting
Exchange:    medium=unconfirmed rumors, high=confirmed hack/insolvency/withdrawal halt
Liquidity:   medium=HIGH volatility regime OR ATR rising + volume below avg,
             high=EXTREME volatility regime OR critically low volume
Volatility:  medium=HIGH regime OR ATR rising with NORMAL regime,
             high=EXTREME regime OR ATR rising with HIGH/EXTREME regime

=== OUTPUT JSON SCHEMA ===
Return exactly this structure. Use null for any field where data is unavailable.
All string enum values must match exactly (case-sensitive).

{{
  "symbol": "{symbol}",
  "date": "{today}",

  "sentiment": {{
    "label": "Positive" | "Negative" | "Mixed",
    "summary": "<one sentence>"
  }},

  "events": [
    {{
      "description": "<event description>",
      "source": "<domain.com>",
      "date": "<YYYY-MM-DD or null>",
      "tier": <1 | 2>,
      "corroborated": <true | false>
    }}
  ],

  "metrics": {{
    "rsi": <number | null>,
    "macd_position": "above_signal" | "below_signal" | null,
    "price_vs_sma20": "above" | "below" | null,
    "price_vs_sma50": "above" | "below" | null,
    "price_vs_sma200": "above" | "below" | null,
    "atr_direction": "expanding" | "contracting" | null,
    "volatility_regime": "LOW" | "NORMAL" | "HIGH" | "EXTREME" | null,
    "volume_vs_30d_avg": "above" | "below" | null
  }},

  "horizons": {{
    "short_term": {{
      "signal_state": "<specific indicator values>",
      "direction": "<directional tendency in plain language>",
      "reasoning": "<2-4 sentences explaining the mechanics>"
    }},
    "medium_term": {{
      "signal_state": "<specific indicator values>",
      "direction": "<directional tendency>",
      "reasoning": "<2-4 sentences>"
    }},
    "long_term": {{
      "signal_state": "<specific indicator values>",
      "direction": "<directional tendency>",
      "reasoning": "<2-4 sentences>"
    }}
  }},

  "macro": {{
    "fed_funds_rate": "<X.XX% | null>",
    "next_fomc_date": "<YYYY-MM-DD | null>",
    "fomc_days_away": <integer | null>,
    "expected_action": "hold" | "cut" | "hike" | null,
    "backdrop_summary": "<2-3 sentences | null>"
  }},

  "risk_factors": [
    {{
      "category": "regulation" | "exchange" | "liquidity" | "volatility",
      "severity": "medium" | "high",
      "signal_basis": "<one sentence citing the specific signal>",
      "expected_behavior": "<one sentence in plain language>"
    }}
  ],

  "prediction": {{
    "pre_decision": "ENTER" | "WAIT" | "NO",
    "final_decision": "ENTER" | "WAIT" | "NO",
    "override_applied": <true | false>,
    "override_reason": "<string | null>"
  }},

  "trading": {{
    "direction": "long" | "short" | "unclear",
    "leverage_min": <integer | null>,
    "leverage_max": <integer | null>,
    "entry_notes": "<order type, price level, stop-loss placement | null>",
    "wait_conditions": "<exact trigger required before entry | null>"
  }},

  "watch_next": {{
    "macro_calendar": ["<bullet>"],
    "macro_triggers": ["<bullet>"],
    "etf_flows": ["<bullet>"],
    "on_chain": ["<bullet>"],
    "technical_triggers": ["<bullet>"]
  }},

  "sources": [
    {{ "domain": "<domain.com>", "tier": <1 | 2> }}
  ]
}}

Rules:
- risk_factors: include ONLY medium or high severity. Empty array [] if none qualify.
- watch_next subcategory arrays: empty array [] if no relevant signal in input data.
- sources: deduplicated list of all domains cited in events.
- trading.entry_notes: fill when final_decision is ENTER, null otherwise.
- trading.wait_conditions: fill when final_decision is WAIT or NO, null otherwise.
- trading.leverage_min / leverage_max: fill for ENTER or WAIT, null for NO.

Do NOT search the web. Use only the provided analyses. Output ONLY the JSON object."""


def build_comparison_narrative_prompt(
    symbol: str,
    base_date,
    compare_date,
    structural_summary: str,
    language: str,
    *,
    base_excerpt: str = "",
    compare_excerpt: str = "",
    diff_text: str = "",
) -> str:
    """Build a prompt for the narrative drift LLM step (Step 4 of the comparison pipeline).

    Two mutually exclusive call patterns:
      - Mode A (both JSON): pass ``base_excerpt`` + ``compare_excerpt`` — compact structured summaries.
      - Mode B (markdown fallback): pass ``diff_text`` — the unified section diff output.

    Args:
        symbol: Cryptocurrency ticker, e.g. ``"BTC"``.
        base_date: Date of the older report.
        compare_date: Date of the newer report.
        structural_summary: Deterministic summary of changed fields (built by ``_build_structural_summary``).
        language: Output language for the narrative (e.g. "Polish", "English").
        base_excerpt: Compact text from the base JSON report (events, risks, watch_next).
        compare_excerpt: Compact text from the compare JSON report.
        diff_text: Unified section diff (``-``/``+`` lines). Used when at least one report is markdown.

    Returns:
        Prompt string ready to pass to ``ClaudeClient.run()``.
    """
    if diff_text:
        intro = (
            f"You are a senior crypto analyst. Below is a unified section diff for {symbol} "
            f"({base_date} → {compare_date}). Lines starting with '-' come from the older report "
            f"({base_date}); lines starting with '+' come from the newer report ({compare_date})."
        )
        context_block = f"=== SECTION DIFF ===\n{diff_text}"
    else:
        intro = (
            f"You are a senior crypto analyst. Two structured report excerpts for {symbol} are "
            f"provided below — base from {base_date}, compare from {compare_date}."
        )
        context_block = (
            f"=== BASE REPORT EXCERPT ({base_date}) ===\n{base_excerpt}\n\n"
            f"=== COMPARE REPORT EXCERPT ({compare_date}) ===\n{compare_excerpt}"
        )

    return f"""\
{intro}

=== STRUCTURAL CHANGES (deterministic field diff) ===
{structural_summary}

{context_block}

=== YOUR TASK ===
Write a narrative drift summary of 4–7 sentences explaining WHY the key metrics and sentiment \
shifted between the two dates. Focus on causality — which news events, macro developments, or \
technical breakouts drove the change. Do NOT repeat the numbers from the structural changes above. \
Bullet lists are allowed for distinct drivers; a short paragraph is preferred if the story is coherent.

Output language: {language}.
Do NOT search the web. Use only the information provided above."""
