import re
from urllib.parse import urlparse
from crewai.tools import tool

STOP_PHRASES = [
    "what is", "explained", "definition", "beginners", "guide",
    "how to", "tutorial", "history of", "basics", "introduction",
]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _looks_evergreen(title: str, summary: str) -> bool:
    txt = f"{title} {summary}".lower()
    return any(p in txt for p in STOP_PHRASES)


def _normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return t


def _extract_topic_fingerprint(title: str, summary: str) -> str:
    """
    Extract a 'topic fingerprint' to identify articles about the same event.
    Combines key numbers, entities, and action words.
    """
    text = f"{title} {summary}".lower()
    
    # Extract monetary amounts (normalize billions/millions)
    # Round to 1 decimal to catch $1.7B and $1.72B as same
    amounts = re.findall(r'\$?(\d+(?:\.\d+)?)\s*(billion|million|b|m|bn|mn)', text)
    normalized_amounts = []
    for amt, unit in amounts:
        val = round(float(amt), 1)  # Round to catch $1.7B == $1.72B
        if unit in ('billion', 'b', 'bn'):
            normalized_amounts.append(f"${val}B")
        elif unit in ('million', 'm', 'mn'):
            # Convert large millions to billions for consistency
            if val >= 1000:
                normalized_amounts.append(f"${round(val/1000, 1)}B")
            else:
                normalized_amounts.append(f"${val}M")
    
    # Extract key event words
    event_keywords = []
    event_patterns = [
        (r'outflow|withdraw|redeem|bleed|losing|loss|lost', 'outflow'),
        (r'inflow|deposit|buying', 'inflow'),
        (r'etf', 'etf'),
        (r'hack|exploit|breach|attack', 'hack'),
        (r'sec|regulation|lawsuit|legal|enforcement', 'regulation'),
        (r'blackrock|ibit', 'blackrock'),
        (r'grayscale|gbtc', 'grayscale'),
        (r'fidelity', 'fidelity'),
        (r'approval|approved|reject|denied', 'approval'),
        (r'surge|rally|jump|soar|pump|gain', 'price_up'),
        (r'crash|dump|plunge|drop|fall|tank|slide', 'price_down'),
        (r'halving', 'halving'),
        (r'fed|fomc|rate|powell', 'fed'),
        (r'trump|biden|election|president', 'politics'),
    ]
    
    for pattern, keyword in event_patterns:
        if re.search(pattern, text):
            event_keywords.append(keyword)
    
    # Combine into fingerprint
    fingerprint_parts = sorted(set(normalized_amounts + event_keywords))
    return "|".join(fingerprint_parts) if fingerprint_parts else ""


def _dedupe_items(items: list, max_per_domain: int = 2, max_per_topic: int = 1) -> list:
    """
    Dedupe by:
    1. Exact normalized title
    2. Topic fingerprint (articles about same event)
    3. Limit per domain to reduce spam/aggregators
    """
    seen_titles = set()
    seen_topics = {}  # topic -> count
    domain_count = {}
    out = []

    for it in items:
        title = getattr(it, "title", "") or ""
        summary = getattr(it, "summary", "") or ""
        url = getattr(it, "url", "") or ""
        dom = _domain(url)

        # 1) Skip exact duplicate titles
        nt = _normalize_title(title)
        if not nt or nt in seen_titles:
            continue

        # 2) Skip if we've seen too many articles on same topic
        topic_fp = _extract_topic_fingerprint(title, summary)
        if topic_fp:
            seen_topics.setdefault(topic_fp, 0)
            if seen_topics[topic_fp] >= max_per_topic:
                continue
            seen_topics[topic_fp] += 1

        # 3) Limit per domain
        domain_count.setdefault(dom, 0)
        if dom and domain_count[dom] >= max_per_domain:
            continue

        seen_titles.add(nt)
        domain_count[dom] += 1
        out.append(it)

    return out


def build_news_tool(
    exa_client,
    *,
    bad_domains,
    good_domains,
    days_back,
    limit,
    max_summary_chars,
    use_include_domains: bool,
):
    @tool("news_tool")
    def news_tool(ticker_symbol: str) -> str:
        """
        Fetch recent, non-definitional cryptocurrency news for the given ticker symbol.
        Applies domain filtering, recency window, deduplication, and returns a compact feed
        to support event-driven market analysis.
        
        Args:
            ticker_symbol: The cryptocurrency ticker symbol (e.g., "BTC", "ETH", "SOL")
        
        Example call: news_tool(ticker_symbol="BTC")
        """
        include = good_domains if use_include_domains else None

        # 1) Pull more than needed, then filter down
        raw_limit = max(limit * 4, 12)

        res = exa_client.search_recent_news_strict(
            ticker_symbol=ticker_symbol,
            days_back=days_back,
            limit=raw_limit,
            exclude_domains=bad_domains,
            include_domains=include,
        )

        if not res.results:
            return "No recent news results found."

        # 2) Prefer items with published_date
        items = [x for x in res.results if getattr(x, "published_date", None)]
        if not items:
            items = res.results

        # 3) Remove evergreen/definitional articles by content heuristics
        filtered = []
        for it in items:
            title = getattr(it, "title", "") or ""
            summary = getattr(it, "summary", "") or ""
            url = getattr(it, "url", "") or ""
            dom = _domain(url)

            if dom in bad_domains:
                continue
            if _looks_evergreen(title, summary):
                continue
            filtered.append(it)

        # 4) Dedupe + domain cap
        filtered = _dedupe_items(filtered, max_per_domain=2)

        # 5) Take final N
        final_items = filtered[:limit] if filtered else items[:limit]

        # 6) Format compact feed
        out_lines = []
        for it in final_items:
            title = getattr(it, "title", "No Title")
            url = getattr(it, "url", "#")
            published = getattr(it, "published_date", "Unknown Date")
            summary = (getattr(it, "summary", "") or "").replace("\n", " ").strip()

            if len(summary) > max_summary_chars:
                summary = summary[: max_summary_chars - 3] + "..."

            out_lines.append(
                f"- {title}\n"
                f"  Date: {published}\n"
                f"  Source: {_domain(url)}\n"
                f"  URL: {url}\n"
                f"  Summary: {summary}"
            )

        # 7) Add an "instruction header" to make LLM extract events (reduces generic output)
        header = (
            "TASK FOR ANALYST:\n"
            "From the articles below, extract 3-5 MARKET-MOVING EVENTS (facts), each with:\n"
            "• Event (one sentence)\n"
            "• Why it matters for price (one sentence)\n"
            "• Link (URL)\n"
            "Ignore definitional content.\n"
            "----\n"
        )
        return header + "\n\n".join(out_lines)

    return news_tool
