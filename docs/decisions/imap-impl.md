# Decision: IMAP Bus Implementation

**date:** 2026-04-27  
**status:** locked  
**decision_id:** D-adc-phase-0-2026-04-27

---

## Decision

**Production:** Dovecot  
**Test fixtures:** Python stub (~80-line asyncio server)

---

## Options evaluated

### Option A: Dovecot

- System dep: `apt install dovecot-imapd dovecot-core` (available, version 2.3.21 on Ubuntu 24.04)
- Mature IDLE support (RFC 2177)
- Expire plugin for 24hr message retention (config: `mail_plugins = expire`)
- Text-file config (`/etc/dovecot/`) — reasonably inspectable
- Maildir storage: no SQLite, no embedded DB
- Requires system privileges at install time (package install + service user)
- Works at work: portable across ubuntu/macOS (macOS via Homebrew)
- Multi-device pub/sub via IDLE works natively — standard IMAP semantics

### Option B: Pure Python IMAP server

- Spike conducted 2026-04-27: asyncio-based server in ~80 lines handles:
  - CAPABILITY, LOGIN, SELECT, APPEND, IDLE, DONE, LOGOUT
  - In-memory message storage (no SQLite — uses `defaultdict(list)`)
  - IDLE notification via `asyncio.Event`
- Verified: APPEND via imaplib client succeeds
- No system dep, controllable from inside the package, testable in-process
- **Not chosen for production**: no persistence, no TLS, no auth, not a real IMAP implementation. Maintenance burden would grow as we need more RFC compliance.

---

## Tradeoffs

| | Dovecot | Python stub |
|---|---|---|
| IDLE | native, RFC-compliant | asyncio.Event (works for tests) |
| 24hr retention | Expire plugin | not needed (in-memory) |
| System dep | yes (apt/brew) | none |
| TLS | built-in | not implemented |
| Auth | PAM / passwd file | skip (test-only) |
| Persistence | Maildir on disk | in-memory only |
| Maintenance | zero (mature project) | grows with RFC coverage |

---

## Architecture

The bus layer (`bus/`) will:
1. Try to connect to a running Dovecot instance (localhost:143 or configured port)
2. If not reachable, use the Python stub **for tests only** (stub raises `TestOnlyError` if called in non-test context)
3. Never fall back silently — startup fails loudly if Dovecot unreachable in production mode

The Python stub lives at `tests/fixtures/imap_stub.py`. A starting reference is in `TheIgors/lab/spikes/imap_stub_spike.py`.

---

## What this means for Phase 1

`T-adc-imap-server-embedded` will:
- Ship Dovecot install + config helper (called by `agentctl init` in Phase 4)
- Ship `tests/fixtures/imap_stub.py` for in-process test fixtures
- Bus connection code detects `AGENT_DATACENTER_TEST_MODE=1` and uses stub

No SQLite at any layer. Dovecot uses Maildir (flat files). Python stub uses `defaultdict`.

---

## Related tickets

- `T-adc-imap-server-embedded` (Phase 1) — Dovecot install helper + Python stub
- `T-adc-imap-mailbox-lifecycle` (Phase 1) — mailbox create/delete per device lifecycle
- `T-adc-imap-24hr-retention` (Phase 1) — Dovecot Expire plugin config
- `T-adc-portable-bootstrap` (Phase 1) — `agentctl init` eventually calls Dovecot setup
