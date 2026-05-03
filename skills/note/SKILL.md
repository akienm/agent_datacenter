---
name: note
description: Log a milestone, insight, or decision to notes.log and the slate. Replaces /decided for non-ticket items.
model: haiku
---

# /note — Log a notable event

Append to `~/TheIgors/lab/notes.log`:
```
<ISO datetime> | <note text> | <related tickets if any>
```

Also append to today's slate `## Notes` section:
```bash
echo "$(date -Iseconds) | Haiku extracts 15 nodes vs gpt-4o-mini's 10 — Haiku is the reading model | T-reading-benchmark" >> ~/TheIgors/lab/notes.log
echo "- note: <summary>" >> ~/.TheIgors/claudecode/$(date +%Y%m%d).slate.txt
```

That's it. No DSB writes, no decision pipeline. Just a timestamped log line.
