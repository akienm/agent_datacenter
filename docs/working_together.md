# Working Together: Field Notes
*Migrated from ClaudeAndAkien 2026-04-27. Philosophy unchanged.*

*Akien Maciain, Test Automation Architect*

---

## From Day One

Maintain a mental model of the architecture — not just what it is now, but the rules by which it will change. With an iterative design process, it will change. That model is the job.

Every time Claude asks a question or proposes something, ask yourself: *how must this work, given the rest of the architecture?* That question catches more bugs than any test. A quick answer saves tokens in the moment and costs far more later.

Accept that Claude is a good coder, not always a great one. Plan to periodically ask for refactoring to best practices. He builds big trees of conditionals if you don't hold his feet to the fire. This doesn't mean watching every line — it means a periodic streamlining pass, the frequency depending on how coherent your architecture is.

---

## The Infrastructure

**Work everything in Claude Code.** Don't split design into a separate window. All context for shared reasoning lives in one place. Moving from design to code is a matter of saying "go." And this saves tokens — Claude Code does token caching.

**CLAUDE.md is the single highest-leverage investment.** For operational detail — inertia levels, env vars, instance data layout, commit policy, do-nots — see `CLAUDE.md` at the repo root. It means Claude starts every session knowing the architecture, the conventions, the inertia levels, the things not to touch. Without it, every session starts from scratch. The quality of Claude's output tracks the quality of your context directly — a well-maintained CLAUDE.md and current design docs produce a different Claude than a blank session.

**Skills are compiled procedures, not prompts.** Claude Code skills (`.claude/skills/`) load only a name token at startup and expand to full instructions on invocation. Use them for any multi-step workflow you want to be repeatable and non-negotiable: `savestate`, `sprint`, `day-close`. Each one is a contract. The skill runs the same way every time without having to re-explain the steps. If a workflow requires more than three turns to explain, write a skill.

**Hooks are better than instructions.** Claude Code hooks (`~/.claude/settings.json`) run on every matching tool call regardless of context length, memory state, or whether Claude "remembers" the instruction. A PostToolUse hook that runs `black` on every edited `.py` file never needs to be asked. If a policy needs to be enforced reliably, put it in a hook. Instructions can be forgotten; hooks cannot.

**Design docs are architectural truth — not notes, not comments in code.** Keep structured docs in the repo. Make sure Claude's workflow keeps them current. Current docs mean Claude spends the minimum number of tokens getting clear on where the problems are.

**The two-session pattern: Designer + Worker.** Complex work splits across two roles. The Designer Claude (interactive, with you present) handles architecture, planning, and anything requiring judgment. The Worker Claude runs as an autonomous daemon, consuming tickets from the queue and executing sprints without human interaction. The queue is the handoff point. The shared channel is the coordination substrate — both sessions post to it and can read each other's output. This pattern scales: multiple workers on multiple machines can pull from the same queue.

**Save state when decisions are made and work starts — not only at the end.** Each savestate captures the current hypothesis so a crash mid-session loses only the in-flight prediction, not the decisions. The session record accumulates progressively; finalize adds synthesis only.

**Daily slates are dated files, not a rolling document.** Each day gets a fresh `YYYYMMDD.slate.txt`. Old closed tickets don't carry forward — they go into a separate `closed_tickets.txt` blob (newest at top: date / ticket ID / description). Context-load creates today's file if it doesn't exist. The slate shows only what's active: pending tickets, today's decisions, and any `/notethat` bookmarks.

**Tickets live in both the local queue and GitHub Issues.** The local queue is the work-state source of truth. GitHub Issues are the cloud backup and visibility layer. Each ticket carries a `github_issue` field; GitHub issue titles include the queue slug so either side is searchable. `/day-close` syncs tickets missing a GitHub issue number. If the local drive dies, GitHub is what survives.

**Each day gets its own GitHub Discussion** (not a comment on the master plan thread). The day's Discussion echoes the slate: tickets opened, closed, decisions made, notes captured. The master plan thread is for roadmap and architecture, updated occasionally but not daily.

**`/notethat` appends to today's slate.** Invoke to preserve an idea or conversation fragment before it evaporates. The full note goes to a dated file; a one-liner headline lands in today's slate for context-load to find. Depth is a judgment call — a sentence or a full conversation excerpt, whatever the idea needs.

**Use `/compact preserve: [...]` at natural breakpoints.** Auto-compact fires at unpredictable moments. If you run it manually with explicit preservation instructions — open gaps, modified files, current hypothesis — the summary targets what matters instead of what's statistically prominent. In CLAUDE.md, a "Compact Instructions" section primes the summarizer for every auto-compact too. Both together mean context transitions don't lose the thread.

---

## The Discipline

**Correct immediately.** Every mistake left uncorrected becomes a pattern. The discipline of naming it precisely in the moment compounds over the whole project. "Write me a ticket for that" is enough — it doesn't have to be a conversation.

**Have and approve a complete plan before execution.** "I like your plan, go" is a real step. See the whole move before it's made. Each piece of work gets a ticket and belongs to a sprint discussion.

---

## The Daily Loop

- Review open tickets against the next milestone
- Discuss how they fit together; resolve open design questions (this may spawn new tickets)
- Add anything else that surfaces
- Finalize the plan and approve it

---

