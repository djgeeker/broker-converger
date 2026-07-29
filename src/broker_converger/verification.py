"""Submission verification: "I sent it" is not "it exists".

The failure this catches: a live strategy submitted an entry on every signal
for nine consecutive days and filled nothing. The submit call returned
normally with order ids, the journal recorded `submitted`, no exception fired.
Orders were being rejected at the broker on arrival, and the rejection landed
after the process had moved on. Crash recovery could not help either — it
required seeing the parent order before acting, and the parent never existed.

An order-management system that only listens for problems cannot detect
silence. You have to go and ask.

For every entry past the moment it should have had an outcome, gather evidence
from three independent places and rule:

    working orders   (matched by submission tag)
    completed orders (tag + terminal status)
    executions       (parent order id)

    any fill / still working / completed-and-filled -> verified
    completed-and-cancelled / absent everywhere     -> DEAD -> alarm

Two properties matter as much as the rule. Evidence expires: brokers reset
their order and execution views daily, so verify inside a short grace period
or every verdict becomes "absent everywhere". And a failed read writes
nothing: marking something dead because you could not look is the same mistake
as trading on an empty snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True)
class SubmissionRecord:
    """What you journaled when you submitted an entry."""

    event_id: str
    #: Tag attached to the order; usually the event id.
    order_ref: str
    parent_order_id: int
    #: When the decision was made, in the venue's local time.
    signal_time: datetime
    #: Minutes the order was deliberately held before becoming active
    #: (good-after-time). 0 for immediate orders.
    activation_delay_minutes: int = 0
    status: str = "submitted"
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    """What the three places said about one submission."""

    order_is_working: bool = False
    completed_status: str = ""
    has_fill: bool = False


@dataclass(frozen=True)
class Verdict:
    event_id: str
    verdict: str      # verified | dead
    detail: str

    @property
    def is_dead(self) -> bool:
        return self.verdict == "dead"


#: Still awaiting an outcome. Anything else is terminal and never re-examined —
#: re-checking settled records turns verification into duplicate alarms.
OPEN_STATUSES = frozenset({"reserved", "submitted", "unknown"})


def due_for_verification(
    records: Iterable[SubmissionRecord],
    *,
    now: datetime,
    grace_minutes: int = 5,
) -> list[SubmissionRecord]:
    """Which submissions are past the moment they should have had an outcome.

    Zero broker round trips — reads only your journal, so it is cheap enough
    to call every cycle and you pay for a connection only when it returns
    something.

    Keep grace_minutes small. It is bounded above by how long the broker keeps
    the evidence; a generous grace produces confident "absent everywhere"
    verdicts about records that merely expired.
    """
    due: list[SubmissionRecord] = []
    for record in records:
        if record.status not in OPEN_STATUSES:
            continue
        deadline = record.signal_time + timedelta(
            minutes=record.activation_delay_minutes + grace_minutes
        )
        if now >= deadline:
            due.append(record)
    return due


def rule(record: SubmissionRecord, evidence: Evidence) -> Verdict:
    """Evidence -> verdict. Pure; no clock, no broker.

    One positive sign is enough. The three sources are not equally fresh at any
    instant — an order can fill and leave the working list before the completed
    list catches up — so requiring agreement would manufacture false deaths. A
    false "verified" costs one missed alarm; a false "dead" costs trust in the
    alarm itself.
    """
    if evidence.has_fill or evidence.order_is_working or evidence.completed_status == "Filled":
        detail = evidence.completed_status or ("working" if evidence.order_is_working else "filled")
        return Verdict(record.event_id, "verified", detail)
    return Verdict(record.event_id, "dead", evidence.completed_status or "not_found_anywhere")


def verify(
    records: Iterable[SubmissionRecord],
    *,
    now: datetime,
    gather,
    grace_minutes: int = 5,
) -> list[Verdict]:
    """Prefilter, gather evidence once for the batch, rule on each record.

    `gather` is a callable list[SubmissionRecord] -> dict[event_id, Evidence].
    It is called once, not per record: the three broker queries are batch
    queries, and issuing them per order trips rate limits.

    Exceptions from `gather` are not caught. A failed read must abort the pass
    and write nothing — verdicts you could not substantiate are worse than no
    verification, because now the alarms lie.
    """
    due = due_for_verification(records, now=now, grace_minutes=grace_minutes)
    if not due:
        return []
    evidence = gather(due)
    return [rule(record, evidence.get(record.event_id, Evidence())) for record in due]
