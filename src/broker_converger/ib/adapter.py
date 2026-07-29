"""IBKR adapter: turn a live client into the library's read model.

Optional — the core has no dependencies and works against any broker.

Read-only on purpose. Placing orders stays in your code, because order
construction is where instrument- and strategy-specific detail lives. The
library tells you which single action to take; how to express it is yours.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..snapshot import BrokerOrderView, BrokerSnapshot
from ..verification import Evidence, SubmissionRecord


class BrokerReadFailed(RuntimeError):
    """A read did not complete. Skip the cycle; do not act on a partial read."""


def read_snapshot(ib: Any, *, contract_id: int = 0) -> BrokerSnapshot:
    """Read working orders and the net position for one contract.

    Raises BrokerReadFailed rather than returning an empty snapshot.

    Order visibility is per client id: IBKR shows a connection only the orders
    that client id submitted, even via reqAllOpenOrders. Reading with a
    different client id returns an empty list, indistinguishable from "no
    orders exist", which makes a converger place duplicates of everything.
    Use the same client id you submit with.
    """
    try:
        trades = list(ib.reqAllOpenOrders()) if hasattr(ib, "reqAllOpenOrders") else list(ib.openTrades())
    except Exception as exc:  # noqa: BLE001
        raise BrokerReadFailed(f"open orders unreadable: {exc!r}") from exc

    views = tuple(
        BrokerOrderView(
            order_id=int(getattr(order, "orderId", 0) or 0),
            order_ref=str(getattr(order, "orderRef", "") or ""),
            action=str(getattr(order, "action", "") or "").upper(),
            order_type=str(getattr(order, "orderType", "") or "").upper(),
            limit_price=float(getattr(order, "lmtPrice", 0.0) or 0.0),
            stop_price=float(getattr(order, "auxPrice", 0.0) or 0.0),
            status=str(getattr(getattr(trade, "orderStatus", None), "status", "") or ""),
        )
        for trade in trades
        for order in [getattr(trade, "order", trade)]
    )

    try:
        positions = list(ib.positions())
    except Exception as exc:  # noqa: BLE001
        raise BrokerReadFailed(f"positions unreadable: {exc!r}") from exc

    net = sum(
        float(getattr(p, "position", 0.0) or 0.0)
        for p in positions
        if not contract_id
        or int(getattr(getattr(p, "contract", None), "conId", 0) or 0) == contract_id
    )
    return BrokerSnapshot(orders=views, net_position=net)


class IBEvidenceGatherer:
    """Gather submission evidence from IBKR's three views.

    Pass as the `gather` argument of broker_converger.verify.

    filled_order_ids must come from executions merged with your durable
    ledger, not a bare reqExecutions: brokers expose only the current session,
    so anything from before the daily reset is missing and would produce
    "dead" verdicts for orders that filled fine yesterday.
    """

    def __init__(self, ib: Any, *, filled_order_ids: Iterable[int] = ()):
        self.ib = ib
        self.filled_order_ids = {int(x) for x in filled_order_ids}

    def __call__(self, records: list[SubmissionRecord]) -> dict[str, Evidence]:
        try:
            working = list(self.ib.reqAllOpenOrders()) if hasattr(self.ib, "reqAllOpenOrders") else list(self.ib.openTrades())
            completed = (
                list(self.ib.reqCompletedOrders(apiOnly=False))
                if hasattr(self.ib, "reqCompletedOrders")
                else []
            )
        except Exception as exc:  # noqa: BLE001
            # Propagate: verify() must abort and record nothing.
            raise BrokerReadFailed(f"verification read failed: {exc!r}") from exc

        def ref(trade: Any) -> str:
            return str(getattr(getattr(trade, "order", trade), "orderRef", "") or "")

        def action(trade: Any) -> str:
            return str(getattr(getattr(trade, "order", trade), "action", "") or "").upper()

        out: dict[str, Evidence] = {}
        for record in records:
            tag = record.order_ref or record.event_id
            out[record.event_id] = Evidence(
                order_is_working=any(ref(t) == tag and action(t) == "BUY" for t in working),
                completed_status=next(
                    (
                        str(getattr(getattr(t, "orderStatus", None), "status", "") or "")
                        for t in completed
                        if ref(t) == tag and action(t) == "BUY"
                    ),
                    "",
                ),
                has_fill=record.parent_order_id > 0
                and record.parent_order_id in self.filled_order_ids,
            )
        return out
