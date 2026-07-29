"""Outbox — the guarantee is 'never twice', and it must fail closed."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from broker_converger import ExecutionOutbox


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.box = ExecutionOutbox(Path(self._dir.name) / "outbox.jsonl")

    def test_a_decision_can_only_be_reserved_once(self):
        self.assertTrue(self.box.reserve("d1"))
        self.assertFalse(self.box.reserve("d1"))

    def test_reservation_survives_a_new_process(self):
        """The whole point: a restart must not re-send the same decision."""
        self.box.reserve("d1")
        self.assertFalse(ExecutionOutbox(self.box.path).reserve("d1"))

    def test_an_empty_id_is_refused(self):
        """Unidentifiable decisions cannot be de-duplicated, so they don't pass."""
        self.assertFalse(self.box.reserve(""))

    def test_marking_clears_it_from_pending(self):
        self.box.reserve("d1", {"note": "x"})
        self.assertEqual([p["event_id"] for p in self.box.pending()], ["d1"])
        self.box.mark("d1", status="submitted")
        self.assertEqual(self.box.pending(), [])

    def test_a_crash_between_reserve_and_mark_is_findable(self):
        self.box.reserve("d1")
        self.box.reserve("d2")
        self.box.mark("d2", status="submitted")
        self.assertEqual([p["event_id"] for p in self.box.pending()], ["d1"])

    def test_a_torn_line_does_not_make_the_log_fail_open(self):
        """A partial write from a crash must not let a duplicate through."""
        self.box.reserve("d1")
        with self.box.path.open("a", encoding="utf-8") as handle:
            handle.write('{"status": "reser')
        self.assertFalse(self.box.reserve("d1"))


if __name__ == "__main__":
    unittest.main()
