# agent_datacenter

Runtime substrate for agent deployments. **Not a framework** — a rack you
plug devices into.

## What this is

A portable, Igor-independent platform:

- **Skeleton** — MCP aggregator on localhost; flat-file device registry
- **IMAP bus** — comms:// addressing; pub/sub via IDLE; 24hr message retention
- **Device contract** — BaseDevice / BaseShim; every agent component is a device
- **agentctl** — `agentctl init` bootstraps an empty rack on a clean machine

## What this is NOT

- Not Igor. Igor is one device that runs on the rack.
- Not TheIgors. That repo is Akien's research workspace; this is the portable substrate.
- Not a monolith. Each device is independently runnable and replaceable.

## Quick start

```bash
pip install -e .
agentctl init   # Phase 4 target — not yet implemented
```

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Design locked, repo scaffold | ✅ done |
| 1 | Skeleton + IMAP bus + Postgres device | pending |
| 2 | Igor on the rack | pending |
| 3 | Claude on the rack + YGM | pending |
| 4 | Discord, SWADL, browser-use, installer | pending |
| 5 | Cleanup (superseded TheIgors plumbing) | pending |

## Spec

Full design spec: `D-agent-datacenter-spec-2026-04-27` in TheIgors palace.
