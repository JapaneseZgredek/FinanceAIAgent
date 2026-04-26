"""
Claude Code CLI client — async wrapper around `claude --print` subprocess calls.

Uses asyncio.create_subprocess_exec so the event loop is never blocked,
making this client compatible with FastAPI and other async frameworks.
"""

import asyncio
import logging
import time

from app.utils.errors import FinanceAgentError

logger = logging.getLogger(__name__)


class ClaudeClient:
    """
    Executes `claude --print` subprocess calls asynchronously.

    Uses asyncio.create_subprocess_exec — the event loop stays unblocked
    during the subprocess call, enabling concurrent Step 1 + Step 2 execution
    and future FastAPI compatibility.

    Args:
        model: Claude model ID to pass via --model flag.
        timeout: Maximum seconds to wait per subprocess call.

    Example:
        client = ClaudeClient(model="claude-opus-4-6", timeout=180)
        result = await client.run("Analyse BTC price data...")
        result_with_web = await client.run("Search for news...", allowed_tools="WebSearch,WebFetch")
    """

    def __init__(self, model: str, timeout: int) -> None:
        self.model = model
        self.timeout = timeout

    async def run(self, prompt: str, allowed_tools: str = "") -> str:
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

        tools_label = f" tools={allowed_tools}" if allowed_tools else ""
        logger.info(
            "Claude CLI starting [model=%s, timeout=%ds%s]",
            self.model, self.timeout, tools_label,
        )
        logger.debug("Prompt length: %d chars", len(prompt))
        t0 = time.perf_counter()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("Claude CLI binary not found in PATH")
            raise FinanceAgentError(
                "Claude CLI not found. Make sure `claude` is installed and in PATH. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.error("Claude CLI timed out after %ds", self.timeout)
            raise FinanceAgentError(
                f"Claude CLI timed out after {self.timeout}s. "
                "Try again or increase timeout."
            )

        if proc.returncode != 0:
            logger.error(
                "Claude CLI failed (rc=%d): %s",
                proc.returncode, stderr.decode()[:200],
            )
            raise FinanceAgentError(
                f"Claude CLI exited with code {proc.returncode}: {stderr.decode()[:500]}"
            )

        elapsed = time.perf_counter() - t0
        response = stdout.decode().strip()
        logger.info(
            "Claude CLI completed in %.1fs (%d chars response)",
            elapsed, len(response),
        )
        return response
