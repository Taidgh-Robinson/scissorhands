from dataclasses import replace
from datetime import datetime
from unittest import TestCase

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.status import CriterionStatus
from scissorhands.core.verification import CommandResult, VerificationResult
from scissorhands.storage.receipts import receipt_data

COMPLETE = IterationRecord(
    iteration=1,
    agent="opencode",
    agent_exit_code=0,
    statuses=(CriterionStatus("AC-1", "Works.", True, "Checked."),),
    status_updated=True,
    progress="Done.",
    progress_updated=True,
    verification=None,
    verification_required=False,
    marker_claimed=True,
    final_iteration=False,
)
FAILURE = VerificationResult((CommandResult("make test", 1, "failed"),))


class IterationDecisionTests(TestCase):
    def test_gate_precedence_and_iteration_limit(self) -> None:
        cases = [
            (COMPLETE, "completed"),
            (replace(COMPLETE, final_iteration=True), "completed"),
            (replace(COMPLETE, marker_claimed=False), "continuing"),
            (
                replace(COMPLETE, marker_claimed=False, final_iteration=True),
                "iteration_limit",
            ),
            (replace(COMPLETE, status_updated=False), "criteria_rejected"),
            (replace(COMPLETE, statuses=None), "criteria_rejected"),
            (
                replace(
                    COMPLETE, statuses=(CriterionStatus("AC-1", "Works.", True, ""),)
                ),
                "criteria_rejected",
            ),
            (
                replace(
                    COMPLETE,
                    verification=FAILURE,
                    status_updated=False,
                    final_iteration=True,
                ),
                "verification_failed",
            ),
            (
                replace(COMPLETE, agent_exit_code=7, verification=FAILURE),
                "agent_failed",
            ),
        ]
        for record, outcome in cases:
            with self.subTest(outcome=outcome, record=record):
                self.assertEqual(record.decision.outcome, outcome)
                self.assertEqual(record.decision.accepted, outcome == "completed")

    def test_feedback_clears_after_verification_passes(self) -> None:
        failed = replace(COMPLETE, verification=FAILURE)
        self.assertIn("failed", failed.verification_feedback)
        passed = replace(
            failed,
            verification=VerificationResult((CommandResult("make test", 0, "passed"),)),
        )
        self.assertIsNone(passed.verification_feedback)


class ReceiptFormatTests(TestCase):
    def test_receipt_preserves_public_schema(self) -> None:
        record = replace(COMPLETE, verification=FAILURE, verification_required=True)
        data = receipt_data(record)
        timestamp = datetime.fromisoformat(data.pop("recorded_at"))
        self.assertIsNotNone(timestamp.tzinfo)
        self.assertEqual(
            data,
            {
                "iteration": 1,
                "agent": "opencode",
                "agent_exit_code": 0,
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": None,
                "agent_elapsed_seconds": None,
                "verification_elapsed_seconds": None,
                "git_before_tree": None,
                "git_after_tree": None,
                "outcome": "verification_failed",
                "rejection_reason": "verification failed",
                "progress_updated": True,
                "progress": "Done.",
                "status_updated": True,
                "status_readable": True,
                "criteria": [
                    {
                        "id": "AC-1",
                        "text": "Works.",
                        "met": True,
                        "evidence": "Checked.",
                    },
                ],
                "verification": {
                    "required": True,
                    "passed": False,
                    "commands": [
                        {"command": "make test", "return_code": 1, "passed": False}
                    ],
                },
                "completion_marker_claimed": True,
                "completion_accepted": False,
            },
        )

    def test_unreadable_status_and_skipped_verification_keep_null_semantics(
        self,
    ) -> None:
        data = receipt_data(replace(COMPLETE, agent_exit_code=7, statuses=None))
        self.assertFalse(data["status_readable"])
        self.assertEqual(data["criteria"], [])
        self.assertEqual(
            data["verification"],
            {
                "required": False,
                "passed": None,
                "commands": [],
            },
        )
        self.assertEqual(data["outcome"], "agent_failed")
        self.assertFalse(data["completion_accepted"])
