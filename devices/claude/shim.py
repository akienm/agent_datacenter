"""
ClaudeShim — manages YGM hook registration for the Claude Code session.

start(): Creates CC.0 mailbox on the IMAP bus and registers a
         UserPromptSubmit hook in ~/.claude/settings.json that calls
         ygm_check.py on every query submission.

stop():  Removes the YGM hook from settings.json (leaves CC.0 mailbox
         in place — 24hr retention handles cleanup).

self_test(): Verifies hook is registered and settings.json is valid JSON.

The hook calls:
  python3 -m devices.claude.ygm_check

from the agent_datacenter repo root, so the PYTHONPATH needs to be set
to the repo root in the hook command.
"""

from __future__ import annotations

import json
import logging
import os

from agent_datacenter.shim import BaseShim
from devices.claude.constants import GLOBAL_MAILBOX, get_session_mailbox

log = logging.getLogger(__name__)

_SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")
_HOOK_ID = "ygm-nudge"

# The hook command — uses the repo root PYTHONPATH so devices.claude resolves
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_HOOK_COMMAND = (
    f"cd {_REPO_ROOT} && python3 -m devices.claude.ygm_check 2>/dev/null || true"
)


def _load_settings() -> dict:
    if not os.path.exists(_SETTINGS_PATH):
        return {}
    with open(_SETTINGS_PATH) as f:
        return json.load(f)


def _save_settings(settings: dict) -> None:
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def _hook_entry() -> dict:
    return {
        "id": _HOOK_ID,
        "command": _HOOK_COMMAND,
    }


def _hook_registered(settings: dict) -> bool:
    hooks = settings.get("hooks", {})
    for hook in hooks.get("UserPromptSubmit", []):
        if isinstance(hook, dict) and hook.get("id") == _HOOK_ID:
            return True
    return False


class ClaudeShim(BaseShim):
    """
    Manages Claude's presence on the rack.

    Registers the YGM hook in ~/.claude/settings.json so that every
    query submission triggers a mailbox check and injects an inbox
    summary when mail is waiting.
    """

    def __init__(self, imap_server=None) -> None:
        self._imap = imap_server

    @property
    def device_id(self) -> str:
        return "claude"

    def start(self) -> bool:
        # Ensure CC.0 mailbox exists on the bus
        if self._imap is not None:
            try:
                self._imap.create_mailbox(GLOBAL_MAILBOX)
                session_mailbox = get_session_mailbox()
                if session_mailbox != GLOBAL_MAILBOX:
                    self._imap.create_mailbox(session_mailbox)
                log.info(
                    "Claude mailboxes ensured: %s, %s", GLOBAL_MAILBOX, session_mailbox
                )
            except Exception as exc:
                log.warning("Could not ensure Claude mailboxes: %s", exc)

        # Register YGM hook in ~/.claude/settings.json
        try:
            settings = _load_settings()
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Could not read %s: %s", _SETTINGS_PATH, exc)
            return False

        if _hook_registered(settings):
            log.info("YGM hook already registered in %s", _SETTINGS_PATH)
            return True

        hooks = settings.setdefault("hooks", {})
        hooks.setdefault("UserPromptSubmit", []).append(_hook_entry())

        try:
            _save_settings(settings)
            log.info("YGM hook registered in %s", _SETTINGS_PATH)
            return True
        except OSError as exc:
            log.error("Could not write %s: %s", _SETTINGS_PATH, exc)
            return False

    def stop(self) -> bool:
        try:
            settings = _load_settings()
        except (json.JSONDecodeError, OSError):
            return True

        hooks = settings.get("hooks", {})
        before = hooks.get("UserPromptSubmit", [])
        after = [
            h for h in before if not (isinstance(h, dict) and h.get("id") == _HOOK_ID)
        ]
        if len(after) == len(before):
            return True  # already removed

        hooks["UserPromptSubmit"] = after
        if not after:
            del hooks["UserPromptSubmit"]
        if not hooks:
            del settings["hooks"]

        try:
            _save_settings(settings)
            log.info("YGM hook removed from %s", _SETTINGS_PATH)
            return True
        except OSError as exc:
            log.error("Could not write %s: %s", _SETTINGS_PATH, exc)
            return False

    def restart(self) -> bool:
        return self.stop() and self.start()

    def self_test(self) -> dict:
        try:
            settings = _load_settings()
        except json.JSONDecodeError as exc:
            return {
                "passed": False,
                "details": f"{_SETTINGS_PATH} is not valid JSON: {exc}",
            }
        except FileNotFoundError:
            return {
                "passed": True,
                "details": f"{_SETTINGS_PATH} does not exist yet (start() will create it)",
            }

        if _hook_registered(settings):
            return {
                "passed": True,
                "details": f"YGM hook '{_HOOK_ID}' registered in {_SETTINGS_PATH}",
            }
        return {
            "passed": False,
            "details": f"YGM hook '{_HOOK_ID}' not found in {_SETTINGS_PATH} — call start()",
        }

    def rollback(self) -> None:
        self.stop()
        log.info("ClaudeShim rollback complete")
