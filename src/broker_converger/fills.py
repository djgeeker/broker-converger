"""Fill aggregation: how much filled, at what average price.

Small enough that every codebase grows several copies of it, and they drift.
The system this was extracted from had four, and only one carried the
order_id == 0 guard below.

Partial fills are the normal case, not an edge case: in live paper trading
about a third of orders filled in more than one execution, one of them in five
executions across two prices. Last-execution price and arithmetic mean are
both wrong; only quantity-weighting is right, and it is also what slippage
measurement divides by.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence


class Fill(Protocol):
    """Structural typing so your rows and a client's execution objects share
    one implementation instead of each growing a copy."""

    order_id: int
    side: str
    shares: float
    price: float


@dataclass(frozen=True)
class AggregatedFills:
    quantity: float
    #: None when nothing filled — not 0.0, which is a legal price. Code that
    #: mistakes "unknown" for "zero" re-pegs stops to nonsense.
    price: Optional[float]
    last_executed_at: str
    #: > 1 means a partial fill.
    fill_count: int
    commission: float
    #: Identifies which of several exit orders actually closed the position.
    last_order_id: int
    #: Matched rows in input order, so a caller summing across two groups can
    #: reproduce the original order. Float addition is not associative; the
    #: difference is a silent one-ULP drift in your books, not an error.
    fills: tuple

    @property
    def is_partial(self) -> bool:
        return self.fill_count > 1


def _matches(fill: Fill, order_ids: frozenset[int], side: str) -> bool:
    order_id = int(getattr(fill, "order_id", 0) or 0)
    if not order_id:
        # 0 means "no such order", not "order number zero". Without this, an
        # execution whose id failed to parse gets attributed to any record
        # that has not claimed an id yet — someone else's fill becomes yours.
        return False
    return order_id in order_ids and str(getattr(fill, "side", "")).upper() == side


def aggregate(
    fills: Iterable[Fill],
    *,
    order_ids: int | Sequence[int],
    side: str,
) -> AggregatedFills:
    """Roll up every `side` fill on `order_ids`.

    Pass fills already merged with your durable ledger. Brokers commonly
    expose only the current session (IBKR clears daily), so a position opened
    yesterday is under-counted otherwise. This function is pure and cannot do
    that merge for you.
    """
    ids = frozenset(
        int(x or 0) for x in ([order_ids] if isinstance(order_ids, int) else order_ids)
    )
    want = str(side).upper()
    matched = [fill for fill in fills if _matches(fill, ids, want)]
    quantity = sum(float(fill.shares) for fill in matched)
    if quantity <= 0:
        return AggregatedFills(0.0, None, "", len(matched), 0.0, 0, tuple(matched))
    notional = sum(float(fill.shares) * float(fill.price) for fill in matched)
    return AggregatedFills(
        quantity=quantity,
        price=notional / quantity,
        last_executed_at=str(getattr(matched[-1], "executed_at", "") or ""),
        fill_count=len(matched),
        commission=sum(float(getattr(fill, "commission", 0.0) or 0.0) for fill in matched),
        last_order_id=int(getattr(matched[-1], "order_id", 0) or 0),
        fills=tuple(matched),
    )
