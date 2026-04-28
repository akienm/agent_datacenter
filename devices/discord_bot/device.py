"""
DiscordBotDevice — rack registration for the Discord bot.

The bot runs as a thread inside Igor's process (wild_igor/igor/network/discord_bot.py).
Phase 4: wraps it at rack level; health via discord.log recency.
Phase 5 (T-adc-network-discord-relocate): bot code relocates here.

Configuration:
  DISCORD_LOG_PATH   — override discord.log location
  IGOR_TMUX_SESSION  — Igor tmux session name (default: igor)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from agent_datacenter.device import BaseDevice, INTERFACE_VERSION

_START_TIME = time.time()
_DEFAULT_LOG = os.path.expanduser(
    os.environ.get("DISCORD_LOG_PATH", "~/.TheIgors/local/logs/discord.log")
)
_LOG_HEALTHY_WINDOW = 300  # 5 min — bot logs every event; silence = unhealthy


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_recency_seconds(log_path: str) -> float | None:
    """Return seconds since discord.log was last modified, or None if absent."""
    try:
        return time.time() - os.path.getmtime(log_path)
    except OSError:
        return None


class DiscordBotDevice(BaseDevice):
    """
    Rack device for the Discord bot embedded in Igor's process.

    Health is measured via discord.log recency — the bot logs every event,
    so staleness or absence indicates the bot thread has died.
    """

    DEVICE_ID = "discord-bot"

    def __init__(self, log_path: str = _DEFAULT_LOG) -> None:
        self._log_path = log_path
        self._blocked = False
        self._block_reason = ""

    # ── BaseDevice contract ───────────────────────────────────────────────────

    def who_am_i(self) -> dict:
        return {
            "device_id": self.DEVICE_ID,
            "name": "DiscordBot",
            "version": "0.1.0",
            "purpose": "Discord channel push for Igor (webhook + bot send; v1 push-only)",
        }

    def requirements(self) -> dict:
        return {
            "deps": ["discord.py>=2.0", "aiohttp"],
            "system": ["DISCORD_BOT_TOKEN env var set", "Igor process running"],
        }

    def capabilities(self) -> dict:
        return {
            "can_send": True,
            "can_receive": False,  # v1 push-only; inbound routing is Phase 5
            "emitted_keywords": ["discord_send"],
            "mcp_endpoint": None,
        }

    def comms(self) -> dict:
        return {
            "address": f"comms://{self.DEVICE_ID}/inbox",
            "mode": "write_only",
            "supports_push": True,
            "supports_pull": False,
            "supports_nudge": False,
        }

    def interface_version(self) -> str:
        return INTERFACE_VERSION

    def health(self) -> dict:
        if self._blocked:
            return {
                "status": "unhealthy",
                "detail": f"blocked: {self._block_reason}",
                "checked_at": _now(),
            }
        age = _log_recency_seconds(self._log_path)
        if age is None:
            return {
                "status": "degraded",
                "detail": f"discord.log not found at {self._log_path}",
                "checked_at": _now(),
            }
        if age > _LOG_HEALTHY_WINDOW:
            return {
                "status": "degraded",
                "detail": f"discord.log stale ({age:.0f}s since last write)",
                "checked_at": _now(),
            }
        return {
            "status": "healthy",
            "detail": f"discord.log fresh ({age:.0f}s ago)",
            "checked_at": _now(),
        }

    def uptime(self) -> float:
        return time.time() - _START_TIME

    def startup_errors(self) -> list:
        return []

    def logs(self) -> dict:
        return {"paths": {"discord": self._log_path}}

    def update_info(self) -> dict:
        return {"current_version": "0.1.0", "update_available": False}

    def where_and_how(self) -> dict:
        return {
            "host": "localhost",
            "pid": os.getpid(),
            "launch_command": "embedded in Igor process (IgorShim().start() starts the bot thread)",
        }

    def restart(self) -> None:
        self._blocked = False
        self._block_reason = ""

    def block(self, reason: str) -> None:
        self._blocked = True
        self._block_reason = reason

    def halt(self) -> None:
        self._blocked = True
        self._block_reason = "halt requested"

    def recovery(self) -> None:
        self._blocked = False
        self._block_reason = ""
