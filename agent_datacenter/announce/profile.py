"""
profile.py — load and validate agent capability profiles.

Profiles are static YAML declarations that describe what an agent type
can bind to. They live at:
  canonical:  agent_datacenter/config/profiles/<agent_id>.yaml  (repo)
  runtime:    ~/.agent_datacenter/profiles/<agent_id>.yaml      (install target)

The broker reads from the runtime directory; tests inject profiles_dir.

v1: no profile inheritance (inherits: [] required). Inheritance with
deep-merge + __replace__ marker is slated for slice 5.

Note on lineage aliases: NOT present in this module by design. The
E-decision (§ 14, 2026-05-01) resolved to ship clean — no backwards-compat
alias path for comms://igor-wild-0001. Single user, research project. If
the lineage form breaks anything, we fix it then.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:
    import yaml  # type: ignore[import]
except ImportError as exc:  # pragma: no cover
    raise ImportError("PyYAML required: pip install pyyaml") from exc

# Default runtime profiles directory — can be overridden per-call.
DEFAULT_PROFILES_DIR = Path("~/.agent_datacenter/profiles").expanduser()

# Top-level keys the profile loader understands; extra keys are preserved
# but logged at DEBUG so callers can detect typos.
_KNOWN_KEYS = frozenset(
    {
        "profile_version",
        "agent_type",
        "description",
        "inherits",
        "allowed_devices",
        "device_permissions",
        "default_channels",
        "state_refs",
        "acl",
        "surfaces",
    }
)


class ProfileNotFoundError(Exception):
    """Raised when no profile YAML exists for the requested agent_id."""


class ProfileValidationError(ValueError):
    """Raised when a profile YAML is missing required fields or is malformed."""


def load_profile(
    agent_id: str,
    profiles_dir: Path | str | None = None,
) -> dict:
    """
    Load profile YAML for agent_id from profiles_dir (default: runtime dir).

    Returns the raw profile dict. v1 skips inheritance (inherits: [] only).
    Raises ProfileNotFoundError if the file is absent.
    Raises ProfileValidationError if required fields are missing.
    """
    d = Path(profiles_dir) if profiles_dir is not None else DEFAULT_PROFILES_DIR
    path = d / f"{agent_id}.yaml"
    if not path.exists():
        raise ProfileNotFoundError(
            f"No profile for agent_id={agent_id!r} — expected {path}"
        )

    text = path.read_text(encoding="utf-8")
    profile = yaml.safe_load(text)

    if not isinstance(profile, dict):
        raise ProfileValidationError(f"Profile for {agent_id!r} is not a YAML mapping")

    _validate(agent_id, profile)

    unknown = set(profile.keys()) - _KNOWN_KEYS
    if unknown:
        log.debug("Profile %r has unrecognised keys: %s", agent_id, unknown)

    inherits = profile.get("inherits", [])
    if inherits:
        log.warning(
            "Profile %r declares inherits=%r but v1 does not process inheritance "
            "(slice 5). Keys will not be merged.",
            agent_id,
            inherits,
        )

    return profile


def profile_yaml_etag(agent_id: str, profiles_dir: Path | str | None = None) -> str:
    """SHA-256 of the raw YAML text — used as cache key in Manifest."""
    d = Path(profiles_dir) if profiles_dir is not None else DEFAULT_PROFILES_DIR
    path = d / f"{agent_id}.yaml"
    if not path.exists():
        raise ProfileNotFoundError(f"No profile for {agent_id!r} at {path}")
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def _validate(agent_id: str, profile: dict) -> None:
    required = {"profile_version", "agent_type"}
    missing = required - profile.keys()
    if missing:
        raise ProfileValidationError(
            f"Profile for {agent_id!r} missing required fields: {missing}"
        )
