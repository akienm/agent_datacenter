# Decision: Claude Mailbox Naming

**date:** 2026-04-27  
**status:** locked  
**decision_id:** D-adc-phase-0-2026-04-27

---

## Naming scheme

| Mailbox | Purpose |
|---|---|
| `CC.0` | Global/broadcast — always present, default delivery target |
| `CC.<session_id>` | Per-session — isolated mailbox for multi-CC deployments |

## Rationale

Multi-CC scenarios exist (4-machine swarm tested in April 2026). Without
per-session mailboxes, messages intended for one CC instance would be visible
to all, causing:
- Spurious context injection
- Confusion about who a YGM message is for
- Double-processing when multiple CC instances share the bus

`CC.0` is the legacy-compatible broadcast. Any CC that doesn't set
`CLAUDE_SESSION_ID` defaults to reading from `CC.0` — safe for single-instance
deployments and backward compatible with pre-mailbox channel patterns.

## Implementation

```python
# devices/claude/constants.py
GLOBAL_MAILBOX = "CC.0"
SESSION_MAILBOX_PREFIX = "CC."
SESSION_ID_ENV_VAR = "CLAUDE_SESSION_ID"

def get_session_mailbox() -> str:
    session_id = os.environ.get(SESSION_ID_ENV_VAR, "").strip()
    if session_id:
        return f"{SESSION_MAILBOX_PREFIX}{session_id}"
    return GLOBAL_MAILBOX
```

## Delivery semantics

- Default delivery target: `CC.0`
- Explicit target: caller passes `session_id` to address a specific CC instance
- YGM/Nudge pipeline: pushes to `CC.0` for global nudges; per-session nudges
  address `CC.<session_id>` of the target CC

## Related tickets

- `T-adc-claude-device-mcp-native` (Phase 3) — Claude device registers using this naming
- `T-adc-ygm-nudge-pipeline` (Phase 3) — YGM delivers to CC.0 by default
