"""
DeviceConfig — per-device policy dataclass + runtime path helpers.

Rack default is drop-oldest: agent traffic is typically state/status updates
where newer supersedes older. Set drop_newest=True for order-preserving
pipelines (e.g. a command queue where sequence matters).

All defaults are rack-level sensible. Override per device at registration time.

Runtime path helpers
--------------------
agent_datacenter_home() → ~/.agent_datacenter/ (or $AGENT_DATACENTER_HOME)
agent_datacenter_logs() → $AGENT_DATACENTER_HOME/logs/

Set AGENT_DATACENTER_HOME to relocate the entire runtime tree (CI, multi-user,
non-home mounts). Default is ~/.agent_datacenter/ for single-user desktop use.
"""

import os
from dataclasses import asdict as _asdict
from dataclasses import dataclass
from pathlib import Path


def agent_datacenter_home() -> Path:
    """Root of the agent_datacenter runtime tree."""
    return Path(
        os.environ.get(
            "AGENT_DATACENTER_HOME",
            str(Path.home() / ".agent_datacenter"),
        )
    )


def agent_datacenter_logs() -> Path:
    """Root of the hierarchical log tree: $AGENT_DATACENTER_HOME/logs/"""
    return agent_datacenter_home() / "logs"


@dataclass
class DeviceConfig:
    # Queue overflow — rack default: drop oldest
    max_queue_length: int = 100
    drop_newest: bool = False  # True = drop-newest (order-preserving mode)

    # Restart loop protection
    max_restart_failures: int = 3
    restart_window_seconds: int = 60
    restart_backoff_seconds: float = 5.0

    # Gate: when True the rack will never auto-unblock this device after
    # a restart-loop failure — only a manual operator ungate clears it.
    manual_block_only: bool = False

    def to_dict(self) -> dict:
        return _asdict(self)


# Rack-level retention policy. All mailboxes retain messages for this many hours
# regardless of SEEN status. After expiry, messages are expunged permanently.
RETENTION_HOURS: int = 24
