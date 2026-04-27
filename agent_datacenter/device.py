"""
BaseDevice — the rack contract.

Every component that registers on agent_datacenter must implement this interface.
The rack calls these methods for health rollup, lifecycle management, and routing.

Return shapes are intentionally loose dicts rather than typed dataclasses so that
devices can include extra fields without breaking the rack. The rigid keywords are
documented per method; extra keys are allowed.
"""

from abc import ABC, abstractmethod

INTERFACE_VERSION = "1.0"


class BaseDevice(ABC):
    """Abstract base for all rack devices."""

    @abstractmethod
    def who_am_i(self) -> dict:
        """Return device identity. Required keys: device_id (str), name (str), version (str)."""

    @abstractmethod
    def requirements(self) -> dict:
        """Return runtime dependencies. Required key: deps (list[str])."""

    @abstractmethod
    def capabilities(self) -> dict:
        """
        Return what this device can do and what envelope keywords it emits.
        Required keys: can_send (bool), can_receive (bool), emitted_keywords (list[str]).
        """

    @abstractmethod
    def comms(self) -> dict:
        """
        Return comms address and direction flags.
        Required keys: address (str comms:// URI), mode (str: read_only|write_only|read_write),
        supports_push (bool), supports_pull (bool), supports_nudge (bool).
        """

    @abstractmethod
    def interface_version(self) -> str:
        """Return the INTERFACE_VERSION this device was built against."""

    @abstractmethod
    def health(self) -> dict:
        """
        Return current health status. Required keys: status (str: healthy|degraded|unhealthy),
        detail (str), checked_at (str ISO 8601).
        """

    @abstractmethod
    def uptime(self) -> float:
        """Return seconds since this device started."""

    @abstractmethod
    def startup_errors(self) -> list:
        """Return list of error strings from the most recent startup attempt."""

    @abstractmethod
    def logs(self) -> dict:
        """
        Return log paths for this device.
        Required key: paths (dict[str, str] subsystem -> log path).
        """

    @abstractmethod
    def update_info(self) -> dict:
        """
        Return update/version metadata.
        Required keys: current_version (str), update_available (bool).
        """

    @abstractmethod
    def where_and_how(self) -> dict:
        """
        Return deployment location and launch method.
        Required keys: host (str), pid (int), launch_command (str).
        """

    @abstractmethod
    def restart(self) -> None:
        """Trigger a graceful restart of this device."""

    @abstractmethod
    def block(self, reason: str) -> None:
        """Block this device from restarting. Rack will not auto-relaunch."""

    @abstractmethod
    def halt(self) -> None:
        """Halt this device immediately. Rack will not restart unless unblocked."""

    @abstractmethod
    def recovery(self) -> None:
        """Attempt recovery from a degraded/unhealthy state."""
