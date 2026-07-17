"""Tests for scripts/existing.py: slug listing and candidate dedupe."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from existing import dedupe, list_slugs, normalize  # noqa: E402


class TestListSlugs(unittest.TestCase):
    def test_lists_json_md_mdx_stems_sorted_and_deduped(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp)
            (content / "zeta-post.json").write_text("{}")
            (content / "alpha-post.md").write_text("# hi")
            (content / "middle-post.mdx").write_text("# hi")
            # Same slug in two formats must appear once.
            (content / "alpha-post.json").write_text("{}")
            # Non-content files are ignored.
            (content / "notes.txt").write_text("ignore")
            (content / "image.png").write_bytes(b"")
            self.assertEqual(
                list_slugs(content),
                ["alpha-post", "middle-post", "zeta-post"],
            )

    def test_missing_directory_returns_empty(self):
        self.assertEqual(list_slugs("/tmp/does-not-exist-blog-pipeline"), [])


class TestNormalize(unittest.TestCase):
    def test_lowercases_and_hyphenates(self):
        self.assertEqual(
            normalize("How to Sync QuickBooks (2026)!"),
            "how-to-sync-quickbooks-2026",
        )

    def test_empty_and_none(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class TestDedupe(unittest.TestCase):
    def test_exact_slug_match_is_dropped(self):
        candidates = [{"title": "Anything", "slug": "monthly-close-checklist"}]
        fresh, dropped = dedupe(candidates, ["monthly-close-checklist"])
        self.assertEqual(fresh, [])
        self.assertEqual(len(dropped), 1)
        self.assertIn("exact slug match", dropped[0]["droppedBecause"])

    def test_normalized_title_exact_match_is_dropped(self):
        candidates = [{"title": "Monthly Close Checklist"}]
        fresh, dropped = dedupe(candidates, ["monthly-close-checklist"])
        self.assertEqual(fresh, [])
        self.assertEqual(len(dropped), 1)

    def test_near_duplicate_title_is_dropped(self):
        candidates = [
            {"title": "How to Combine Reports from Multiple QuickBooks Online Companies"}
        ]
        existing = [
            "how-to-combine-reports-from-multiple-quickbooks-online-companies-compared"
        ]
        fresh, dropped = dedupe(candidates, existing)
        self.assertEqual(fresh, [])
        self.assertEqual(len(dropped), 1)
        self.assertIn("title too similar", dropped[0]["droppedBecause"])

    def test_fresh_candidate_passes(self):
        candidates = [{"title": "Restaurant Payroll Benchmarks for 2026"}]
        existing = [
            "how-to-combine-reports-from-multiple-quickbooks-online-companies-compared",
            "monthly-close-checklist",
        ]
        fresh, dropped = dedupe(candidates, existing)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(dropped, [])
        self.assertNotIn("droppedBecause", fresh[0])

    def test_mixed_batch_splits_correctly(self):
        candidates = [
            {"title": "Monthly Close Checklist"},
            {"title": "Cash Flow Forecasting for Seasonal Businesses"},
        ]
        fresh, dropped = dedupe(candidates, ["monthly-close-checklist"])
        self.assertEqual(len(fresh), 1)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(
            fresh[0]["title"], "Cash Flow Forecasting for Seasonal Businesses"
        )


if __name__ == "__main__":
    unittest.main()
