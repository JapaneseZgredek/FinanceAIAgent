"""
Utilities for managing prompt size and preventing oversized LLM inputs.

This module provides functions to:
- Estimate token count (rough approximation)
- Truncate long strings while preserving structure
- Apply hard caps on tool outputs
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Hard caps to prevent excessive prompt sizes
# These are absolute maximums regardless of config
ABSOLUTE_MAX_NEWS_ARTICLES = 10
ABSOLUTE_MAX_SUMMARY_CHARS = 500
ABSOLUTE_MAX_PRICE_HISTORY_LINES = 30
ABSOLUTE_MAX_TOOL_OUTPUT_CHARS = 8000  # ~2000 tokens


def estimate_token_count(text: str) -> int:
    """
    Rough estimate of token count for English text.
    
    Rule of thumb: ~4 characters per token on average.
    This is approximate but good enough for safety checks.
    
    Args:
        text: Input text string
    
    Returns:
        Estimated number of tokens
    """
    return len(text) // 4


def truncate_with_ellipsis(text: str, max_chars: int, preserve_lines: int = 3) -> str:
    """
    Truncate text to max_chars while preserving structure.
    
    Strategy:
    - Keep first few lines intact (for context)
    - Truncate middle content
    - Add "... (truncated)" marker
    
    Args:
        text: Text to truncate
        max_chars: Maximum character count
        preserve_lines: Number of initial lines to preserve
    
    Returns:
        Truncated text if needed, original if under limit
    """
    if len(text) <= max_chars:
        return text
    
    lines = text.split('\n')
    
    # Try to preserve structure
    if len(lines) > preserve_lines:
        header = '\n'.join(lines[:preserve_lines])
        truncation_msg = f"\n... (truncated {len(text) - max_chars} chars, output too large)"
        
        # Calculate how much space we have
        available = max_chars - len(header) - len(truncation_msg)
        
        if available > 0:
            return header + truncation_msg
    
    # Fallback: simple truncation
    return text[:max_chars - 50] + "\n... (truncated, output too large)"


def enforce_tool_output_limits(output: str, tool_name: str, max_chars: int | None = None) -> str:
    """
    Enforce hard limits on tool output size.
    
    This is a safety mechanism to prevent tools from returning
    extremely large outputs that would exceed LLM context limits.
    
    Args:
        output: Tool output string
        tool_name: Name of the tool (for logging)
        max_chars: Maximum characters (default: ABSOLUTE_MAX_TOOL_OUTPUT_CHARS)
    
    Returns:
        Original output if within limits, truncated version if too large
    """
    max_chars = max_chars or ABSOLUTE_MAX_TOOL_OUTPUT_CHARS
    original_size = len(output)
    
    if original_size <= max_chars:
        return output
    
    # Output is too large - truncate it
    logger.warning(
        f"{tool_name} output too large ({original_size} chars, ~{estimate_token_count(output)} tokens). "
        f"Truncating to {max_chars} chars."
    )
    
    truncated = truncate_with_ellipsis(output, max_chars)
    logger.debug(f"Truncated {tool_name} output from {original_size} to {len(truncated)} chars")
    
    return truncated


def validate_config_limits() -> dict[str, Any]:
    """
    Validate that configuration values don't exceed absolute maximums.
    
    Returns:
        Dictionary of {setting: (configured_value, capped_value, was_capped)}
    """
    from app.config import NEWS_LIMIT, NEWS_MAX_SUMMARY_CHARS, PRICE_LAST_N
    
    results = {}
    
    # Check NEWS_LIMIT
    if NEWS_LIMIT > ABSOLUTE_MAX_NEWS_ARTICLES:
        logger.warning(
            f"NEWS_LIMIT={NEWS_LIMIT} exceeds absolute maximum {ABSOLUTE_MAX_NEWS_ARTICLES}. "
            f"Capping to {ABSOLUTE_MAX_NEWS_ARTICLES}."
        )
        results["NEWS_LIMIT"] = (NEWS_LIMIT, ABSOLUTE_MAX_NEWS_ARTICLES, True)
    else:
        results["NEWS_LIMIT"] = (NEWS_LIMIT, NEWS_LIMIT, False)
    
    # Check NEWS_MAX_SUMMARY_CHARS
    if NEWS_MAX_SUMMARY_CHARS > ABSOLUTE_MAX_SUMMARY_CHARS:
        logger.warning(
            f"NEWS_MAX_SUMMARY_CHARS={NEWS_MAX_SUMMARY_CHARS} exceeds absolute maximum {ABSOLUTE_MAX_SUMMARY_CHARS}. "
            f"Capping to {ABSOLUTE_MAX_SUMMARY_CHARS}."
        )
        results["NEWS_MAX_SUMMARY_CHARS"] = (NEWS_MAX_SUMMARY_CHARS, ABSOLUTE_MAX_SUMMARY_CHARS, True)
    else:
        results["NEWS_MAX_SUMMARY_CHARS"] = (NEWS_MAX_SUMMARY_CHARS, NEWS_MAX_SUMMARY_CHARS, False)
    
    # Check PRICE_LAST_N
    if PRICE_LAST_N > ABSOLUTE_MAX_PRICE_HISTORY_LINES:
        logger.warning(
            f"PRICE_LAST_N={PRICE_LAST_N} exceeds absolute maximum {ABSOLUTE_MAX_PRICE_HISTORY_LINES}. "
            f"Capping to {ABSOLUTE_MAX_PRICE_HISTORY_LINES}."
        )
        results["PRICE_LAST_N"] = (PRICE_LAST_N, ABSOLUTE_MAX_PRICE_HISTORY_LINES, True)
    else:
        results["PRICE_LAST_N"] = (PRICE_LAST_N, PRICE_LAST_N, False)
    
    return results
