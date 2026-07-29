"""Which part of the account's net position is mine?

Brokers report one net position per instrument with no strategy label. The
moment two strategies share an account and an instrument, that number is an
ambiguity, and resolving it wrongly closes someone else's position.

The failure is silent. Shape:

    strategy A's stop fills, its reconciliation has not run yet
    strategy B still holds 3 contracts
    -> net position is non-zero
    -> A asks "anything left to close?" -> yes -> A closes B's position

Rule: size every correction, above all every close, from your own ledger, and
use the net position only as an upper bound.
"""
from __future__ import annotations

from typing import Iterable


def owned_exit_quantity(
    *,
    net_position: float,
    other_strategy_quantity: float,
    owned: float,
) -> float:
    """min(what my ledger says I hold, what the net cannot explain away).

    Failure directions are deliberately asymmetric:

    * others unreadable (report 0) -> degenerates to the whole net position,
      i.e. the naive behaviour. Adopting this adds no new risk.
    * others over-report -> close nothing this cycle. The position stays, but
      rung (1) guarantees its protective order is there, and the next cycle
      retries.

    The opposite mistake — treating the net as your own — is not recoverable
    by waiting.
    """
    unexplained = abs(float(net_position)) - max(float(other_strategy_quantity), 0.0)
    return max(0.0, min(max(float(owned), 0.0), unexplained))


def quantity_on_contract(
    positions: Iterable[tuple[int, float]],
    *,
    contract_id: int,
) -> float:
    """Sum other strategies' holdings on the same contract.

    Matching contract id, not just quantity, matters at rolls: "3 of the
    September expiry" and "3 of the December expiry" match numerically and
    mean nothing. An unknown id (0) explains nothing, which keeps the
    arithmetic conservative.
    """
    if not contract_id:
        return 0.0
    return sum(
        abs(float(quantity))
        for con_id, quantity in positions
        if int(con_id or 0) == int(contract_id)
    )
