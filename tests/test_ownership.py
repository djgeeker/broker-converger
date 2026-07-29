"""Ownership arithmetic — the difference between flat and doubled-up short."""
from __future__ import annotations

import unittest

from broker_converger import owned_exit_quantity, quantity_on_contract


class OwnedExitQuantityTests(unittest.TestCase):
    def test_another_strategys_position_is_not_mine_to_close(self):
        """My stop filled, reconciliation has not run, someone else holds 3."""
        self.assertEqual(
            owned_exit_quantity(net_position=3.0, other_strategy_quantity=3.0, owned=3.0),
            0.0,
        )

    def test_i_still_close_my_own_when_another_strategy_also_holds(self):
        self.assertEqual(
            owned_exit_quantity(net_position=6.0, other_strategy_quantity=3.0, owned=3.0),
            3.0,
        )

    def test_unreadable_others_degrade_to_the_naive_behaviour(self):
        """Adopting this function must never add risk versus not having it."""
        self.assertEqual(
            owned_exit_quantity(net_position=3.0, other_strategy_quantity=0.0, owned=3.0),
            3.0,
        )

    def test_over_reporting_others_closes_nothing_rather_than_too_much(self):
        self.assertEqual(
            owned_exit_quantity(net_position=3.0, other_strategy_quantity=99.0, owned=3.0),
            0.0,
        )

    def test_a_short_net_position_is_measured_by_size_not_sign(self):
        self.assertEqual(
            owned_exit_quantity(net_position=-4.0, other_strategy_quantity=1.0, owned=5.0),
            3.0,
        )


class ContractMatchingTests(unittest.TestCase):
    def test_only_the_same_contract_explains_anything(self):
        """After a roll, equal quantities on different expiries mean nothing."""
        self.assertEqual(quantity_on_contract(((999, 3.0),), contract_id=111), 0.0)
        self.assertEqual(quantity_on_contract(((111, 3.0),), contract_id=111), 3.0)

    def test_an_unknown_contract_id_explains_nothing(self):
        self.assertEqual(quantity_on_contract(((111, 3.0),), contract_id=0), 0.0)


if __name__ == "__main__":
    unittest.main()
