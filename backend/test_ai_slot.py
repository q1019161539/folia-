import threading
import time
import unittest

import ai_slot


class AiSlotTests(unittest.TestCase):
    def test_two_heavy_jobs_never_hold_the_slot_at_once(self):
        """The guarantee the slot exists for: ASR and forced alignment must not
        be resident together. 7.7GB beside 3.9GB is what got the ASR killed."""
        overlaps = []
        inside = []
        barrier = threading.Barrier(4)

        def heavy(name):
            barrier.wait()
            with ai_slot.occupy(label=name):
                inside.append(name)
                if len(inside) > 1:
                    overlaps.append(list(inside))
                time.sleep(0.05)
                inside.remove(name)

        threads = [threading.Thread(target=heavy, args=(f"任务{i}",)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(overlaps, [])
        self.assertFalse(ai_slot.busy())

    def test_the_slot_is_released_even_when_the_work_fails(self):
        # A crash mid-alignment must not wedge the pipeline forever.
        with self.assertRaises(RuntimeError):
            with ai_slot.occupy(label="会失败的任务"):
                raise RuntimeError("boom")
        self.assertFalse(ai_slot.busy())
        with ai_slot.occupy(label="后续任务") as waited:
            self.assertLess(waited, 1)

    def test_waiting_work_is_visible_while_it_queues(self):
        started = threading.Event()
        release = threading.Event()

        def holder():
            with ai_slot.occupy(label="整场 ASR"):
                started.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(started.wait(timeout=5))

        waiter_done = threading.Event()

        def waiter():
            with ai_slot.occupy(label="逐字对齐"):
                waiter_done.set()

        second = threading.Thread(target=waiter)
        second.start()
        time.sleep(0.2)
        view = ai_slot.snapshot()
        self.assertTrue(view["busy"])
        self.assertEqual(view["holder"], "整场 ASR")
        self.assertIn("逐字对齐", [item["label"] for item in view["waiting"]])

        release.set()
        thread.join(timeout=5)
        self.assertTrue(waiter_done.wait(timeout=10))
        second.join(timeout=5)
        self.assertEqual(ai_slot.snapshot()["waiting"], [])
        self.assertFalse(ai_slot.busy())

    def test_a_long_wait_is_announced_once_not_repeatedly(self):
        # The notice exists so a queued job does not look stuck; a run with a
        # dozen songs must not produce a dozen of them.
        original = (ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS)
        ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS = 0, 0.02
        calls = []
        release = threading.Event()
        holding = threading.Event()

        def holder():
            with ai_slot.occupy(label="占着"):
                holding.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(holding.wait(timeout=5))

        def waiter():
            with ai_slot.occupy(label="等着", on_wait=calls.append):
                pass

        second = threading.Thread(target=waiter)
        second.start()
        # Long enough for many poll cycles: a notice per cycle would be dozens.
        time.sleep(0.5)
        release.set()
        thread.join(timeout=5)
        second.join(timeout=10)
        ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS = original
        self.assertEqual(len(calls), 1)

    def test_a_failing_notice_does_not_cost_the_caller_its_turn(self):
        original = (ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS)
        ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS = 0, 0.02
        release = threading.Event()
        holding = threading.Event()
        got_through = threading.Event()

        def holder():
            with ai_slot.occupy(label="占着"):
                holding.set()
                release.wait(timeout=5)

        def exploding(_):
            raise RuntimeError("通知失败")

        def waiter():
            with ai_slot.occupy(label="等着", on_wait=exploding):
                got_through.set()

        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(holding.wait(timeout=5))
        second = threading.Thread(target=waiter)
        second.start()
        time.sleep(0.3)
        release.set()
        thread.join(timeout=5)
        self.assertTrue(got_through.wait(timeout=10))
        second.join(timeout=5)
        ai_slot.WAIT_NOTICE_SECONDS, ai_slot.POLL_SECONDS = original


if __name__ == "__main__":
    unittest.main()
