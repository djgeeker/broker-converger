"""A complete strategy in ~40 lines, against a fake broker. Runnable:

    PYTHONPATH=src python3 examples/minimal_leg.py

Shows the whole loop: read -> translate to a desired state -> one correction
-> act. The fake broker is deliberately hostile: it accepts the order but
reports failure, which is what makes the idempotency visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from broker_converger import (  # noqa: E402
    BrokerOrderView, BrokerSnapshot, DesiredOrder, DesiredState, plan,
)

TICK = 0.25


class FakeBroker:
    """Accepts everything, then lies about it."""

    def __init__(self):
        self.orders: list[BrokerOrderView] = []
        self.next_id = 100

    def read(self) -> BrokerSnapshot:
        return BrokerSnapshot(orders=tuple(self.orders), net_position=0.0)

    def place_bracket(self, ref: str, limit: float, stop: float) -> str:
        self.orders.append(BrokerOrderView(self.next_id, ref, "BUY", "LMT", limit_price=limit))
        self.orders.append(BrokerOrderView(self.next_id + 1, ref, "SELL", "STP", stop_price=stop))
        self.next_id += 2
        return "ERROR: submit failed"      # the echo lies

    def modify_limit(self, ref: str, price: float) -> str:
        for i, o in enumerate(self.orders):
            if o.order_ref == ref and o.order_type == "LMT":
                self.orders[i] = BrokerOrderView(o.order_id, ref, "BUY", "LMT", limit_price=price)
        return "ok"


# --- The only function a strategy has to write -------------------------------

def desired_state(*, limit: float, stop: float, placed: bool) -> DesiredState:
    entry = DesiredOrder(
        slot="entry", action="BUY", order_type="LMT", price=limit,
        order_ref="my-decision-1", anchor=True,
        place_when_missing=not placed,
        place_kind="place_bracket", modify_kind="modify_limit",
    )
    protective = DesiredOrder(
        slot="stop", action="SELL", order_type="STP", price=stop,
        order_ref="my-decision-1", protective=True, modify_kind="modify_stop",
    )
    return DesiredState(orders=(entry, protective), pending_place=not placed)


def main() -> None:
    broker = FakeBroker()
    limit, stop, placed = 100.00, 95.00, False

    for cycle in range(1, 5):
        if cycle == 3:
            limit = 100.75                      # strategy changes its mind
        snapshot = broker.read()                # read before act
        action = plan(desired=desired_state(limit=limit, stop=stop, placed=placed),
                      snapshot=snapshot, price_tick=TICK)

        if action is None:
            print(f"cycle {cycle}: converged")
            continue
        print(f"cycle {cycle}: {action.kind} ({action.reason}) slot={action.slot!r}")
        if action.kind == "place_bracket":
            echo = broker.place_bracket("my-decision-1", limit, stop)
            print(f"           broker echoed {echo!r} — ignored, next read decides")
            placed = True
        elif action.kind == "modify_limit":
            broker.modify_limit("my-decision-1", limit)

    print("\norders at the broker:")
    for o in broker.orders:
        print(f"  #{o.order_id} {o.action} {o.order_type} "
              f"{o.limit_price or o.stop_price}")
    print("\nExactly one entry despite the failed echo — the next cycle found it by ref.")


if __name__ == "__main__":
    main()
