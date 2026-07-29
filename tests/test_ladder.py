"""The ladder: rung order, and the cases that look harmless but are not."""
from __future__ import annotations

import unittest

from broker_converger import BrokerOrderView, BrokerSnapshot, DesiredOrder, DesiredState, plan


def entry(**kw):
    base = dict(slot="entry", action="BUY", order_type="LMT", price=100.0,
                order_id=1, order_ref="ref-1", anchor=True,
                place_kind="place_bracket", modify_kind="modify_limit",
                cancel_kind="cancel_entry", modify_reason="limit_changed")
    base.update(kw)
    return DesiredOrder(**base)


def stop(**kw):
    base = dict(slot="stop", action="SELL", order_type="STP", price=95.0,
                order_id=2, order_ref="ref-1", protective=True,
                modify_kind="modify_stop", modify_reason="stop_changed")
    base.update(kw)
    return DesiredOrder(**base)


def snap(*orders, net=0.0):
    return BrokerSnapshot(orders=tuple(orders), net_position=net)


def live(order_id=1, ref="ref-1", action="BUY", otype="LMT", lmt=100.0, aux=0.0):
    return BrokerOrderView(order_id=order_id, order_ref=ref, action=action,
                           order_type=otype, limit_price=lmt, stop_price=aux)


LIVE_STOP = live(order_id=2, action="SELL", otype="STP", lmt=0.0, aux=95.0)


class RungOrderTests(unittest.TestCase):
    def test_protection_outranks_everything_else(self):
        """Holding with no stop, and three other diffs at once -> only the stop."""
        got = plan(
            desired=DesiredState(
                orders=(entry(price=999.0), stop()),
                holding=True, owned_quantity=3, exiting=True, exit_quantity=3,
                cancelling=True,
            ),
            snapshot=snap(live(), net=3.0), price_tick=0.25,
        )
        self.assertEqual(got.kind, "ensure_protective")
        self.assertEqual(got.slot, "stop")

    def test_exit_with_zero_owned_quantity_sends_nothing(self):
        """The close already happened. Sending anyway turns flat into short."""
        self.assertIsNone(plan(
            desired=DesiredState(orders=(stop(),), holding=True, exiting=True,
                                 exit_quantity=0.0),
            snapshot=snap(LIVE_STOP, net=5.0), price_tick=0.25,
        ))

    def test_cancel_never_touches_a_protective_order(self):
        """A cancel racing a fill must not strip the position's protection."""
        got = plan(
            desired=DesiredState(orders=(stop(), entry()), cancelling=True),
            snapshot=snap(LIVE_STOP, live()), price_tick=0.25,
        )
        self.assertEqual(got.slot, "entry")

    def test_at_most_one_correction_ever(self):
        """Two mispriced orders at once still yields one action, the first."""
        got = plan(
            desired=DesiredState(orders=(entry(price=101.0), stop(price=96.0))),
            snapshot=snap(live(lmt=100.0), LIVE_STOP), price_tick=0.25,
        )
        self.assertEqual(got.slot, "entry")


class IdempotencyTests(unittest.TestCase):
    def test_reserved_and_absent_places_it(self):
        got = plan(
            desired=DesiredState(orders=(entry(order_id=0, place_when_missing=True),),
                                 pending_place=True),
            snapshot=snap(), price_tick=0.25,
        )
        self.assertEqual(got.kind, "place_bracket")

    def test_reserved_but_already_at_the_broker_places_nothing(self):
        """Found by ref alone -> the crashed submit actually succeeded."""
        self.assertIsNone(plan(
            desired=DesiredState(orders=(entry(order_id=0, place_when_missing=True),),
                                 pending_place=True),
            snapshot=snap(live(order_id=777)), price_tick=0.25,
        ))


class PriceTests(unittest.TestCase):
    def test_a_half_tick_difference_is_not_a_difference(self):
        """Otherwise you send a modify every cycle, forever."""
        self.assertIsNone(plan(
            desired=DesiredState(orders=(entry(price=100.10),)),
            snapshot=snap(live(lmt=100.0)), price_tick=0.25,
        ))

    def test_a_trailing_stop_only_ratchets_one_way(self):
        held = DesiredState(orders=(stop(raise_only=True, price=90.0),), holding=True)
        self.assertIsNone(plan(desired=held, snapshot=snap(LIVE_STOP), price_tick=0.25))
        up = DesiredState(orders=(stop(raise_only=True, price=99.0),), holding=True)
        self.assertEqual(
            plan(desired=up, snapshot=snap(LIVE_STOP), price_tick=0.25).kind, "modify_stop"
        )

    def test_a_missing_anchor_stops_all_judgement_this_cycle(self):
        """Filled/cancelled/vanished are reconciliation's call, not ours."""
        self.assertIsNone(plan(
            desired=DesiredState(orders=(entry(), stop(price=99.0))),
            snapshot=snap(LIVE_STOP), price_tick=0.25,
        ))

    def test_an_order_with_no_modify_actuator_is_never_repriced(self):
        """Empty kind means the path does not exist, not 'use a default'."""
        self.assertIsNone(plan(
            desired=DesiredState(orders=(entry(anchor=False, modify_kind="", price=999.0),)),
            snapshot=snap(live()), price_tick=0.25,
        ))


if __name__ == "__main__":
    unittest.main()
