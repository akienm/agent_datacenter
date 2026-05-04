---
name: sprint-batch
description: Run multiple tickets in one session with one shared setup (git pull, venv, env) instead of per-ticket. Takes a selector — today-slate, slate:planned, slate:ad-hoc, decision:D-..., tag:<tag>, or an explicit ticket list. Filters out gated tickets. Topo-sorts by dependencies.
model: sonnet
---

# /sprint-batch — Multi-ticket sprint

Shared setup once, per-ticket loop, shared teardown. Use when /decided just
filed a batch, or when you're clearing a slate.

## Selectors (positional arg)

- `/sprint-batch today-slate` — every pending ticket in today's slate under `## Planned` and `## Ad hoc`
- `/sprint-batch slate:planned` — just the `## Planned` section
- `/sprint-batch slate:ad-hoc` — just the `## Ad hoc` section
- `/sprint-batch decision:D-...` — every ticket with matching `decision_id`
- `/sprint-batch tag:<tag>` — every pending ticket tagged `<tag>` (e.g. `tag:WorkflowOverhaul`)
- `/sprint-batch T-x T-y T-z` — explicit space-separated ticket ids

## Steps

### 1. Resolve target set

Always parse the selector first and resolve it against the canonical
sources — `~/.TheIgors/cc_channel/queue.json` (for ticket selectors) or the
slate file (for slate selectors). Filter to `status=pending` and
`gate=null`. When nothing matches, bail with a clear message — an empty
batch is a signal, not a sprint.

### 2. Topo-sort by dependencies

Always topo-sort before running — gated and dependent tickets must land in
the right order. Build the graph from:
- Explicit `related_to` edges
- Implicit `gate` references ("T-x gated on T-y" → T-y before T-x)
- Same-decision sibling tickets: lowest priority number first

When the graph has cycles, always print the cycle and bail — a cycle is a
dependency-graph bug, not something to silently break by picking an order.
Ask Akien to pick when the graph is cyclic.

### 3. Shared setup (once)

Always run setup once at batch start — per-ticket re-setup just burns time:
```bash
cd ~/TheIgors
git pull --rebase origin main
source venv/bin/activate
export IGOR_HOME_DB_URL=postgresql://igor:choose_a_password@127.0.0.1/Igor-wild-0001
```

Print the ordered plan:
```
SPRINT-BATCH plan (N tickets):
  1. T-xxx (S) — title
  2. T-yyy (M) — title
  ...
```

Unless running in auto mode, always ask Akien: "proceed, reorder, skip-one,
abort?" before the first ticket.

### 4. Per-ticket loop

For each ticket in topo-order, run the /sprint body:

1. **Claim**: `cc_queue.py claim <id>`
2. **Review plan**: when the ticket description carries an /audit-ticket approval stamp, skip asking. Otherwise always invoke /audit-precode on the plan before coding.
3. **Build**: implement the ticket
4. **Test**: `python -m pytest tests/ -x -q 2>&1 | tail -20`
5. **Cleanup** (REQUIRED): always review the diff and remove debris — debug prints, commented code, unused imports, replaced functions, single-use helpers, temp files. Every file in the diff exists on purpose.
6. **Doc-refresh** (when a load-bearing file is touched, per T-docs-live-in-code): always update the top-of-file docstring alongside the code change.
6.5. **Teach Igor — palace deposit (default skip)**: ask "what from this ticket would I deposit into Igor's palace?" Default answer: **skip** — most sprint work is mechanical and shouldn't pollute the palace. Deposit only when novel reasoning emerged: a non-obvious WHY the ticket didn't anticipate, a hidden invariant the refactor surfaced, a workaround whose mechanism the next reader needs, or a bug fix whose ROOT differed from the symptom. When non-skip: propose 0–N palace nodes (path + title + content), surface to Akien inline for review, then INSERT via psql to memory_palace. Workflow consumer of theigors/rules/capability-protocol — closes the "teach Igor as you implement tickets" lapse.
7. **Commit + push** (full cycle, with stash when Igor auto-edits interfere):
   ```bash
   git stash -u && git pull --rebase origin main && git stash pop
   git add <specific files>
   git commit -m "..."
   git push origin main
   ```
8. **Close**: `cc_queue.py done <id> "<summary of what was built>"` then retitle to add `CLOSED:` prefix:
   ```bash
   # Strip old prefix (DESIGNED:/NEW:/NEEDS DESIGN:) and prepend CLOSED:
   python3 ~/TheIgors/lab/claudecode/cc_queue.py retitle <id> "CLOSED: <bare-title>"
   ```
9. **Retroactive incidental ticket** (T-sync-on-close-not-dayend pattern): when the commit includes changes unrelated to the claimed ticket (the "oh, and I also fixed this" case), always draft a new ticket and immediately close it for the incidental fix — every change has a ticket.
10. **Slate**: `echo "- done: T-... — ..." >> ~/.TheIgors/claudecode/$(date +%Y%m%d).slate.txt`

### 5. Handle failure mid-batch

When a ticket fails (test failure, unresolvable conflict, scope mismatch), always prompt:
- **abort** — stop the batch, leave remaining tickets pending
- **skip** — mark this ticket blocked with reason, continue
- **rewind** — reset this ticket to pending, stop the batch, let Akien investigate

### 6. Shared teardown

Once all tickets complete (or the batch aborts):
1. Always run /savestateauto once for the whole batch (not per-ticket — that's just noise).
2. Print recap: N done, M skipped, P failed, ticket ids + commit hashes.

## Invariants

- Each ticket in the batch gets its own commit (no combined commits across tickets).
- Gated tickets are skipped, not unblocked by the batch — when the batch happens to ship a ticket that was gating another, the gate clears on the done action (via T-sync-on-close-not-dayend) and the formerly-gated one becomes eligible for the NEXT batch, not this one.
- Dependencies are always respected — no sprint starts before its prerequisites close.

## Flow integration

Right after /decided:
```
/decided <topic>
  → T-a, T-b, T-c filed (all share decision_id)
/sprint-batch decision:D-<topic-id>
  → ships all three in dep order
```

At start of day:
```
/context-load
/sprint-batch today-slate
  → sprint every unblocked slate item
```

## Hard rules

- Shared setup (venv activation + env var export) always runs once per batch — cheap, prevents per-ticket drift.
- Always run tests per-ticket with `pytest -x -q`; failure stops that ticket and prompts skip/abort.
- Always commit per ticket — load-bearing for decision-rollup, which needs per-ticket close events.
- Topo cycles always surface as a dependency-graph bug — bail with the cycle printed and get Akien's call.

## Related

- **/decided** — files tickets that this skill consumes.
- **/fixit** — (after T-fixit-rewrite) = /decided + /sprint-batch on the just-filed set.
- **T-sync-on-close-not-dayend** (gated) — handles the palace/GitHub/file echo on each close action.
- **T-decision-rollup-on-last-ticket-close** (gated) — when /sprint-batch closes the last ticket of a decision, the decision auto-rolls-up with outcome.
