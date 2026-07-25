import unittest

from stock_strategy.job_lifecycle import (
    ALLOWED_JOB_TRANSITIONS,
    InvalidJobTransition,
    JobStatus,
    TERMINAL_JOB_STATUSES,
    validate_job_transition,
)


class JobLifecycleTest(unittest.TestCase):
    def test_happy_paths_and_terminal_states_are_explicit(self):
        validate_job_transition("queued", "running")
        validate_job_transition("running", "succeeded")
        validate_job_transition("running", "cancelling")
        validate_job_transition("cancelling", "cancelled")
        self.assertEqual(
            TERMINAL_JOB_STATUSES,
            {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED},
        )
        for status in TERMINAL_JOB_STATUSES:
            self.assertEqual(ALLOWED_JOB_TRANSITIONS[status], frozenset())

    def test_illegal_rewind_and_unknown_status_are_rejected(self):
        with self.assertRaisesRegex(
            InvalidJobTransition,
            "cannot transition from succeeded to running",
        ):
            validate_job_transition("succeeded", "running")
        with self.assertRaisesRegex(InvalidJobTransition, "unknown job status"):
            validate_job_transition("mystery", "failed")


if __name__ == "__main__":
    unittest.main()
