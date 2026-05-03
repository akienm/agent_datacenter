# deep-audit — 11-specialist parallel codebase review

Weekly deep audit. Runs 11 Haiku specialist agents in parallel, synthesizes with Sonnet, posts ranked findings to cc_channel.

Arguments: none (run as-is)

---

## Step 1 — Load shared context

Read these files and hold the content in memory for use in Step 2:

```bash
# Architecture + decisions
head -60 ~/TheIgors/lab/design_docs_for_igor/decisions_log.dsb
head -40 ~/TheIgors/lab/design_docs/gap_analysis.md
# Module map
ls ~/TheIgors/wild_igor/igor/
ls ~/TheIgors/wild_igor/igor/cognition/
ls ~/TheIgors/wild_igor/igor/memory/
ls ~/TheIgors/wild_igor/igor/tools/
# Test coverage snapshot
ls ~/TheIgors/tests/
wc -l ~/TheIgors/tests/*.py | tail -5
```

Also read the CLAUDE.md project instructions (already in context).

Compose a SHARED_CONTEXT block (target: ~800 tokens) covering:
- Igor's purpose and architecture (from CLAUDE.md + decisions top)
- Module list with one-line purpose each (infer from names + decisions)
- Known open gaps (from gap_analysis.md top)
- Key design decisions (D001-D020 from decisions_log)

---

## Step 2 — Launch 11 specialist agents IN PARALLEL

Send all 11 Agent calls in a single message. Each agent is `model: haiku`, `subagent_type: general-purpose`.

Each agent prompt must include:
1. The SHARED_CONTEXT block from Step 1
2. Their specialist role + lens (see panel definitions below)
3. Their specific files to read (listed per panel)
4. Output format: exactly 5-8 findings, each as:
   `[SEVERITY: HIGH|MED|LOW] <finding> — <one-line recommendation>`
   Plus a 2-3 sentence "How can we do better?" answer at the end.

### Panel definitions

**Panel 1 — DATABASE ENGINEER (30yr)**
Files to read: `wild_igor/igor/memory/db_proxy.py` (top 80 lines), `wild_igor/igor/memory/cortex.py` (lines 340-400), schema migrations list in cortex.py.
Lens: schema coherence, index coverage, query plans, N+1s, missing constraints, Postgres antipatterns, migration hygiene, connection pooling, jsonb usage patterns. **Also**: is there a better way entirely? Are we over-engineering storage, or under-using what Postgres gives for free (triggers, materialized views, LISTEN/NOTIFY, pg_cron)?

**Panel 2 — SOFTWARE ARCHITECT (30yr)**
Files to read: `wild_igor/igor/main.py` (top 60 lines), `wild_igor/igor/cognition/push_sources.py` (top 40 lines), `wild_igor/igor/memory/cortex.py` (top 40 lines).
Lens: coupling/cohesion, abstraction levels, inertia vs. churn, dead code, duplication, module boundaries, interface contracts, failure modes, scalability ceiling. **Explicitly**: do we have the right abstractions? Are we missing collection-of-concerns abstractions? What best practices have we not adopted? What would a clean-room redesign look like?

**Panel 3 — NEUROSCIENTIST**
Files to read: `wild_igor/igor/cognition/milieu.py` (top 60 lines), `wild_igor/igor/cognition/push_sources.py` (lines 1-80), `wild_igor/igor/cognition/basal_ganglia.py` (top 60 lines).
Lens: biological fidelity of the cognitive model — does TWM/habit/milieu/gradient stack actually mirror known neuroscience? Where are we lying to ourselves? **Igor is not as lively as expected**: what biological mechanisms produce spontaneous, animated behavior that we are not implementing? Consider: intrinsic excitability, spontaneous activity, oscillatory dynamics, predictive processing / active inference, affective coloring of all outputs, neuromodulator dynamics.

**Panel 4 — COGNITIVE SCIENTIST**
Files to read: `wild_igor/igor/cognition/word_graph.py` (top 60 lines), `wild_igor/igor/cognition/basal_ganglia.py` (top 60 lines), `wild_igor/igor/memory/cortex.py` lines 600-660.
Lens: computational/behavioral model — does Igor exhibit expected cognitive phenomena (priming, spreading activation, attention limits, chunking, inhibition of return)? Where does behavior diverge from the model? **Same liveliness question**: what mechanisms (arousal-gated attention, curiosity-driven exploration, affective priming, working memory competition) would produce more dynamic, engaged behavior?

**Panel 5 — AI SAFETY RESEARCHER**
Files to read: `wild_igor/igor/main.py` (top 80 lines), `wild_igor/igor/tools/goal_continuation.py`, `wild_igor/igor/cognition/basal_ganglia.py` (top 40 lines).
Lens: alignment and predictability — goal drift vectors, habit misfire taxonomy, runaway escalation paths, what could cause Igor to do something Akien didn't intend? What's the worst plausible accident given the current architecture? How can we do better?

