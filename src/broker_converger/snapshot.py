"""Read model: what the broker actually has right now.

Constructing a BrokerSnapshot asserts the read succeeded. If a request timed
out, raise — do not return an empty snapshot. "Could not read" and "nothing is
there" are different facts, and a converger that confuses them places
duplicates.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerOrderView:
    """One working order, flattened to primitives so planning stays pure."""

    order_id: int
    #: Your submission tag (IBKR: orderRef). Survives process restarts, which
    #: is what makes crash recovery possible.
    order_ref: str
    action: str          # BUY / SELL
    order_type: str      # LMT / STP / MKT
    limit_price: float = 0.0
    stop_price: float = 0.0   # IBKR: auxPrice
    status: str = ""


@dataclass(frozen=True)
class BrokerSnapshot:
    """One honest read. Read failed => raise, don't construct this."""

    orders: tuple[BrokerOrderView, ...]
    #: Account-level net position, unlabelled by strategy. With several
    #: strategies on one instrument this alone cannot tell you what is yours —
    #: see broker_converger.ownership.
    net_position: float = 0.0
