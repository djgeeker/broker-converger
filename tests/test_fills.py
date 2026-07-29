"""Fill aggregation — partial fills are the normal case."""
from __future__ import annotations

import unittest
from dataclasses import dataclass

from broker_converger import aggregate


@dataclass
class Row:
    order_id: int
    side: str
    shares: float
    price: float
    commission: float = 0.0
    executed_at: str = ""


class AggregateTests(unittest.TestCase):
    def test_weighted_average_across_two_price_levels(self):
        """Last price and arithmetic mean are both wrong; only weighting is right."""
        got = aggregate([Row(38, "SLD", 7.0, 102.50), Row(38, "SLD", 3.0, 101.00)],
                        order_ids=38, side="SLD")
        self.assertEqual(got.quantity, 10.0)
        self.assertEqual(got.price, 102.05)
        self.assertNotEqual(got.price, (102.50 + 101.00) / 2)   # arithmetic mean
        self.assertNotEqual(got.price, 101.00)                  # last price

    def test_order_id_zero_never_matches(self):
        """0 means 'no such order'. Without this, a stray fill becomes yours."""
        rows = [Row(0, "BOT", 5.0, 100.0)]
        self.assertEqual(aggregate(rows, order_ids=0, side="BOT").quantity, 0.0)
        self.assertIsNone(aggregate(rows, order_ids=0, side="BOT").price)

    def test_several_order_ids_and_which_one_closed_it(self):
        got = aggregate([Row(49, "SLD", 1.0, 99.0), Row(50, "SLD", 2.0, 99.5)],
                        order_ids=(49, 50), side="SLD")
        self.assertEqual(got.quantity, 3.0)
        self.assertEqual(got.last_order_id, 50)

    def test_partial_counts_executions_not_quantity(self):
        one = aggregate([Row(7, "BOT", 10.0, 100.0)], order_ids=7, side="BOT")
        many = aggregate([Row(7, "BOT", 5.0, 100.0), Row(7, "BOT", 5.0, 100.0)],
                         order_ids=7, side="BOT")
        self.assertEqual(one.quantity, many.quantity)
        self.assertFalse(one.is_partial)
        self.assertTrue(many.is_partial)

    def test_zero_quantity_gives_none_price_not_zero(self):
        """0.0 is a legal price; 'unknown' must not look like it."""
        got = aggregate([Row(7, "BOT", 0.0, 100.0)], order_ids=7, side="BOT")
        self.assertIsNone(got.price)
        self.assertEqual(got.fill_count, 1)

    def test_matched_rows_keep_input_order(self):
        """So a caller summing across two groups reproduces the original order."""
        rows = [Row(7, "BOT", 1.0, 100.0, commission=1e7),
                Row(7, "BOT", 1.0, 100.0, commission=0.1),
                Row(7, "BOT", 1.0, 100.0, commission=2.13)]
        got = aggregate(rows, order_ids=7, side="BOT")
        self.assertEqual([f.commission for f in got.fills], [1e7, 0.1, 2.13])


if __name__ == "__main__":
    unittest.main()
