#!/usr/bin/env python3
"""
cc_queue.py — Designer/Worker Claude task queue manager.

Canonical storage: clan.memories where parent_id='TICKETS_ROOT' (FACTUAL rows,
metadata.kind='ticket').

Log file:  ~/.TheIgors/cc_channel/log.jsonl

Usage:
    cc_queue.py list                          — show tasks (pending first, gated hidden)
    cc_queue.py list --gated                  — include gated tickets in the list
    cc_queue.py list --by-decision            — group output by decision_id
    cc_queue.py add <json-file>               — add task from JSON file
    cc_queue.py claim <id>                    — mark task in_progress
    cc_queue.py done <id> <msg>               — mark task completed with result
    cc_queue.py block <id> <msg>              — mark task blocked with reason
    cc_queue.py show <id>                     — show full task detail
    cc_queue.py log <msg>                     — append a free-form log entry
    cc_queue.py flush_decision <id> <summary> — flush decision to Igor memory
    cc_queue.py flush_session <session> <summary> — flush session blob to Igor memory
    cc_queue.py worker-launch                     — ensure worker daemon is running (spawns konsole if not)
    cc_queue.py reset <id>                        — reset one ticket from in_progress → pending (retry after timeout)
    cc_queue.py reset-stale                       — reset all in_progress tickets → pending (daemon startup cleanup)
    cc_queue.py set-worker <worker> <id> [<id>]  — assign worker (igor|claude) to ticket(s)
    cc_queue.py needs-review <id>                — mark ticket needs_review (Igor self-coding review gate)
    cc_queue.py gate <id> <reason>               — gate a ticket behind a precondition (hides from default list)
    cc_queue.py ungate <id> [note]               — clear a ticket's gate
    cc_queue.py set-decision <id> <decision-id>  — attach a decision id to a ticket
"""

import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone

IGOR_FLUSH_URL = "https://localhost:8080/api/cc_send"

TICKETS_ROOT_ID = "TICKETS_ROOT"


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


LOG_PATH = os.path.expanduser("~/.TheIgors/cc_channel/log.jsonl")
CLOSED_TICKETS_PATH = os.path.expanduser("~/.TheIgors/claudecode/closed_tickets.txt")
STATUS_ORDER = {
    "pending": 0,
    "in_progress": 1,
    "needs_review": 2,
    "awaiting_approval": 3,
    "blocked": 4,
    "done": 5,
}


def _db_conn():
    """Connect to clan.memories storage."""
    import psycopg2

    return psycopg2.connect(
        os.environ.get(
            "IGOR_HOME_DB_URL",
            "postgresql://igor:choose_a_password@127.0.0.1/Igor-wild-0001",
        )
    )


def _narrative_for(t: dict) -> str:
    """Narrative = title + description (both GIN-searchable)."""
    title = (t.get("title") or "").strip()
    desc = (t.get("description") or t.get("body") or "").strip()
    return f"{title}\n\n{desc}" if desc else title


def _load():
    """Canonical read: SELECT from clan.memories. Returns list of ticket dicts."""
    conn = _db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT metadata FROM clan.memories WHERE parent_id = %s",
            (TICKETS_ROOT_ID,),
        )
        tasks = []
        for (md,) in cur.fetchall():
            if not md:
                continue
            t = dict(md)
            t.pop("kind", None)
            tasks.append(t)
        return tasks
    finally:
        conn.close()


