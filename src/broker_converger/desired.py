"""Expectation model: what your strategy wants the broker to look like.

The whole adaptation surface. To plug a strategy in you write one function
returning a DesiredState; the ladder, the one-corrective rule and the
ownership arithmetic are already written.

Desired state rather than commands: commands accumulate one bug per edge case
because each writer keeps its own picture of reality. A desired state is
re-derived every cycle, so it has no memory to drift, and crash recovery is
just the next cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DesiredOrder:
    """One order the strategy expects to exist."""

    #: Stable name for this order across cycles, independent of broker ids
    #: (ids change on cancel/replace). Multi-order strategies must be specific:
    #: "move the stop" is not an instruction when you have three.
    slot: str
    action: str          # BUY / SELL
    order_type: str      # LMT / STP
    price: float
    order_id: int = 0
    #: Fallback identity when order_id is not claimed yet. This is what makes
    #: placement read-idempotent after a crashed submit.
    order_ref: str = ""
    #: Stops. While holding, a missing protective order is repaired before
    #: anything else.
    protective: bool = False
    #: Price may only move one way (trailing stop). A desired price moving the
    #: wrong way can only come from bad data, so it is not executed.
    raise_only: bool = False
    #: If absent, stop judging this cycle — it filled, was cancelled or
    #: vanished, and that verdict belongs to reconciliation.
    anchor: bool = False
    #: Whether the converger should place this when missing. False for bracket
    #: children: placing one separately gives you two stops on one position.
    place_when_missing: bool = False

    # Your actuator names. Empty means "this path does not exist" and the rung
    # skips this order — naming an unimplemented actuator silently promises a
    # repair that never happens.
    place_kind: str = ""
    modify_kind: str = ""
    cancel_kind: str = ""
    ensure_kind: str = "ensure_protective"
    modify_reason: str = "desired_price_changed"


@dataclass(frozen=True)
class DesiredState:
    """Everything the strategy expects, for one cycle."""

    orders: tuple[DesiredOrder, ...] = ()
    #: Holding anything => protective orders must exist. Separate from
    #: owned_quantity on purpose: a failed quantity read returning 0 must not
    #: be read as "flat" and leave a real position unprotected.
    holding: bool = False
    #: This strategy's own quantity, not the account net. Sizing off the net
    #: means correcting — or closing — someone else's position.
    owned_quantity: float = 0.0
    exiting: bool = False
    #: How much to close. Must be this strategy's own quantity.
    exit_quantity: float = 0.0
    cancelling: bool = False
    #: Two-phase submit, phase one: reserved durably, not yet sent.
    pending_place: bool = False
    tags: dict = field(default_factory=dict)
