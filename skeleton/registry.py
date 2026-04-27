"""
DeviceRegistry — flat-file device registry for the skeleton.

Why flat-file and not Postgres: the skeleton manages Postgres. If the registry
lived in Postgres, skeleton couldn't restart Postgres when Postgres goes down —
circular dependency. A JSON flat file breaks the cycle.

File location: {runtime_dir}/devices.json (default ~/.agent_datacenter/devices.json)
Write discipline: always write to .tmp then rename — never corrupts main file on crash.

Device record shape:
    {
        "id": str,
        "name": str,
        "status": "online" | "offline" | "blocked",
        "mailbox": str,          # comms:// URI
        "config": {...},         # DeviceConfig.to_dict()
        "registered_at": str,    # ISO 8601
    }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from config.device_config import DeviceConfig

log = logging.getLogger(__name__)

DEFAULT_REGISTRY_DIR = Path.home() / ".agent_datacenter"
DEFAULT_REGISTRY_PATH = DEFAULT_REGISTRY_DIR / "devices.json"


class DeviceRegistry:
    def __init__(self, path: Path = DEFAULT_REGISTRY_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._atomic_write({})

    def register(
        self, device_id: str, config: DeviceConfig, mailbox: str, name: str = ""
    ) -> None:
        data = self._load()
        data[device_id] = {
            "id": device_id,
            "name": name or device_id,
            "status": "online",
            "mailbox": mailbox,
            "config": config.to_dict(),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(data)
        log.info("registered device %s at %s", device_id, mailbox)

    def deregister(self, device_id: str) -> None:
        data = self._load()
        if device_id in data:
            del data[device_id]
            self._atomic_write(data)
            log.info("deregistered device %s", device_id)

    def list_devices(self) -> list[dict]:
        return list(self._load().values())

    def get_device(self, device_id: str) -> dict | None:
        return self._load().get(device_id)

    def set_status(self, device_id: str, status: str) -> None:
        data = self._load()
        if device_id in data:
            data[device_id]["status"] = status
            self._atomic_write(data)

    def ping_on_restart(self, ping_fn) -> None:
        """
        Called after skeleton restart. For each registered device, call ping_fn(device_id)
        which returns True if reachable. Sets status online/offline accordingly.
        ping_fn signature: (device_id: str) -> bool
        """
        data = self._load()
        changed = False
        for device_id, record in data.items():
            if record.get("status") == "blocked":
                continue
            reachable = False
            try:
                reachable = ping_fn(device_id)
            except Exception:
                pass
            new_status = "online" if reachable else "offline"
            if record["status"] != new_status:
                record["status"] = new_status
                changed = True
                log.info("device %s → %s (ping-on-restart)", device_id, new_status)
        if changed:
            self._atomic_write(data)

    def _atomic_write(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self._path)

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("registry file corrupt or missing — starting empty")
            return {}
