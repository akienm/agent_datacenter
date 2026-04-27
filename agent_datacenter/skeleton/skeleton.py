"""
Skeleton — MCP aggregator and central registry for agent_datacenter.

The skeleton is device #1 on every rack. It:
  - Exposes a single MCP endpoint (rack.*) for rack-level operations
  - Maintains the flat-file device registry (no Postgres dependency)
  - Detects namespace collisions at registration time (fails hard before start)
  - Proxies {device_id}.health to each registered device object

v1 proxy scope: rack.* tools + per-device .health tool.
Full tool-namespace proxying (transparent MCP-over-MCP) is a future ticket.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from agent_datacenter.device import BaseDevice, INTERFACE_VERSION
from agent_datacenter.skeleton.exceptions import RegistrationError
from config.device_config import DeviceConfig
from skeleton.registry import DeviceRegistry

log = logging.getLogger(__name__)

_START_TIME = time.time()


class Skeleton(BaseDevice):
    DEVICE_ID = "skeleton"

    def __init__(self, registry: DeviceRegistry | None = None) -> None:
        self._registry = registry or DeviceRegistry()
        self._devices: dict[str, BaseDevice] = {}  # live device objects
        self._mcp = FastMCP("agent_datacenter")
        self._setup_rack_tools()
        # Register self in the flat-file registry
        self._registry.register(
            self.DEVICE_ID,
            DeviceConfig(manual_block_only=True),
            "comms://skeleton/inbox",
            name="Skeleton",
        )
        log.info("skeleton initialized — rack.* tools registered")

    # ── MCP tool registration ─────────────────────────────────────────────────

    def _setup_rack_tools(self) -> None:
        skel = self

        @self._mcp.tool()
        def rack_devices() -> list[dict]:
            """List all registered devices and their current status."""
            return skel._registry.list_devices()

        @self._mcp.tool()
        def rack_health() -> dict:
            """Return a health rollup across all registered devices."""
            return skel._health_rollup()

        @self._mcp.tool()
        def rack_channels() -> list[str]:
            """List all comms:// mailbox addresses registered on this rack."""
            return [d.get("mailbox", "") for d in skel._registry.list_devices()]

    def _health_rollup(self) -> dict:
        rollup = {}
        for device_id, device in self._devices.items():
            try:
                rollup[device_id] = device.health()
            except Exception as e:
                rollup[device_id] = {
                    "status": "unhealthy",
                    "detail": str(e),
                    "checked_at": _now(),
                }
        return rollup

    # ── Device registration ───────────────────────────────────────────────────

    def register_device(
        self,
        device: BaseDevice,
        config: DeviceConfig | None = None,
        mailbox: str | None = None,
    ) -> None:
        device_id = device.who_am_i()["device_id"]

        if device_id in self._devices:
            raise RegistrationError(
                f"Device '{device_id}' is already registered. "
                "Deregister before re-registering."
            )

        cfg = config or DeviceConfig()
        mbox = mailbox or device.comms().get("address", f"comms://{device_id}/inbox")

        self._registry.register(
            device_id, cfg, mbox, name=device.who_am_i().get("name", device_id)
        )
        self._devices[device_id] = device

        # Expose {device_id}.health as an MCP tool
        self._add_device_health_tool(device_id, device)
        log.info("registered device %s (mailbox=%s)", device_id, mbox)

    def deregister_device(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        self._registry.deregister(device_id)
        # Note: MCP tools registered via FastMCP are not dynamically removable in v1.
        # The tool remains but returns an error after deregistration.
        log.info("deregistered device %s", device_id)

    def _add_device_health_tool(self, device_id: str, device: BaseDevice) -> None:
        skel = self

        # Use a closure to capture device_id/device correctly
        def make_health_tool(did: str, dev: BaseDevice):
            tool_name = f"{did}_health"

            @skel._mcp.tool(name=tool_name)
            def device_health() -> dict:
                f"""Return health for device '{did}'."""
                if did not in skel._devices:
                    return {
                        "status": "unhealthy",
                        "detail": f"device '{did}' deregistered",
                        "checked_at": _now(),
                    }
                try:
                    return dev.health()
                except Exception as e:
                    return {
                        "status": "unhealthy",
                        "detail": str(e),
                        "checked_at": _now(),
                    }

        make_health_tool(device_id, device)

    # ── BaseDevice contract ───────────────────────────────────────────────────

    def who_am_i(self) -> dict:
        return {
            "device_id": self.DEVICE_ID,
            "name": "Skeleton",
            "version": "1.0.0",
            "purpose": "MCP aggregator and device registry",
        }

    def requirements(self) -> dict:
        return {"deps": ["mcp"]}

    def capabilities(self) -> dict:
        return {
            "can_send": False,
            "can_receive": True,
            "emitted_keywords": [],
            "mcp_endpoint": "stdio",
        }

    def comms(self) -> dict:
        return {
            "address": "comms://skeleton/inbox",
            "mode": "read_write",
            "supports_push": False,
            "supports_pull": True,
            "supports_nudge": False,
        }

    def interface_version(self) -> str:
        return INTERFACE_VERSION

    def health(self) -> dict:
        n = len(self._devices)
        return {
            "status": "healthy",
            "registered_devices": n,
            "detail": f"{n} device(s) on rack",
            "checked_at": _now(),
        }

    def uptime(self) -> float:
        return time.time() - _START_TIME

    def startup_errors(self) -> list:
        return []

    def logs(self) -> dict:
        return {"paths": {}}

    def update_info(self) -> dict:
        return {"current_version": "1.0.0", "update_available": False}

    def where_and_how(self) -> dict:
        return {
            "host": os.environ.get("HOSTNAME", "localhost"),
            "pid": os.getpid(),
            "launch_command": "agentctl init",
        }

    def restart(self) -> None:
        pass  # skeleton restart handled at process level

    def block(self, reason: str) -> None:
        log.warning("skeleton blocked: %s", reason)

    def halt(self) -> None:
        log.warning("skeleton halt requested")

    def recovery(self) -> None:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
