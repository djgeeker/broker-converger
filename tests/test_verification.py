"""Verification — 'I sent it' is not 'it exists'."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from broker_converger import Evidence, SubmissionRecord, due_for_verification, rule, verify

NOW = datetime(2026, 1, 2, 12, 0, 0)


def record(**kw):
    base = dict(event_id="e1", order_ref="e1", parent_order_id=7,
                signal_time=datetime(2026, 1, 2, 11, 0, 0))
    base.update(kw)
    return SubmissionRecord(**base)


class DueTests(unittest.TestCase):
    def test_not_yet_due_is_left_alone(self):
        just_sent = record(signal_time=NOW - timedelta(minutes=1))
        self.assertEqual(due_for_verification([just_sent], now=NOW, grace_minutes=5), [])

    def test_the_activation_delay_pushes_the_deadline_out(self):
        """An order deliberately held for 30 minutes is not late at minute 10."""
        held = record(signal_time=NOW - timedelta(minutes=10), activation_delay_minutes=30)
        self.assertEqual(due_for_verification([held], now=NOW), [])

    def test_terminal_records_are_never_rechecked(self):
        """Re-checking settled records turns verification into duplicate alarms."""
        for status in ("entry_verified", "entry_dead", "cancelled"):
            self.assertEqual(due_for_verification([record(status=status)], now=NOW), [])


class RuleTests(unittest.TestCase):
    def test_any_single_positive_sign_is_enough(self):
        """Requiring agreement across three unsynchronised views invents deaths."""
        for evidence in (Evidence(has_fill=True),
                         Evidence(order_is_working=True),
                         Evidence(completed_status="Filled")):
            self.assertEqual(rule(record(), evidence).verdict, "verified")

    def test_cancelled_at_the_broker_is_dead(self):
        got = rule(record(), Evidence(completed_status="Cancelled"))
        self.assertTrue(got.is_dead)
        self.assertEqual(got.detail, "Cancelled")

    def test_absent_everywhere_is_dead(self):
        """The nine-day silent failure: submitted, echoed fine, existed nowhere."""
        got = rule(record(), Evidence())
        self.assertTrue(got.is_dead)
        self.assertEqual(got.detail, "not_found_anywhere")


class VerifyTests(unittest.TestCase):
    def test_evidence_is_gathered_once_for_the_whole_batch(self):
        """Per-record broker queries trip rate limits."""
        calls = []

        def gather(records):
            calls.append(len(records))
            return {r.event_id: Evidence(has_fill=True) for r in records}

        verify([record(event_id="a"), record(event_id="b")], now=NOW, gather=gather)
        self.assertEqual(calls, [2])

    def test_nothing_due_means_no_broker_call_at_all(self):
        def gather(records):  # pragma: no cover
            raise AssertionError("must not connect when nothing is due")

        self.assertEqual(verify([record(status="entry_verified")], now=NOW, gather=gather), [])

    def test_a_failed_read_aborts_and_writes_no_verdict(self):
        """Verdicts you could not substantiate are worse than no verification."""
        def gather(records):
            raise RuntimeError("socket closed")

        with self.assertRaises(RuntimeError):
            verify([record()], now=NOW, gather=gather)


if __name__ == "__main__":
    unittest.main()
