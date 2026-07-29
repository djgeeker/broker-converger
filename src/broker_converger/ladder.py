"""The priority ladder: desired vs snapshot -> at most one correction.

Pure function, no IO. Three rules, each made structural rather than
documented:

1. Read before act — you never call this without a successful snapshot.
2. One corrective per cycle — the return type is Optional[Correction], so two
   orders in one pass is not expressible.
3. Never trust the echo — a submit call's return value is for logs; order
   state is whatever the next snapshot says.

Rungs, in order of least-acceptable state. Each returns immediately:

    (1) protection  holding with no protective order -> repair, nothing else
    (2) exit        wants out -> close its OWN quantity
    (3) cancel      wants resting orders gone
    (4) place       reserved but not sent -> send (idempotent via ref)
    (5) reprice     price differs -> modify, in `orders` order

None means converged, which should be the answer almost every cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .desired import DesiredOrder, DesiredState
from .snapshot import BrokerOrderView, BrokerSnapshot


@dataclass(frozen=True)
class Correction:
    """The one action for this cycle. `kind` selects your actuator."""

    kind: str
    reason: str
    #: Which order. Empty for single-order strategies.
    slot: str = ""


def find_order(order: DesiredOrder, snapshot: BrokerSnapshot) -> Optional[BrokerOrderView]:
    """Find by claimed id, then fall back to (ref, action, type).

    The fallback is what makes placement idempotent: if a submit crashed — or
    the client lied about failing — after the broker accepted it, the next
    cycle finds it by ref and does not send a second.
    """
    for live in snapshot.orders:
        if order.order_id and live.order_id == order.order_id:
            return live
    for live in snapshot.orders:
        if (
            order.order_ref
            and live.order_ref == order.order_ref
            and live.action == order.action
            and live.order_type == order.order_type
        ):
            return live
    return None


def _live_price(order: DesiredOrder, live: BrokerOrderView) -> float:
    return live.stop_price if order.order_type == "STP" else live.limit_price


def plan(
    *,
    desired: Optional[DesiredState],
    snapshot: BrokerSnapshot,
    price_tick: float,
) -> Optional[Correction]:
    """Return at most one correction.

    Prices are compared with a half-tick tolerance so a broker rounding to the
    nearest legal increment does not look like a difference — otherwise you
    would send a modify every cycle forever.
    """
    if desired is None:
        return None
    half_tick = max(price_tick, 0.0) / 2.0
    resolved = tuple((order, find_order(order, snapshot)) for order in desired.orders)

    # (1) Protection outranks every other difference, however many exist.
    if desired.holding:
        for order, live in resolved:
            if order.protective and live is None:
                return Correction(order.ensure_kind, "position_without_protective_order", order.slot)

    # (2) Zero owned quantity => send nothing. The close already happened and
    #     the fact is arriving via reconciliation; sending anyway turns a flat
    #     account into a short one.
    if desired.exiting:
        if abs(desired.exit_quantity) > 1e-9:
            return Correction("exit_market", "strategy_requested_exit", "")
        return None

    # (3) An order already gone gets no second guess about why — that is
    #     reconciliation's call. Protective orders are never cancelled here: a
    #     cancel racing a fill must not strip the position's protection.
    if desired.cancelling:
        for order, live in resolved:
            if not order.protective and live is not None and order.cancel_kind:
                return Correction(order.cancel_kind, "strategy_requested_cancel", order.slot)
        return None

    # (4) Found at the broker => the previous submit succeeded whatever the
    #     client said; claiming ids is reconciliation's job, stay quiet.
    if desired.pending_place:
        for order, live in resolved:
            if order.place_when_missing and live is None:
                return Correction(order.place_kind, "reserved_not_yet_placed", order.slot)
        return None

    # (5) List order is the priority when several prices differ at once.
    for order, live in resolved:
        if live is None:
            if order.anchor:
                return None
            continue
        if not order.modify_kind:
            continue
        if order.raise_only:
            if order.price > _live_price(order, live) + half_tick:
                return Correction(order.modify_kind, order.modify_reason, order.slot)
            continue
        if abs(order.price - _live_price(order, live)) > half_tick:
            return Correction(order.modify_kind, order.modify_reason, order.slot)
    return None
