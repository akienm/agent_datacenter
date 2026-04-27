"""
Skeleton tests — registration, health rollup, namespace collision.

All tests use StubDevice and an in-memory registry (tmp_path) — no real
Postgres or IMAP required.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from agent_datacenter.device import BaseDevice, INTERFACE_VERSION
from agent_datacenter.skeleton.exceptions import AuthError, RegistrationError
from agent_datacenter.skeleton.health import rack_health_async
from agent_datacenter.skeleton.skeleton import Skeleton
from config.device_config import DeviceConfig
from skeleton.registry import DeviceRegistry
from tests.fixtures.stub_devices import StubDevice


def _make_skeleton(tmp_path: Path) -> Skeleton:
    registry = DeviceRegistry(path=tmp_path / "devices.json")
    return Skeleton(registry=registry)


# ── Registration ──────────────────────────────────────────────────────────────


def test_skeleton_self_registers(tmp_path):
    skel = _make_skeleton(tmp_path)
    ids = [d["id"] for d in skel._registry.list_devices()]
    assert "skeleton" in ids


def test_register_device_appears_in_registry(tmp_path):
    skel = _make_skeleton(tmp_path)
    device = StubDevice()
    skel.register_device(device)
    ids = [d["id"] for d in skel._registry.list_devices()]
    assert "stub" in ids


def test_register_device_status_online(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    record = skel._registry.get_device("stub")
    assert record is not None
    assert record["status"] == "online"


def test_deregister_device_status_offline(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    skel.deregister_device("stub")
    record = skel._registry.get_device("stub")
    # Device record persists after deregistration (mailbox retention)
    assert record is not None
    assert record["status"] == "offline"
    # Not in live devices dict
    assert "stub" not in skel._devices


def test_deregister_allows_reattach(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    skel.deregister_device("stub")
    # Re-registration after offline must succeed (reattach scenario)
    skel.register_device(StubDevice())
    assert "stub" in skel._devices


# ── Collision ─────────────────────────────────────────────────────────────────


def test_namespace_collision_raises(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    with pytest.raises(RegistrationError, match="already registered"):
        skel.register_device(StubDevice())


def test_collision_after_reregister_not_deregistered(tmp_path):
    """Online device cannot be reregistered without deregister first."""
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    # Device is now online; second call must fail even with same object
    with pytest.raises(RegistrationError):
        skel.register_device(StubDevice())
    # Registry state unchanged (no duplicate entry)
    stubs = [d for d in skel._registry.list_devices() if d["id"] == "stub"]
    assert len(stubs) == 1


# ── Health rollup ─────────────────────────────────────────────────────────────


def test_health_rollup_healthy(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    result = asyncio.run(rack_health_async(skel._devices))
    assert "stub" in result
    assert result["stub"]["healthy"] is True
    assert result["stub"]["error"] is None


def test_health_rollup_empty_when_no_devices(tmp_path):
    skel = _make_skeleton(tmp_path)
    result = asyncio.run(rack_health_async(skel._devices))
    # Only skeleton is in registry, but it's not in _devices (Skeleton manages itself)
    assert result == {}


def test_health_rollup_captures_exception(tmp_path):
    class BrokenDevice(StubDevice):
        def health(self):
            raise RuntimeError("disk gone")

    skel = _make_skeleton(tmp_path)
    # Manually inject a broken device — bypass register_device id collision check
    skel._devices["broken"] = BrokenDevice()
    result = asyncio.run(rack_health_async(skel._devices))
    assert "broken" in result
    assert result["broken"]["healthy"] is False
    assert "disk gone" in result["broken"]["error"]


def test_health_rollup_timeout(tmp_path):
    class SlowDevice(StubDevice):
        def health(self):
            time.sleep(5)
            return {"status": "healthy", "checked_at": "x"}

    skel = _make_skeleton(tmp_path)
    skel._devices["slow"] = SlowDevice()
    result = asyncio.run(rack_health_async(skel._devices, timeout=0.1))
    assert result["slow"]["healthy"] is False
    assert result["slow"]["error"] == "timeout"


# ── Access control ────────────────────────────────────────────────────────────


def test_auth_halt_skeleton_caller_allowed(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    # 'skeleton' is always allowed to halt any device
    skel._check_caller_auth("skeleton", "stub", "halt")  # must not raise


def test_auth_halt_self_allowed(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    # A device can halt itself
    skel._check_caller_auth("stub", "stub", "halt")  # must not raise


def test_auth_halt_third_party_raises(tmp_path):
    skel = _make_skeleton(tmp_path)
    skel.register_device(StubDevice())
    with pytest.raises(AuthError):
        skel._check_caller_auth("CC.0", "stub", "halt")
