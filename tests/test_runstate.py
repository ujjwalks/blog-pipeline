import tempfile
import unittest
import sys
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from runstate import (  # noqa: E402
    ALREADY_PUBLISHED,
    AWAITING_CONTENT_APPROVAL,
    AWAITING_TOPIC_APPROVAL,
    COMMITTING,
    DEPLOYING,
    DRAFTING,
    DRY_RUN_VALIDATED,
    FAILED,
    NOTHING_PUBLISHABLE,
    PUBLISHED,
    RESEARCHING,
    SELECTING,
    SKIPPED_LOCKED,
    VALIDATING,
    VERIFYING,
    RunStateError,
    advance,
    create_terminal_run,
    main,
    record_event,
)


class AutoRunStateTest(unittest.TestCase):
    def test_automatic_happy_path_transition_is_legal(self):
        run = {"status": RESEARCHING, "history": []}
        advanced = advance(run, SELECTING, "2026-09-08T12:10:00+05:30")
        self.assertEqual(advanced["status"], SELECTING)

    def test_failure_is_legal_from_non_terminal_state(self):
        run = {"status": SELECTING, "history": []}
        self.assertEqual(advance(run, FAILED)["status"], FAILED)

    def test_record_event_does_not_mutate_input(self):
        run = {"status": SELECTING, "history": []}
        updated = record_event(run, "candidate_scored", "2026-09-08T12:11:00+05:30", {"score": 22})
        self.assertEqual(run["history"], [])
        self.assertEqual(updated["history"][0]["details"]["score"], 22)

    def test_record_event_deep_copies_existing_history_and_new_details(self):
        run = {
            "status": SELECTING,
            "history": [{"event": "scored", "details": {"score": {"value": 22}}}],
        }
        details = {"candidate": {"score": 23}}
        updated = record_event(run, "candidate_selected", "2026-09-08T12:11:00+05:30", details)

        updated["history"][0]["details"]["score"]["value"] = 100
        updated["history"][1]["details"]["candidate"]["score"] = 101
        self.assertEqual(run["history"][0]["details"]["score"]["value"], 22)
        self.assertEqual(details["candidate"]["score"], 23)

        run["history"][0]["details"]["score"]["value"] = 200
        details["candidate"]["score"] = 201
        self.assertEqual(updated["history"][0]["details"]["score"]["value"], 100)
        self.assertEqual(updated["history"][1]["details"]["candidate"]["score"], 101)

    def test_record_event_rejects_non_json_details(self):
        for details in ({"at": datetime.now()}, {"path": Path("/tmp/blog.json")}):
            with self.subTest(details=details):
                with self.assertRaises(RunStateError):
                    record_event({"status": SELECTING, "history": []}, "candidate_scored", "now", details)

    def test_record_event_rejects_sensitive_detail_keys_without_exposing_value(self):
        secret_value = "do-not-print-this-secret"
        with self.assertRaises(RunStateError) as context:
            record_event(
                {"status": SELECTING, "history": []},
                "candidate_scored",
                "now",
                {"metadata": {"SlackWebhookUrl": secret_value}},
            )
        self.assertNotIn(secret_value, str(context.exception))

    def test_advance_does_not_mutate_input(self):
        run = {"status": RESEARCHING, "history": []}
        advanced = advance(run, SELECTING, "2026-09-08T12:10:00+05:30")
        self.assertEqual(run, {"status": RESEARCHING, "history": []})
        self.assertEqual(advanced["history"], [{"status": SELECTING, "at": "2026-09-08T12:10:00+05:30"}])

    def test_advance_deep_copies_existing_history(self):
        run = {
            "status": RESEARCHING,
            "history": [{"event": "scored", "details": {"score": {"value": 22}}}],
        }
        advanced = advance(run, SELECTING)
        advanced["history"][0]["details"]["score"]["value"] = 100
        self.assertEqual(run["history"][0]["details"]["score"]["value"], 22)

        run["history"][0]["details"]["score"]["value"] = 200
        self.assertEqual(advanced["history"][0]["details"]["score"]["value"], 100)

    def test_automatic_happy_path_reaches_published(self):
        run = {"status": RESEARCHING, "history": []}
        for status in (SELECTING, DRAFTING, VALIDATING, COMMITTING, DEPLOYING, VERIFYING, PUBLISHED):
            run = advance(run, status)
        self.assertEqual(run["status"], PUBLISHED)

    def test_dry_run_validation_is_terminal(self):
        run = {"status": VALIDATING, "history": []}
        dry_run = advance(run, DRY_RUN_VALIDATED)
        self.assertEqual(dry_run["status"], DRY_RUN_VALIDATED)
        with self.assertRaises(RunStateError):
            advance(dry_run, COMMITTING)

    def test_startup_terminal_run_is_limited_to_idempotent_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            run = create_terminal_run(
                directory, "2026-09-08-auto", ALREADY_PUBLISHED,
                "2026-09-08T12:10:00+05:30", {"url": "https://example.test/blog/post"},
            )
            self.assertEqual(run["status"], ALREADY_PUBLISHED)
            self.assertEqual(run["history"][0]["details"]["url"], "https://example.test/blog/post")
            skipped = create_terminal_run(directory, "2026-09-09-auto", SKIPPED_LOCKED, "now")
            self.assertEqual(skipped["status"], SKIPPED_LOCKED)
            with self.assertRaises(RunStateError):
                create_terminal_run(directory, "2026-09-10-auto", NOTHING_PUBLISHABLE, "now")

    def test_startup_terminal_run_requires_auto_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            for run_id in ("2026-09-08", "2026-09-08-templates"):
                with self.subTest(run_id=run_id):
                    with self.assertRaises(RunStateError):
                        create_terminal_run(directory, run_id, ALREADY_PUBLISHED, "now")


class ManualRunStateTest(unittest.TestCase):
    def test_manual_happy_path_is_preserved(self):
        run = {"status": RESEARCHING, "history": []}
        for status in (AWAITING_TOPIC_APPROVAL, DRAFTING, AWAITING_CONTENT_APPROVAL, DEPLOYING, PUBLISHED):
            run = advance(run, status)
        self.assertEqual(run["status"], PUBLISHED)


class RunStateCliTest(unittest.TestCase):
    def test_status_display_handles_audit_events(self):
        with tempfile.TemporaryDirectory() as directory:
            create_terminal_run(directory, "2026-09-08-auto", SKIPPED_LOCKED, "2026-09-08T12:10:00+05:30")
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["runstate.py", directory, "2026-09-08-auto"]), 0)
            self.assertIn("skipped_locked", output.getvalue())


if __name__ == "__main__":
    unittest.main()