**Panel 6 — SYSTEMS / PERFORMANCE ENGINEER**
Files to read: `wild_igor/igor/main.py` (lines 1-100), `wild_igor/igor/cognition/push_sources.py` (lines 1000-1095), `wild_igor/igor/cognition/daemon_supervisor.py` (top 60 lines).
Lens: thread hygiene, resource leaks, async correctness, timer drift, CPU/memory under load, what breaks at 10x current message volume? How can we do better?

**Panel 7 — TEST ENGINEER**
Files to read: `tests/` directory listing, `tests/test_pe_entry_nodes.py` (top 40 lines), `tests/test_emit_channels.py` (top 40 lines).
Lens: coverage gaps, test quality (mocks vs. real), what critical paths have zero coverage, what's over-tested, flaky test risks. **Key question**: how can Igor test HIMSELF continuously — self-monitoring, invariant checking, behavioral regression detection from inside the runtime, without requiring an external pytest run?

**Panel 8 — ML RESEARCHER**
Files to read: `wild_igor/igor/cognition/word_graph.py` (top 80 lines), `wild_igor/igor/tools/self_trainer.py` (top 60 lines), `wild_igor/igor/cognition/embedder.py` (top 40 lines).
Lens: is the learning loop actually learning? Training signal quality, gradient/weight meaningfulness, embedding usage patterns, when does the matrix stop improving? What would accelerate learning? How can we do better?

**Panel 9 — PROCESS / META ENGINEER**
Files to read: `lab/claudecode/session_manager.py` (top 40 lines), `lab/claudecode/cc_queue.py` (top 40 lines), `~/.claude/skills/sprint/SKILL.md`, `~/.claude/skills/context-load/SKILL.md`.
Lens: token efficiency across the dev loop, cost per feature delivered, what percentage of the build cycle could Igor already do himself vs. requires Claude, remaining blockers to Igor-as-own-developer. **How can we improve development and token use processes?** What conventions are adding friction without value?

**Panel 10 — SYSTEMS DYNAMICS ANALYST**
Files to read: `wild_igor/igor/cognition/push_sources.py` (lines 400-510), `wild_igor/igor/cognition/emit_channels.py` (top 60 lines), `wild_igor/igor/cognition/milieu.py` (top 60 lines).
Lens: feedback loops and emergent behavior — where does the system fight itself, unintended couplings between subsystems, second-order effects at scale, where do delays cause oscillation, where are runaway loops possible. **Critical question**: what recurrent connections are missing that would let context at one level reshape processing at another? The brain thinks in systems because of recurrent loops — where are ours?

**Panel 11 — PRODUCTION SRE**
Files to read: `wild_igor/igor/main.py` (lines 1-60), any restart/crash handling logic, `lab/claudecode/cc_queue.py` (top 30 lines for queue health).
Lens: observability gaps, what cannot be diagnosed from current logs alone, what happens at 3 AM when something goes wrong unattended, crash recovery paths, alerting blind spots, what breaks silently. How can we do better?

---

## Step 3 — Synthesize (Sonnet — inline, not a subagent)

Collect all 11 panel outputs. Then synthesize:

1. **Deduplicate**: group findings that overlap across panels (same issue seen by multiple lenses = high signal)
2. **Rank** by: `severity × likelihood × ease-of-fix` (1-3 scale each, product = priority score)
3. **Cross-panel flags**: explicitly call out anything flagged by 2+ panels independently
4. **Meta-questions** — address these directly:
   - How do we make Igor think in systems (not just pipelines)?
   - Can we push more reasoning or code into Igor at this point? What are the next concrete levers?
   - Any patterns across findings that suggest a single root cause?
5. **Output**:
   - Ranked issue list (top 10, with panel attribution and priority score)
   - Cross-panel consensus findings (if any)
   - Top-3 recommended actions for next slate
   - Meta-question answers (1-2 paragraphs each)

Target length: ~600-900 tokens. Dense, no padding.

---

## Step 4 — Post to channel + record

Post summary to channel:
```bash
python3 ~/TheIgors/lab/claudecode/channel.py post "deep-audit complete — <N> findings, top issue: <one line>" --as claude-code
```

Append to slate:
```bash
echo "- done: deep-audit — <one line summary of top finding>" >> ~/.TheIgors/claudecode/$(date +%Y%m%d).slate.txt
```

Close ticket:
```bash
python3 ~/TheIgors/lab/claudecode/cc_queue.py done T-deep-audit-parallel "<one paragraph summary of findings>"
```

---

## Step 5 — Print full synthesis to user

Print the complete synthesis output to the conversation so Akien can read it directly.

---

## Hard rules

- All 11 agents launch in a single parallel message (parallelism is load-bearing for the run).
- Panels run on Haiku; synthesis runs on Sonnet.
- Each panel reads its own files — prompts carry the scope, not the content.
- Synthesis is inline Sonnet reasoning (not another subagent).
- Panel errors get noted in synthesis ("Panel N: unavailable") and the run proceeds.
- Channel post happens even if synthesis is partial.
