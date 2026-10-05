"""Whole-operation read deadlines, cancellation and single-lane quarantine."""

import time
from threading import Event, Thread
from unittest import TestCase

from mos_eisley.conversation_schedule_handlers import (
    ScheduleHandlerError,
    ScheduleReads,
)


class HandlerTests(TestCase):
    def test_hung_read_returns_boundedly_and_rejects_replacement_until_finished(
        self,
    ) -> None:
        reads = ScheduleReads(0.04)
        release, finished = Event(), Event()
        calls: list[str] = []

        def hung() -> str:
            calls.append("started")
            release.wait(2)
            finished.set()
            return "late result"

        start = time.monotonic()
        try:
            with self.assertRaises(ScheduleHandlerError):
                reads.call(hung)
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertTrue(reads.blocked)
            with self.assertRaises(ScheduleHandlerError):
                reads.call(hung)
            with self.assertRaises(ScheduleHandlerError):
                reads.reset()
            self.assertEqual(calls, ["started"])
        finally:
            release.set()
        self.assertTrue(finished.wait(1))
        # Wait for the worker to publish completion, not merely its callback exit.
        deadline = time.monotonic() + 1
        while True:
            try:
                reads.reset()
                break
            except ScheduleHandlerError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.001)
        self.assertEqual(reads.call(lambda: "fresh"), "fresh")

    def test_cancellation_invalidates_owner_operation_and_discards_late_result(
        self,
    ) -> None:
        reads = ScheduleReads(1)
        entered, release, ended = Event(), Event(), Event()
        errors: list[Exception] = []

        def read() -> int:
            entered.set()
            release.wait(2)
            return 7

        def owner() -> None:
            try:
                reads.call(read)
            except Exception as error:
                errors.append(error)
            finally:
                ended.set()

        worker = Thread(target=owner)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            reads.cancel()
            self.assertTrue(ended.wait(0.5))
            self.assertIsInstance(errors[0], ScheduleHandlerError)
            self.assertTrue(reads.blocked)
        finally:
            release.set()
            worker.join(1)

    def test_multiple_reads_share_one_deadline_and_nested_operations(self) -> None:
        reads = ScheduleReads(0.08)

        def delayed() -> int:
            time.sleep(0.05)
            return 1

        with reads.operation():
            self.assertEqual(reads.call(delayed), 1)
            with self.assertRaises(ScheduleHandlerError), reads.operation():
                reads.call(delayed)

    def test_failure_messages_are_bounded_and_do_not_expose_callback_content(
        self,
    ) -> None:
        reads = ScheduleReads()
        for error in (
            ValueError("private artifact"),
            OSError("secret path"),
            TimeoutError("secret"),
        ):

            def fail(error: Exception = error) -> None:
                raise error

            with self.assertRaises(ScheduleHandlerError) as caught:
                reads.call(fail)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("private", str(caught.exception))
            reads.reset()
        for timeout in (0, -1, float("inf"), float("nan"), 11):
            with self.assertRaises(ValueError):
                ScheduleReads(timeout)
