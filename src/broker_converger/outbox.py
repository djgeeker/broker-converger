"""Idempotency across process death: reserve before you call the broker.

    decide -> [crash] -> restart -> decide the same thing -> send twice

A strategy that re-derives state from market data will correctly reach the
same decision after a restart. Without a durable record that it was already
acted on, "correct" and "duplicate" are the same thing.

Append-only log written BEFORE the broker call, keyed by a stable decision id.
Reserving is fail-closed: an id already present is refused.

Making the id stable: derive it from the decision (strategy, instrument, kind,
signal time, prices), not from when you had it, and exclude anything
describing state after acting. A timestamp or counter produces a fresh id
after a restart and the outbox never sees the duplicate.

This stops duplicates; it does not resolve stragglers. Automatic replay is
deliberately not offered — replaying safely needs a broker check first, and
only cancellations are safe to retry blindly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExecutionOutbox:
    """Append-only, fail-closed decision log, one JSON object per line."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def reserve(self, event_id: str, payload: Any = None) -> bool:
        """Claim a decision id once. False if already claimed.

        Call before the broker call. Reserving afterwards leaves exactly the
        window this class closes. An empty id is refused: a decision that
        cannot be identified cannot be de-duplicated.
        """
        if not event_id or event_id in self._known_ids():
            return False
        self._append({"status": "reserved", "event_id": event_id, "payload": payload})
        return True

    def mark(self, event_id: str, *, status: str, detail: str = "") -> None:
        """Record the outcome. Unmarked reservations are what pending() finds."""
        if not event_id:
            return
        self._append({"status": status, "event_id": event_id, "detail": detail})

    def pending(self) -> list[dict]:
        """Reserved but never marked — decisions that went quiet.

        Each is something your system believes it handled and the broker may
        never have heard of. Surface them; do not replay automatically.
        """
        reserved: dict[str, Any] = {}
        terminal: set[str] = set()
        if not self.path.exists():
            return []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_id = str(row.get("event_id", ""))
            if not event_id:
                continue
            if row.get("status") == "reserved":
                reserved[event_id] = row.get("payload")
            else:
                terminal.add(event_id)
        return [
            {"event_id": eid, "payload": payload}
            for eid, payload in reserved.items()
            if eid not in terminal
        ]

    def _known_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        found: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                event_id = str(json.loads(line).get("event_id", ""))
            except json.JSONDecodeError:
                # A torn last line from a crash mid-write must not make the log
                # unreadable — that would fail open, the one direction this
                # class may never fail in.
                continue
            if event_id:
                found.add(event_id)
        return found

    def _append(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
