"""
DeviceConfig — per-device policy dataclass.

Rack default is drop-oldest: agent traffic is typically state/status updates
where newer supersedes older. Set drop_newest=True for order-preserving
pipelines (e.g. a command queue where sequence matters).

All defaults are rack-level sensible. Override per device at registration time.
"""

from dataclasses import dataclass
from dataclasses import asdict as _asdict


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
