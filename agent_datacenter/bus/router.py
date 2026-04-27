"""
Router — comms:// URI resolver and message dispatcher.

The comms:// scheme is the only addressing layer in agent_datacenter. Callers are
topology-blind: they address by name; the router handles IMAP APPEND dispatch.

Pub/sub falls out naturally from IMAP IDLE: comms://Shared → all IDLE subscribers
receive the message when they next poll or wake from IDLE. No separate pub/sub
layer is needed.

URI shape:
    comms://{mailbox_name}

Examples:
    comms://Shared              → publish to Shared mailbox (fan-out via IDLE)
    comms://CC.0                → direct to Claude's main mailbox
    comms://igor-wild-0001      → direct to Igor's device mailbox
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bus.envelope import Envelope

if TYPE_CHECKING:
    from bus.imap_server import IMAPServer

log = logging.getLogger(__name__)

_SCHEME = "comms://"


class AddressError(Exception):
    """Raised when a comms:// address cannot be resolved to a known mailbox."""


class Router:
    """
    Resolves comms:// URIs to IMAP mailboxes and dispatches messages.

    send() = resolve() + imap_server.append(). The split exists so callers
    can validate addresses before composing messages.

    Self-healing: if the IMAP server raises ConnectionError on send(), Router
    delegates to BusLauncher.relaunch() and retries once. If relaunch fails or
    the bus is blocked, BusBlockedError / BusUnavailableError propagate to caller.
    Pass bus_launcher=None (default) to disable self-healing (e.g. in tests).
    """

    def __init__(
        self,
        imap_server: "IMAPServer",
        bus_launcher: "BusLauncher | None" = None,
    ) -> None:
        self._imap = imap_server
        self._launcher = bus_launcher

    def resolve(self, address: str) -> str:
        """
        Parse mailbox_name from a comms:// address and verify it exists.

        Returns the mailbox name (the bare name, not the full URI).
        Raises AddressError if the URI is malformed or the mailbox is not registered.
        """
        if not address.startswith(_SCHEME):
            raise AddressError(
                f"Invalid address {address!r}: must start with 'comms://'"
            )
        mailbox = address[len(_SCHEME) :]
        if not mailbox:
            raise AddressError(f"Invalid address {address!r}: mailbox name is empty")

        known = self._imap.list_mailboxes()
        if mailbox not in known:
            raise AddressError(
                f"Unknown mailbox {mailbox!r} in address {address!r}. "
                f"Known mailboxes: {known}"
            )
        return mailbox

    def send(self, address: str, envelope: Envelope) -> None:
        """
        Dispatch an envelope to the mailbox identified by the comms:// address.

        Resolves the address first — raises AddressError immediately if unknown.
        On ConnectionError, delegates to BusLauncher for self-healing if configured.
        """
        from agent_datacenter.bus.bus_launcher import BusBlockedError, BusLauncher

        if self._launcher is not None and self._launcher.is_blocked():
            raise BusBlockedError(
                "Bus is blocked — operator must manually clear block before sending."
            )

        try:
            mailbox = self.resolve(address)
            self._imap.append(mailbox, envelope)
        except (ConnectionError, OSError) as exc:
            if self._launcher is None:
                raise
            log.warning("Bus unreachable on send to %r: %s", address, exc)
            relaunched = self._launcher.relaunch()
            if not relaunched:
                from agent_datacenter.bus.bus_launcher import BusUnavailableError

                raise BusUnavailableError(
                    f"Bus relaunch failed — cannot deliver to {address!r}"
                ) from exc
            # Retry once after successful relaunch
            mailbox = self.resolve(address)
            self._imap.append(mailbox, envelope)
            log.info("Retry after relaunch succeeded for %r", address)
