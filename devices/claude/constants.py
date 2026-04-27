"""
Claude device mailbox naming constants.

Naming scheme (locked 2026-04-27, D-adc-phase-0-2026-04-27):
  CC.0          — global/broadcast mailbox, always present, legacy-compatible
  CC.<session>  — per-session isolated mailbox for multi-CC deployments

Multi-CC swarms (e.g. 4-machine setup) use per-session mailboxes to avoid
cross-talk. CC.0 is the fallback broadcast when no session is specified.
"""

import os

GLOBAL_MAILBOX = "CC.0"
SESSION_MAILBOX_PREFIX = "CC."
SESSION_ID_ENV_VAR = "CLAUDE_SESSION_ID"


def get_session_mailbox() -> str:
    """Return CC.<session_id> if CLAUDE_SESSION_ID is set, else CC.0."""
    session_id = os.environ.get(SESSION_ID_ENV_VAR, "").strip()
    if session_id:
        return f"{SESSION_MAILBOX_PREFIX}{session_id}"
    return GLOBAL_MAILBOX
