"""
Claude Code CLI client — thin wrapper around `claude --print` subprocess calls.

Isolates all subprocess mechanics (command assembly, timeout, error handling)
from pipeline logic in claude_runner.py.
"""

import logging
import subprocess

from app.utils.errors import FinanceAgentError

logger = logging.getLogger(__name__)


class ClaudeClient:
    """
    Executes `claude --print` subprocess calls and returns stdout.

    Args:
        model: Claude model ID to pass via --model flag.
        timeout: Maximum seconds to wait per subprocess call.

    Example:
        client = ClaudeClient(model="claude-opus-4-6", timeout=180)
        result = client.run("Analyse BTC price data...")
        result_with_web = client.run("Search for news...", allowed_tools="WebSearch,WebFetch")
    """

    def __init__(self, model: str, timeout: int) -> None:
        self.model = model
        self.timeout = timeout

    def run(self, prompt: str, allowed_tools: str = "") -> str:
        """
        Run a single `claude --print` call and return the response.

        Web tools are only granted when explicitly requested — steps that must
        not access the web pass nothing (empty string).

        Args:
            prompt: Prompt text to send to Claude CLI.
            allowed_tools: Comma-separated tool names to enable
                (e.g. "WebSearch,WebFetch"). Empty string = no extra tools.

        Returns:
            Stripped stdout from the Claude CLI process.

        Raises:
            FinanceAgentError: If the process times out, is not found,
                or exits with a non-zero return code.
        """
        cmd = ["claude", "--print", "--model", self.model]

        if allowed_tools:
            cmd += ["--allowedTools", allowed_tools]

        cmd += ["-p", prompt]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise FinanceAgentError(
                f"Claude CLI timed out after {self.timeout}s. "
                "Try again or increase timeout."
            )
        except FileNotFoundError:
            raise FinanceAgentError(
                "Claude CLI not found. Make sure `claude` is installed and in PATH. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )

        if result.returncode != 0:
            raise FinanceAgentError(
                f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}"
            )

        return result.stdout.strip()
