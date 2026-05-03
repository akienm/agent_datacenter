---
name: savestate
description: End-of-session — runs /savestateauto then triggers /compact with preserve string.
model: haiku
---

# /savestate — Full session close

## Steps

1. **Run /savestateauto** (flushes all in-flight state)

2. **Compose preserve string** (write fresh, don't copy-paste):
   ```
   preserve: session=YYYY-MM-DDx finalized. Done: <2-3 line summary>.
   Next: <top priority>. In-flight: <hypothesis or NONE>.
   ```

3. **Inject compaction**:
   If `CLAUDE_TMUX_SESSION` is set: call `mcp__igor__request_compaction` with the preserve string.
   Otherwise: output the preserve string for manual `/compact`.