def _save(tasks):
    """Canonical write: UPSERT each ticket to clan.memories."""
    conn = _db_conn()
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        for t in tasks:
            if not t.get("id"):
                continue
            metadata = dict(t)
            metadata["kind"] = "ticket"
            cur.execute(
                """
                INSERT INTO clan.memories
                  (id, narrative, memory_type, parent_id, metadata, timestamp,
                   source, scope, confidence, updated_at)
                VALUES (%s, %s, 'FACTUAL', %s, %s::jsonb, %s, 'cc_queue',
                        'class', 1.0, %s)
                ON CONFLICT (id) DO UPDATE SET
                  narrative = EXCLUDED.narrative,
                  metadata = EXCLUDED.metadata,
                  updated_at = EXCLUDED.updated_at
                """,
                (
                    t["id"],
                    _narrative_for(t),
                    TICKETS_ROOT_ID,
                    json.dumps(metadata),
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ── Public API ────────────────────────────────────────────────────────────


def load_tasks() -> list[dict]:
    """Load all tickets from canonical Postgres."""
    return _load()


def save_tasks(tasks: list[dict]) -> None:
    """Save tickets via canonical Postgres UPSERT."""
    _save(tasks)


def _log(entry: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _prepend_closed_ticket(tid: str, title: str) -> None:
    """Prepend one line to closed_tickets.txt (newest at top)."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = f"{date_str} | {tid} | {title}\n"
    os.makedirs(os.path.dirname(CLOSED_TICKETS_PATH), exist_ok=True)
    existing = ""
    if os.path.exists(CLOSED_TICKETS_PATH):
        with open(CLOSED_TICKETS_PATH) as f:
            existing = f.read()
    with open(CLOSED_TICKETS_PATH, "w") as f:
        f.write(line + existing)


def _find(tasks, tid):
    for t in tasks:
        if t["id"] == tid:
            return t
    return None


def _format_task_line(t: dict) -> str:
    STATUS_ICON = {
        "pending": "⬜",
        "in_progress": "🔵",
        "needs_review": "🟡",
        "awaiting_approval": "🟠",
        "blocked": "🔴",
        "done": "✅",
    }
    icon = STATUS_ICON.get(t["status"], "?")
    size = t.get("size", "?")
    epic = f" #{t['epic']}" if t.get("epic") else ""
    worker_tag = " [igor]" if t.get("worker") == "igor" else ""
    gh_tag = f" GH#{t['github_issue']}" if t.get("github_issue") else ""
    return f"  {icon} [{t['id']}] ({size}){epic}{worker_tag}{gh_tag} {t['title']}  [{t['status']}]"


def _print_task(t: dict) -> None:
    print(_format_task_line(t))
    if t["status"] == "blocked" and t.get("result"):
        print(f"       BLOCKED: {t['result']}")
    if t["status"] == "done" and t.get("result"):
        print(f"       done: {t['result']}")


def cmd_list(args):
    by_epic = "--by-epic" in args
    show_gated = "--gated" in args
    by_decision = "--by-decision" in args
    tasks = _load()
    if not tasks:
        print("Queue empty.")
        return

    if not show_gated:
        tasks = [t for t in tasks if not t.get("gate")]

    def _priority_int(t):
        p = t.get("priority", 99)
        try:
            return int(str(p).lstrip("pP"))
        except (ValueError, TypeError):
            return 99

    tasks_sorted = sorted(
        tasks, key=lambda t: (STATUS_ORDER.get(t["status"], 9), _priority_int(t))
    )

    if by_epic:
        from collections import defaultdict

        groups: dict[str, list] = defaultdict(list)
        for t in tasks_sorted:
            groups[t.get("epic") or "(no epic)"].append(t)
        for epic_name in sorted(groups):
            print(f"\n## #{epic_name}")
            for t in groups[epic_name]:
                _print_task(t)
    elif by_decision:
        from collections import defaultdict

        groups: dict[str, list] = defaultdict(list)
        for t in tasks_sorted:
            groups[t.get("decision_id") or "(no decision)"].append(t)
        for decision in sorted(groups):
            print(f"\n## {decision}")
            for t in groups[decision]:
                _print_task(t)
    else:
        for t in tasks_sorted:
            _print_task(t)


def cmd_show(args):
    if not args:
        print("Usage: show <id>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    print(json.dumps(t, indent=2))


def cmd_claim(args):
    # --as <worker> selects the claiming worker. Default 'igor' preserves
    # the cert_worker_freeze design (pe_chain claims without the flag stay
    # gated to worker=igor tickets). CC manual claims pass --as claude.
    as_worker = "igor"
    if "--as" in args:
        i = args.index("--as")
        if i + 1 >= len(args):
            print("Usage: claim <id> [--as <worker>]")
            sys.exit(1)
        as_worker = args[i + 1]
        args = args[:i] + args[i + 2 :]
    if not args:
        print("Usage: claim <id> [--as <worker>]")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    if t["status"] != "pending" or (t.get("worker") and t.get("worker") != as_worker):
        print(
            f"Task {args[0]} is {t['status']} or worker mismatch "
            f"(ticket worker={t.get('worker')!r}, claiming as={as_worker!r})."
        )
        sys.exit(1)
    t["status"] = "in_progress"
    t["claimed_at"] = _now()
    _save(tasks)
    _log({"action": "claim", "id": args[0], "title": t["title"], "as": as_worker})
    print(f"Claimed {args[0]} as {as_worker}: {t['title']}")


def _close_igor_goal(ticket_id: str) -> None:
    """Close Igor's GOAL memory for a ticket so pe_chain stops re-firing."""
    try:
        import psycopg2

        db_url = os.environ.get(
            "IGOR_HOME_DB_URL",
            "postgresql://igor:choose_a_password@127.0.0.1/Igor-wild-0001",
        )
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "UPDATE memories SET narrative = REPLACE(narrative, 'ACTIVE GOAL', 'CLOSED GOAL') "
            "WHERE memory_type='GOAL' AND narrative ILIKE %s AND narrative ILIKE '%%ACTIVE GOAL%%'",
            (f"%{ticket_id}%",),
        )
        closed = cur.rowcount
        conn.close()
        if closed:
            print(f"Closed {closed} GOAL(s) for {ticket_id}")
    except Exception as e:
        print(f"GOAL close failed (non-fatal): {e}")


def _decision_rollup(tasks: list, decision_id: str) -> None:
    """T-decision-rollup-on-last-ticket-close: when the last ticket of a decision
    closes, write a rollup doc + un-gate dependents referencing this decision.

    Preserves any pre-existing narrative. If the decision doc already exists
    with narrative content (i.e. doesn't start with the rollup header), the
    rollup block is APPENDED as a `## Rollup` section and the frontmatter
    `status: open` is flipped to `status: closed`. If the file is absent or
    already rollup-stub-shaped, the stub form is (re)written.

    Rollup location: lab/design_docs/decisions/<decision-id>.md (file-stub until
    T-decisions-into-palace-subtree moves this into the palace).
    """
    if not decision_id:
        return
    siblings = [t for t in tasks if t.get("decision_id") == decision_id]
    if not siblings:
        return
    open_count = sum(
        1 for t in siblings if t.get("status") not in ("done", "discarded", "blocked")
    )
    if open_count > 0:
        return

    # All tickets in this decision are closed. Roll up.
    from pathlib import Path
    import os as _os

    rollup_dir = Path(_os.path.expanduser("~/TheIgors/lab/design_docs/decisions"))
    rollup_dir.mkdir(parents=True, exist_ok=True)
    rollup_path = rollup_dir / f"{decision_id}.md"
    now = _now()
    closed_tickets = sorted(siblings, key=lambda t: t.get("completed_at") or "")

    rollup_lines = [
        f"**Closed at:** {now}",
        f"**Ticket count:** {len(siblings)} (all closed)",
        "",
        "### Shipped via",
    ]
    for t in closed_tickets:
        rollup_lines.append(
            f"- {t['id']} ({t.get('size', '?')}) — {t.get('title', '?')}  "
            f"`{t.get('status')}` — {(t.get('result') or '')[:200]}"
        )
    rollup_lines.append("")
    rollup_lines.append(
        "_Generated by cc_queue.py _decision_rollup. File-stub until "
        "T-decisions-into-palace-subtree moves rollups into the memory palace._"
    )
    rollup_block = "\n".join(rollup_lines)

    existing = rollup_path.read_text() if rollup_path.exists() else ""
    has_narrative = bool(existing) and not existing.lstrip().startswith(
        "# Decision rollup —"
    )

    if has_narrative:
        preserved = existing
        if "\nstatus: open" in preserved:
            preserved = preserved.replace("\nstatus: open", "\nstatus: closed", 1)
        final = preserved.rstrip() + "\n\n## Rollup\n\n" + rollup_block + "\n"
    else:
        final = f"# Decision rollup — {decision_id}\n\n" + rollup_block + "\n"

    rollup_path.write_text(final)
    shape = "narrative+rollup" if has_narrative else "stub"
    print(
        f"  [rollup] {decision_id} closed — {len(siblings)} tickets "
        f"({shape}). → {rollup_path}"
    )

    # Un-gate dependents whose gate text mentions this decision
    ungated = 0
    for t in tasks:
        gate = t.get("gate") or ""
        if not gate:
            continue
        if decision_id in gate:
            prev = t["gate"]
            t["gate"] = None
            ungated += 1
            print(f"  [rollup] ungated {t['id']} (was: {prev[:60]}...)")
    if ungated:
        _log(
            {
                "action": "decision_rollup_ungate",
                "decision_id": decision_id,
                "ungated_count": ungated,
            }
        )


def _append_to_todays_slate(ticket: dict) -> None:
    """T-sync-on-close-not-dayend: append closed ticket to today's slate
    ## Done today section. Idempotent (skips if ticket id already there).
    Graceful degrade: silent on missing slate or read/write failure.
    """
    try:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        slate_path = os.path.expanduser(f"~/.TheIgors/claudecode/{today}.slate.txt")
        if not os.path.exists(slate_path):
            return
        with open(slate_path) as f:
            content = f.read()
        tid = ticket["id"]
        title = ticket.get("title", "")
        result = (ticket.get("result") or "").split("\n")[0][:120]
        entry = f"- {tid} — {title}"
        if result:
            entry += f" ({result})"
        lines = content.splitlines(keepends=True)
        out = []
        appended = False
        in_done = False
        for i, line in enumerate(lines):
            # Skip idempotency: if ticket already present in "## Done today"
            if in_done and tid in line and line.lstrip().startswith("-"):
                appended = True  # treat as already-done
                out.append(line)
                continue
            out.append(line)
            if line.startswith("## Done"):
                in_done = True
                continue
            if in_done and line.startswith("## ") and not appended:
                out.insert(len(out) - 1, entry + "\n")
                appended = True
                in_done = False
        if in_done and not appended:
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            out.append(entry + "\n")
            appended = True
        if appended:
            with open(slate_path, "w") as f:
                f.writelines(out)
    except Exception as e:
        _log({"action": "slate_append_failed", "error": str(e), "id": ticket.get("id")})


def _ungate_dependents(tasks: list, closed_id: str) -> int:
    """Clear `gate` on any pending task whose gate text references closed_id.

    Returns count of tickets ungated. Operates in-place; caller must _save.
    Mirrors the decision-rollup ungate pattern at the ticket-id level so
    gated chains (e.g. T-cc-walk-02 gated on T-cc-walk-01) flow on close.
    """
    ungated = 0
    for t in tasks:
        if t.get("status") != "pending":
            continue
        gate = t.get("gate") or ""
        if not gate:
            continue
        if closed_id in gate:
            t["gate"] = None
            ungated += 1
            print(f"  [ungate] {t['id']} (was gated on {closed_id})")
    if ungated:
        _log(
            {
                "action": "ungate_on_close",
                "closed_id": closed_id,
                "ungated_count": ungated,
            }
        )
    return ungated


def cmd_done(args):
    if len(args) < 2:
        print("Usage: done <id> <result-message>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    t["status"] = "done"
    t["result"] = args[1]
    t["completed_at"] = _now()
    decision_id = t.get("decision_id")
    _decision_rollup(tasks, decision_id)
    _ungate_dependents(tasks, t["id"])
    _save(tasks)
    _log({"action": "done", "id": args[0], "title": t["title"], "result": args[1]})
    _prepend_closed_ticket(args[0], t["title"])
    _close_igor_goal(args[0])
    _append_to_todays_slate(t)
    print(f"Completed {args[0]}: {t['title']}")


def cmd_block(args):
    if len(args) < 2:
        print("Usage: block <id> <reason>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    t["status"] = "blocked"
    t["result"] = args[1]
    t["blocked_at"] = _now()
    _save(tasks)
    _log({"action": "blocked", "id": args[0], "title": t["title"], "reason": args[1]})
    _close_igor_goal(args[0])
    print(f"Blocked {args[0]}: {args[1]}")


def cmd_propose(args):
    """D331: Igor proposes a design change for approval. Sets status=awaiting_approval."""
    if len(args) < 2:
        print("Usage: propose <id> <proposal text>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    proposal = " ".join(args[1:])
    t["status"] = "awaiting_approval"
    t["proposal"] = proposal
    t["proposed_at"] = _now()
    _save(tasks)
    _log(
        {
            "action": "propose",
            "id": args[0],
            "title": t["title"],
            "proposal": proposal[:200],
        }
    )
    print(f"Proposed {args[0]}: {proposal[:120]}")
    print(f"Status: awaiting_approval — CC will review on next context-load")


def cmd_approve(args):
    """D331: Approve a pending proposal. Resets ticket to pending with approved plan."""
    if not args:
        print("Usage: approve <id> [approval notes]")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    if t["status"] != "awaiting_approval":
        print(f"Task {args[0]} is {t['status']}, not awaiting_approval.")
        sys.exit(1)
    notes = " ".join(args[1:]) if len(args) > 1 else ""
    t["status"] = "pending"
    t["approved_plan"] = t.get("proposal", "")
    t["approval_notes"] = notes
    t["approved_at"] = _now()
    t["blocked_at"] = None  # Clear any prior block
    _save(tasks)
    _log(
        {"action": "approve", "id": args[0], "title": t["title"], "notes": notes[:200]}
    )
    print(f"Approved {args[0]}: {t['title']}")
    if notes:
        print(f"Notes: {notes}")

    # D333: notify Igor so he re-adopts without waiting 30min PROC_QUEUE_DRAIN
    try:
        import urllib.request

        cc_send_url = os.environ.get("CC_SEND_URL", "http://localhost:8080/api/cc_send")
        msg = (
            f"[APPROVED] {args[0]} approved by CC. "
            f"adopt top ticket. {f'Notes: {notes[:100]}' if notes else ''}"
        )
        req = urllib.request.Request(
            cc_send_url,
            data=json.dumps({"content": msg}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        print("Notified Igor via cc_send")
    except Exception as e:
        print(f"Igor notification failed (non-fatal): {e}")

    print("Status: pending — Igor notified, will adopt on next turn")


def cmd_log(args):
    if not args:
        print("Usage: log <message>")
        sys.exit(1)
    msg = " ".join(args)
    _log({"action": "note", "message": msg})
    print(f"Logged: {msg}")


# ── Worker auto-default (D-worker-mode-routing-2026-04-21) ────────────────────
#
# HIGH-inertia or XL-sized tickets route to CC (reviewable konsole-spawn).
# Everything else routes to Igor (cheap in-process via engram chain / Qwen).
# Explicit `worker` in input JSON always wins.
#
# Keep these heuristics synced with lab/theigors/rules/coding.md
# ("Inertia levels") and decision D-worker-mode-routing-2026-04-21.

_HIGH_INERTIA_TAGS = {"HIGH", "high-inertia", "HIGH-inertia", "high_inertia"}
_HIGH_INERTIA_PATHS = (
    "brainstem/",
    "memory/models.py",
    "cognition/reasoners/base.py",
)


def _infer_worker(t: dict) -> str:
    """Route ticket to 'claude' (reviewable) or 'igor' (cheap) by metadata.

    Rule:
      HIGH-inertia tag OR size=XL OR description touches HIGH-inertia paths
        → 'claude' (CC reviews; konsole-spawned session).
      Everything else → 'igor' (in-process via engram chain, Qwen tier).

    Callers should only invoke this when the ticket has no explicit 'worker'.
    """
    tags = t.get("tags") or []
    if any(tag in _HIGH_INERTIA_TAGS for tag in tags):
        return "claude"

    size = (t.get("size") or "").upper()
    if size == "XL":
        return "claude"

    # Scan title + description for HIGH-inertia code paths
    blob_parts = [t.get("title") or "", t.get("description") or "", t.get("body") or ""]
    for f in t.get("required_files") or []:
        blob_parts.append(f)
    blob = " ".join(blob_parts)
    for path in _HIGH_INERTIA_PATHS:
        if path in blob:
            return "claude"

    return "igor"


def cmd_add(args):
    """Add tasks from a JSON file (array of task objects) or inline JSON string."""
    if not args:
        print("Usage: add <json-file-or-inline-json>")
        sys.exit(1)
    src = args[0]
    if os.path.exists(src):
        with open(src) as f:
            new_tasks = json.load(f)
    else:
        new_tasks = json.loads(src)
    if isinstance(new_tasks, dict):
        new_tasks = [new_tasks]
    tasks = _load()
    existing_ids = {t["id"] for t in tasks}
    added = 0
    for nt in new_tasks:
        if nt["id"] in existing_ids:
            print(f"  skip (exists): {nt['id']}")
            continue
        nt.setdefault("status", "pending")
        # D-worker-mode-routing-2026-04-21: auto-default by metadata if unset
        if "worker" not in nt or nt.get("worker") in (None, ""):
            nt["worker"] = _infer_worker(nt)
        nt.setdefault("result", None)
        nt.setdefault("claimed_at", None)
        nt.setdefault("completed_at", None)
        nt.setdefault("required_files", [])
        nt.setdefault("related_to", None)
        nt.setdefault("github_issue", None)
        nt.setdefault("decision_id", None)
        nt.setdefault("gate", None)
        tasks.append(nt)
        _log({"action": "add", "id": nt["id"], "title": nt["title"]})
        print(f"  added: {nt['id']} — {nt['title']}")
        added += 1
    _save(tasks)
    print(f"Added {added} task(s).")


def _igor_post(content: str, tag: str) -> bool:
    """POST a message to UC's /api/cc_send as author 'claude-code'.

    tag is a short label used for failure logging only.
    """
    data = json.dumps({"content": content}).encode()
    req = urllib.request.Request(
        IGOR_FLUSH_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5, context=_ssl_ctx()):
            return True
    except Exception as e:
        _log({"action": "flush_failed", "error": str(e), "tag": tag})
        print(f"  [Igor flush failed — UC not running? {e}]")
        return False


def cmd_flush_decision(args):
    """Post a design-decision flush to the channel (author: claude-code)."""
    if len(args) < 2:
        print("Usage: flush_decision <id> <summary>")
        sys.exit(1)
    decision_id = args[0]
    summary = " ".join(args[1:])
    content = f"[FLUSH decision {decision_id}] {summary}"
    if _igor_post(content, tag=decision_id):
        _log({"action": "flush_decision", "id": decision_id, "summary": summary})
        print(f"Flushed {decision_id} to Igor: {summary[:80]}")
    else:
        print(f"  (decision logged locally only)")


def cmd_flush_session(args):
    """Post a session-summary flush to the channel (author: claude-code)."""
    if len(args) < 2:
        print("Usage: flush_session <session_id> <summary>")
        sys.exit(1)
    session_id = args[0]
    summary = " ".join(args[1:])
    content = f"[FLUSH session {session_id}] {summary}"
    if _igor_post(content, tag=f"session_{session_id}"):
        _log({"action": "flush_session", "session": session_id})
        print(f"Flushed session {session_id} to Igor")
    else:
        print(f"  (session logged locally only)")


WORKER_PIDS_PATH = os.path.expanduser("~/.TheIgors/cc_channel/worker_pids.json")
DAEMON_PID_FILE = os.path.expanduser("~/.TheIgors/cc_channel/worker_daemon.pid")
DAEMON_SCRIPT = os.path.expanduser("~/TheIgors/lab/claudecode/worker_daemon.sh")


def _load_worker_pids():
    if not os.path.exists(WORKER_PIDS_PATH):
        return {}
    with open(WORKER_PIDS_PATH) as f:
        return json.load(f)


def _save_worker_pids(pids):
    os.makedirs(os.path.dirname(WORKER_PIDS_PATH), exist_ok=True)
    with open(WORKER_PIDS_PATH, "w") as f:
        json.dump(pids, f, indent=2)


def _daemon_alive():
    """Return daemon PID if running, else None."""
    if not os.path.exists(DAEMON_PID_FILE):
        return None
    try:
        pid = int(open(DAEMON_PID_FILE).read().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def cmd_notify_igor(args):
    """Send a message to Igor via the cc_send bridge (POST /api/cc_send)."""
    if not args:
        print("Usage: notify-igor <message>")
        sys.exit(1)
    msg = " ".join(args)
    data = json.dumps({"content": msg}).encode()
    req = urllib.request.Request(
        "https://localhost:8080/api/cc_send",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5, context=_ssl_ctx()):
            print(f"sent to Igor: {msg}")
    except Exception as e:
        _log({"action": "notify_igor_failed", "error": str(e), "msg": msg})
        print(f"  [notify-igor failed — Igor not running? {e}]")


def cmd_worker_launch(args):
    """Ensure the worker daemon is running. Spawns a konsole if not already alive.

    The daemon (worker_daemon.sh) polls the queue and runs /sprint for each
    pending ticket automatically — no xdotool injection needed.
    Ticket-id argument is accepted but ignored (daemon finds next pending itself).
    """
    import subprocess

    pid = _daemon_alive()
    if pid:
        print(
            f"Worker daemon already running (PID {pid}) — will pick up next pending ticket automatically."
        )
        return

    proc = subprocess.Popen(
        [
            "konsole",
            "--separate",
            "-e",
            "bash",
            "-c",
            f"bash {DAEMON_SCRIPT}; exec bash",
        ],
        start_new_session=True,
    )
    pids = _load_worker_pids()
    pids["daemon"] = {
        "konsole_pid": proc.pid,
        "launched_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_worker_pids(pids)
    print(f"Launched worker daemon — konsole PID {proc.pid}")


def cmd_reset(args):
    """Reset a single ticket back to pending (e.g., after a timeout)."""
    if not args:
        print("Usage: reset <id>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    prev = t["status"]
    t["status"] = "pending"
    t["claimed_at"] = None
    t["blocked_at"] = (
        None  # Clear block so adopt_top_queue_ticket will pick it up again
    )
    _save(tasks)
    _log({"action": "reset", "id": args[0], "prev_status": prev})
    print(f"Reset {args[0]}: {prev} → pending (blocked_at cleared)")


def cmd_reset_stale(args):
    """Reset all in_progress tickets back to pending (used at daemon startup to clean orphans)."""
    tasks = _load()
    reset_count = 0
    for t in tasks:
        if t["status"] == "in_progress":
            prev = t["status"]
            t["status"] = "pending"
            t["claimed_at"] = None
            _log({"action": "reset_stale", "id": t["id"], "prev_status": prev})
            print(f"  reset stale: {t['id']}")
            reset_count += 1
    if reset_count:
        _save(tasks)
    print(f"Reset {reset_count} stale in_progress ticket(s).")


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "claim": cmd_claim,
    "done": cmd_done,
    "block": cmd_block,
    "propose": cmd_propose,
    "approve": cmd_approve,
    "log": cmd_log,
    "add": cmd_add,
    "flush_decision": cmd_flush_decision,
    "flush_session": cmd_flush_session,
    "worker-launch": cmd_worker_launch,
    "notify-igor": cmd_notify_igor,
    "reset": cmd_reset,
    "reset-stale": cmd_reset_stale,
}


def cmd_set_epic(args):
    """Set the epic tag on one or more tickets: set-epic <epic> <id> [<id> ...]"""
    if len(args) < 2:
        print("Usage: set-epic <epic> <ticket-id> [<ticket-id> ...]")
        sys.exit(1)
    epic, ids = args[0], args[1:]
    tasks = _load()
    idx = {t["id"]: t for t in tasks}
    for tid in ids:
        if tid not in idx:
            print(f"  not found: {tid}")
            continue
        idx[tid]["epic"] = epic
        print(f"  {tid} → #{epic}")
    _save(tasks)


COMMANDS["set-epic"] = cmd_set_epic


def cmd_set_worker(args):
    """Assign worker (igor|claude) to one or more tickets: set-worker <worker> <id> [<id> ...]"""
    if len(args) < 2:
        print("Usage: set-worker <worker> <ticket-id> [<ticket-id> ...]")
        sys.exit(1)
    worker, ids = args[0], args[1:]
    if worker not in ("igor", "claude"):
        print(f"Unknown worker '{worker}' — use igor or claude")
        sys.exit(1)
    tasks = _load()
    idx = {t["id"]: t for t in tasks}
    for tid in ids:
        if tid not in idx:
            print(f"  not found: {tid}")
            continue
        idx[tid]["worker"] = worker
        print(f"  {tid} → worker={worker}")
    _save(tasks)


COMMANDS["set-worker"] = cmd_set_worker


def cmd_needs_review(args):
    """Mark a ticket needs_review — Igor self-coding review gate."""
    if not args:
        print("Usage: needs-review <id>")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, args[0])
    if not t:
        print(f"Task {args[0]} not found.")
        sys.exit(1)
    t["status"] = "needs_review"
    t["needs_review_at"] = _now()
    _save(tasks)
    _log({"action": "needs_review", "id": args[0], "title": t["title"]})
    print(f"Needs review: {args[0]}: {t['title']}")


COMMANDS["needs-review"] = cmd_needs_review


def cmd_gate(args):
    """Gate a ticket behind a precondition. Usage: gate <id> <reason>"""
    if len(args) < 2:
        print("Usage: gate <ticket-id> <reason-string>")
        sys.exit(1)
    tid = args[0]
    reason = " ".join(args[1:])
    tasks = _load()
    t = _find(tasks, tid)
    if not t:
        print(f"Task {tid} not found.")
        sys.exit(1)
    t["gate"] = reason
    _save(tasks)
    _log({"action": "gate", "id": tid, "reason": reason})
    print(f"Gated {tid}: {reason}")


COMMANDS["gate"] = cmd_gate


def cmd_ungate(args):
    """Clear a ticket's gate. Usage: ungate <id> [reason-cleared]"""
    if not args:
        print("Usage: ungate <ticket-id> [reason-cleared]")
        sys.exit(1)
    tid = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else None
    tasks = _load()
    t = _find(tasks, tid)
    if not t:
        print(f"Task {tid} not found.")
        sys.exit(1)
    prev = t.get("gate")
    t["gate"] = None
    _save(tasks)
    _log({"action": "ungate", "id": tid, "prev_gate": prev, "reason_cleared": reason})
    msg = f"Ungated {tid}"
    if prev:
        msg += f" (was: {prev})"
    if reason:
        msg += f" — {reason}"
    print(msg)


COMMANDS["ungate"] = cmd_ungate


def cmd_set_decision(args):
    """Attach a decision id to a ticket. Usage: set-decision <id> <decision-id>"""
    if len(args) < 2:
        print("Usage: set-decision <ticket-id> <decision-id>")
        sys.exit(1)
    tid, did = args[0], args[1]
    tasks = _load()
    t = _find(tasks, tid)
    if not t:
        print(f"Task {tid} not found.")
        sys.exit(1)
    t["decision_id"] = did
    _save(tasks)
    _log({"action": "set_decision", "id": tid, "decision_id": did})
    print(f"Set decision on {tid}: {did}")


COMMANDS["set-decision"] = cmd_set_decision


def cmd_set_github_issue(args):
    """Write a GitHub issue number back to a ticket: set-github-issue <id> <number>"""
    if len(args) < 2:
        print("Usage: set-github-issue <ticket-id> <github-issue-number>")
        sys.exit(1)
    tid, issue_num = args[0], args[1]
    try:
        issue_num = int(issue_num)
    except ValueError:
        print(f"Issue number must be an integer, got: {issue_num}")
        sys.exit(1)
    tasks = _load()
    t = _find(tasks, tid)
    if not t:
        print(f"Task {tid} not found.")
        sys.exit(1)
    t["github_issue"] = issue_num
    _save(tasks)
    _log({"action": "set_github_issue", "id": tid, "github_issue": issue_num})
    print(f"Set {tid} github_issue → {issue_num}")


COMMANDS["set-github-issue"] = cmd_set_github_issue


def cmd_retitle(args):
    """Update a ticket's title: retitle <id> <new-title>"""
    if len(args) < 2:
        print("Usage: retitle <ticket-id> <new-title>")
        sys.exit(1)
    tid = args[0]
    new_title = args[1]
    tasks = _load()
    t = _find(tasks, tid)
    if not t:
        print(f"Task {tid} not found.")
        sys.exit(1)
    old_title = t["title"]
    t["title"] = new_title
    _save(tasks)
    _log(
        {"action": "retitle", "id": tid, "old_title": old_title, "new_title": new_title}
    )
    print(f"Retitled {tid}: {new_title!r}")


COMMANDS["retitle"] = cmd_retitle


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
