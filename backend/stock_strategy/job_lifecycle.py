from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
)

ALLOWED_JOB_TRANSITIONS = {
    JobStatus.QUEUED: frozenset(
        {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.CANCELLING,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.CANCELLING: frozenset({JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class InvalidJobTransition(RuntimeError):
    pass


def validate_job_transition(current: str, target: str) -> None:
    try:
        current_status = JobStatus(current)
        target_status = JobStatus(target)
    except ValueError as error:
        raise InvalidJobTransition(f"unknown job status: {error}") from error
    if target_status not in ALLOWED_JOB_TRANSITIONS[current_status]:
        raise InvalidJobTransition(
            f"job cannot transition from {current_status.value} "
            f"to {target_status.value}"
        )