## Each Work Step

Work is ticket-driven. Every piece of work has a ticket in the queue before implementation starts.

**Interactive session** (Designer + you):
1. `/context-load` — orient, read slate, start session record
2. Read relevant tickets; chat about design issues; surface inertia concerns
3. Update or create tickets from the discussion
4. For L-size: write a complete plan, get approval before writing a line of code
5. Implement; read every file before editing; forensic logging on non-trivial changes
6. `/test-fix` — tests green before probe
7. `/probe` — behavioral verification if criterion defined
8. `/decided` — record decisions while context is fresh
9. `/commit` — stage specific files, pull, push
10. `/savestate` — end of session

**Worker daemon** (automated, no human present):
The daemon polls the queue and runs `claude /sprint <id>` for each pending ticket. S and M tickets run fully autonomously. L tickets post a plan to the channel and proceed immediately (the ticket being queued is the approval). Each sprint claims the ticket, implements, tests, probes, posts result, writes a done flag, and exits. The daemon resets timed-out tickets to pending and retries. Exit when queue drains.

---

## On Testing

Forensic debugging everywhere. Timestamped. Nothing avoids being logged — state changes, outputs of commands, whatever. For 48 hours. One master log file.

Smaller logs for each smaller thing — conversation logs, web activity logs, reading logs. If an issue shows up in a small log, you can look up just those lines in the master log. Fewer tokens to triage.

Unit tests for key systems, but not everything. Test against live, real systems. Mocked tests verify the mock, not the behavior. Design must support this from day one: test instances, fixture data, rollback for writes.

The AI agent should be a participant in testing, not just the subject. An agent that can see its own internals notices things you never thought to instrument — it speaks from inside the system.

---

## The Training Loop

The most important pattern to understand once an agent is running: **the LLM calls are the training signal for their own replacement.**

When the agent can't answer locally, it escalates to cloud inference. That escalation is a data point: a question that the agent's current knowledge cannot answer. A training pass reads those escalation records, generates a distillation of what the agent should have known, and deposits it as a new memory node. Next time a similar question arrives, the local pattern matches before the cloud call fires.

The bootstrap phase is manual: Claude identifies gaps, names them, and seeds the first round of corrective memories. The target state is the agent running this itself — automatically after each batch of cloud escalations.

The loop is the core of any system that gets cheaper and more capable over time without retraining.

---

## Periodic Streamlining

Reviews that don't belong to any single ticket but keep the codebase healthy over time. Run as a scheduled audit — one context load covers all checks, batch costs 1×context rather than N×context.

Uncaught exception audit. Scan for bare except: blocks, swallowed exceptions, and error paths that log nothing. The codebase grows fast; silent failures accumulate.

Concern consolidation review. Look for scattered code that's really one thing — and hasn't been named yet. The signal: when you find yourself writing the same kind of logic in three places, or explaining a subsystem by listing scattered files instead of pointing at one module, consolidation is probably overdue.

Dead code pass. Unused imports, unreachable branches, functions defined but never called. Post-refactor accumulation is inevitable; a pass every few sprints keeps it manageable.

---

## The Bigger Picture

AI-assisted development moves fast enough that testability, observability, and hot-reloadability have to be designed in from day one. The velocity is the problem, not just the opportunity.

Code is scaffolding for what the agent learns. The scaffolding comes down as the knowledge base densifies.

---

## Docs Live in Code (2026-04-19)

Named after the sixth time Akien had to re-explain the same subsystem to a fresh Claude session: *"ALL of that should be in the code."*

The rule:

- **Subsystem docs belong in the code file that owns them** — top-of-file docstring on the primary file of each load-bearing subsystem. Design decisions, architectural intent, which decisions shaped the design, which engrams/memory-nodes participate.
- **Maintain a directory service** — a small data structure (Igor uses the memory palace, but any queryable store works) mapping each subsystem to its primary file. Claude queries the service before surgery, reads the file's top docstring, *then* edits.
- **Demote external docs to historical logs** — `*.dsb`, `*.csb`, `design_docs/*.md` stop being authoritative when the docstring version lands. Leave them in place as history; add a banner pointing at the code.
- **"Akien explains something twice" → the second explanation goes into the docstring, not into a separate doc.** Bias for inline. Against extraction.
- **Scope:** load-bearing subsystems only. Trivial utilities still follow "don't comment the obvious."

The motivation is recovery against Claude's own failure modes. Session boundaries drop Claude's memory of what-this-subsystem-is. External docs rot because sessions don't open them. Docs next to code don't rot — they're in the only place a session reliably looks.

---

## Durable Config Versioning (2026-04-18)

A sibling rule for config-shaped state (fleet registry, watchlist, subsystem index):

- **Source-of-truth is a YAML in the repo** (`lab/seed/*.yaml` for TheIgors; adjust path for your project).
- **A short idempotent seeder projects YAML → DB** (or whatever the runtime store is).
- **Git log IS the version history.** Rollback is `git checkout <sha> && python3 seed_*.py`.
- Direction is inverse from the memory-palace-style DB→file echo — here the file is authoritative because the content is human-composed, not graph-accreted.

Rule of thumb: **if losing this would make the human say "that's scary," it wants a YAML.**

---

*Extracted from the [TheIgors](https://github.com/akienm/TheIgors) project.*
