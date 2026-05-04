---
name: sprint
description: Claim a ticket, work it, commit, close it. Args: "last", ticket ID, or empty (next in queue).
model: sonnet
---

# /sprint — Claim, work, ship

## Args
- `/sprint last` — sprint the thing just discussed (must be ticketed)
- `/sprint T-xxx` — sprint a specific ticket
- `/sprint` — pick next pending ticket from queue

## Steps

### 1. Select ticket
```bash
python3 ~/TheIgors/lab/claudecode/cc_queue.py list 2>/dev/null | grep "⚪\|🟡"
```
No args: highest-priority pending. `last`: most recently discussed ticket.

Always sprint from a ticket. When no ticket exists yet, stop here and run
/ticket first — a sprint without a ticket has no place to report done.

### 2. Claim ticket
```bash
python3 ~/TheIgors/lab/claudecode/cc_queue.py claim <id>
```
Always claim before working — the claim marks the ticket in-progress so the
queue and slate reflect active work. Then add the ticket ID to today's slate
under `## Planned` or `## Ad hoc`.

### 3. Select executor
- **CC inline**: default for code changes in this repo
- **Haiku subagent**: mechanical/checklist work (use the Agent tool, subagent_type=general-purpose with a Haiku model override)
- **Igor**: delegate via `mcp__igor__cc_send` for Igor-domain work (cognition debugging, memory curation, palace edits)

### 4. Review the plan
First, state the plan in one to three sentences: what files will change, what tests will cover it, what the scope boundary is.

Check inertia before touching anything — the authoritative list lives at
`theigors/rules/safeguards` in the palace. Read it via:
```
memory_get(path="theigors/rules/safeguards")
```
When the plan touches a HIGH-inertia file, always pause and surface it to
Akien for inline pre-approval before coding. Stamp the approval into the
ticket body so it survives compaction.

### 4.5. Infrastructure brief (D-scaffold-not-correct-2026-04-21)
After the inertia check, surface a one-screen infrastructure brief for the
touched areas (MCP tools, proxies, base classes, IMAP buses, channels).
This catches the "Sonnet forgot MCP exists" failure mode before the first
edit rather than after.

```bash
python3 ~/TheIgors/lab/claudecode/sprint_infrastructure_brief.py \
  <file1> <file2> ...
```

The output is positive scaffolding — read it and ask: "does my plan use the
preferred forms listed here?" If the plan proposes a deprecated form (raw
psql, channel.py direct write, print()), amend before coding. Also run
`/audit-precode` on the plan text before step 5.

### 5. Pull + work
First, pull to get a clean base:
```bash
git pull --rebase origin main
```
If the working tree is dirty, stash first (`git stash -u`), pull, then pop.

Then write the change. Code first, tests alongside (integration tests hit
real Postgres per `theigors/rules/database` — no mocks), docstrings on
load-bearing files per `theigors/rules/docs-live-in-code`.

### 6. Cleanup (REQUIRED)
Always review the diff before staging:
```bash
git diff --stat && git diff
```
Every file in the diff exists on purpose. Remove: debug prints,
commented-out code, unused imports, replaced functions, single-use helpers
(inline them), temp files. A clean diff is the signal that the sprint is
ready to ship.

### 7. Test
Always run tests before commit:
```bash
cd ~/TheIgors && source venv/bin/activate && python -m pytest tests/ -x -q 2>&1 | tail -20
```
A green run is the signal to stage. A red run means fix the failure first —
never commit-and-see.

### 7.5. Teach Igor — palace deposit (default skip)

Per theigors/rules/capability-protocol (workflow consumer side): when a
sprint surfaces novel design reasoning, this is the moment to deposit it
into Igor's palace so future-Igor (and future-CC) can reach for it.

Ask: "**What from this sprint would I deposit into Igor's palace?**"

**Default answer: skip.** Most sprint work is mechanical — ticket said do
X, did X, tested, shipped. Those produce no novel reasoning and shouldn't
pollute the palace. This step exists to catch the rarer cases where a
*non-obvious why* emerged.

When to deposit:
- A design choice with a non-obvious WHY (ticket text didn't anticipate it)
- A refactor that surfaced a hidden invariant
- A workaround whose mechanism the next reader needs to understand
- A bug fix whose ROOT was different from the reported symptom

When to skip:
- The change matched the ticket plan exactly
- The reasoning is fully captured in code + commit message already
- The work was mechanical (rename, format, dependency bump)

When non-skip, propose 0–N palace nodes (path + title + content), surface
the proposal to Akien inline for review, then write after approval:
```bash
psql postgresql://igor:choose_a_password@127.0.0.1/Igor-wild-0001 -c \
  "INSERT INTO memory_palace (path, title, content, memory_type)
   VALUES ('theigors/...', 'short title', 'reasoning...', 'PROCEDURAL')"
```

This is the workflow consumer side of theigors/rules/capability-protocol —
closes the lapsed practice "teach Igor as you implement tickets" by making
the prompt mandatory at the moment where novel reasoning is freshest.

### 8. Commit + push
Always stage files specifically by name (not `git add -A` / `git add .`) —
that keeps `.env`, `*.db`, and runtime paths under `~/.TheIgors/` out of
the commit by default.
```bash
git add <specific files>
git commit -m "$(cat <<'EOF'
feat/fix/docs: description

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git pull --rebase origin main && git push origin main
```
Always let pre-commit hooks run — they catch issues before they ship.
Push non-force to main; force-push overwrites shared history and is only
used with explicit instruction.

### 9. Close ticket
Always close with a one-line summary of what actually shipped — this line
feeds decision-rollup, the session record, and today's slate:
```bash
python3 ~/TheIgors/lab/claudecode/cc_queue.py done <id> "what was built"
echo "- done: <id> — <summary>" >> ~/.TheIgors/claudecode/$(date +%Y%m%d).slate.txt
```

### 10. /savestateauto
Always run /savestateauto at sprint end — it flushes session state, appends
the change to the session record, and emits a compact-ready preserve
string. That's what makes sprint work visible to the next session.

## Hard rules
- Always sprint from a ticket — run /ticket first when one doesn't exist.
- Cleanup (step 6) is the last pre-commit act of every sprint — the debris review is load-bearing, not optional.
- Always let pre-commit hooks run; always push non-force to main.
- Always stage files by name. Runtime state (`.env`, `*.db`, paths under `~/.TheIgors/`) lives outside the tree; name-staging keeps it there.
- When tests pass and no secrets are in the diff, commit proceeds without asking for permission.
