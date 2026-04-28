"""
DiscordBotShim — lifecycle proxy for the Discord bot embedded in Igor.

Phase 4: bot runs as a thread inside Igor's process. start()/stop() are
no-ops — lifecycle is owned by IgorShim. self_test() verifies preconditions.

Phase 5 (T-adc-network-discord-relocate): once bot code moves into
agent_datacenter, this shim will own a standalone discord.py Client.
"""

from __future__ import annotations

import logging
import os
import time

from agent_datacenter.shim import BaseShim

log = logging.getLogger(__name__)

_DEFAULT_LOG = os.path.expanduser(
    os.environ.get("DISCORD_LOG_PATH", "~/.TheIgors/local/logs/discord.log")
)
_LOG_RECENCY_LIMIT = 300  # 5 min


class DiscordBotShim(BaseShim):
    """
    Lifecycle proxy for the Discord bot (Phase 4: embedded-in-Igor mode).

    start() and stop() delegate to IgorShim semantics — the bot starts
    and stops with Igor, not independently.
    """

    def __init__(self, log_path: str = _DEFAULT_LOG) -> None:
        self._log_path = log_path

    @property
    def device_id(self) -> str:
        return "discord-bot"

    def start(self) -> bool:
        log.info("DiscordBotShim.start(): no-op (bot starts with Igor)")
        return True

    def stop(self) -> bool:
        log.info("DiscordBotShim.stop(): no-op (bot stops with Igor)")
        return True

    def restart(self) -> bool:
        return self.stop() and self.start()

    def self_test(self) -> dict:
        token = os.environ.get("DISCORD_BOT_TOKEN", "")
        if not token:
            return {
                "passed": False,
                "details": "DISCORD_BOT_TOKEN not set in environment",
            }
        try:
            age = time.time() - os.path.getmtime(self._log_path)
            if age > _LOG_RECENCY_LIMIT:
                return {
                    "passed": False,
                    "details": f"discord.log stale ({age:.0f}s since last write) — bot may be down",
                }
            return {
                "passed": True,
                "details": f"token set, discord.log fresh ({age:.0f}s ago)",
            }
        except OSError:
            return {
                "passed": False,
                "details": f"discord.log not found at {self._log_path}",
            }

    def rollback(self) -> None:
        log.info("DiscordBotShim.rollback(): no-op")
