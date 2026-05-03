---
name: savestateauto
description: Lightweight state flush — write in-flight hypothesis to slate, remove debug flag, emit compact preserve string.
model: haiku
---

# /savestateauto — Quick state flush (+ compact preserve string)

Called automatically by /ticket, /sprint, /day-close. Also callable directly.

Always emit the preserve string — that way Akien can /compact at any clean
boundary without a separate setup step.

## Steps

### 1. State hypothesis

Always write one sentence naming what's in-flight and why. Use `NONE` when
the session is clean — the slate must say something either way, and silence
is not interpretable.

### 2. Write in-flight to slate

Always append the hypothesis to today's slate so the next session reads it
on /context-load:
```bash
SLATE=~/.TheIgors/claudecode/$(date +%Y%m%d).slate.txt
echo "" >> "$SLATE"
echo "## In-flight: <hypothesis from step 1>" >> "$SLATE"
```

### 3. Remove debug flag
```bash
rm -f ~/.TheIgors/Igor-wild-0001/debug_session.flag
```

### 4. Emit compact preserve string

Always emit the preserve block at the end of /savestateauto output, even
when Akien didn't ask for /compact — preserving the option is cheap.

The preserve string is a **fixed generic pointer**. The slate holds all
state on disk (in-flight and next were written in Step 2); post-compact CC
resolves the rest by reading the slate.

Always emit this exact string — no per-session customization needed:
```
preserve: Read today's slate: ~/.TheIgors/claudecode/YYYYMMDD.slate.txt. In-flight and Next: see slate.
```

Print the block at the end of output, clearly labeled:
```
── COMPACT PRESERVE STRING (copy if you want to /compact now) ──
preserve: Read today's slate: ~/.TheIgors/claudecode/YYYYMMDD.slate.txt. In-flight and Next: see slate.
───────────────────────────────────────────────────────────────
```

Post-compact CC knows today's date from context and resolves YYYYMMDD itself.
No session ids, commit lists, ticket ids, or rule text — those all live on disk.

That's it. No compact (Akien triggers that), no DB writes, no session records.
