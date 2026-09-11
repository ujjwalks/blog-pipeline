"""Tests for scripts/existing.py: content loading and candidate dedupe."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from existing import (  # noqa: E402
    PostRecord,
    dedupe,
    find_duplicate,
    list_slugs,
    load_post_records,
    normalize,
)


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


class TestLoadPostRecords(unittest.TestCase):
    def test_loads_json_fields_and_falls_back_to_filename_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp)
            (content / "fallback-slug.json").write_text(
                json.dumps(
                    {
                        "title": "AI Controls",
                        "excerpt": "Verify automated output",
                        "tags": ["AI", "audit trail"],
                    }
                )
            )

            self.assertEqual(
                load_post_records(content),
                [
                    PostRecord(
                        "fallback-slug",
                        "AI Controls",
                        "Verify automated output",
                        ("AI", "audit trail"),
                    )
                ],
            )

    def test_loads_markdown_and_mdx_frontmatter_and_sorts_by_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp)
            (content / "zeta.mdx").write_text(
                """---
slug: custom-zeta
title: \"Zeta Close\"
excerpt: 'A month-end checklist'
tags: [close, accounting]
---
# Body
"""
            )
            (content / "alpha.md").write_text(
                """---
title: Alpha AI
excerpt: Verify output
tags:
  - AI
  - audit trail
---
# Body
"""
            )

            self.assertEqual(
                load_post_records(content),
                [
                    PostRecord(
                        "alpha",
                        "Alpha AI",
                        "Verify output",
                        ("AI", "audit trail"),
                    ),
                    PostRecord(
                        "custom-zeta",
                        "Zeta Close",
                        "A month-end checklist",
                        ("close", "accounting"),
                    ),
                ],
            )


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

    def test_dropped_entry_includes_auditable_match_fields(self):
        fresh, dropped = dedupe([{"slug": "monthly-close-checklist", "title": "Monthly Close Checklist"}], ["monthly-close-checklist"])
        self.assertEqual(fresh, [])
        self.assertEqual(dropped[0]["duplicateSource"], "published")
        self.assertEqual(dropped[0]["duplicateSlug"], "monthly-close-checklist")
        self.assertIn("duplicateScore", dropped[0])
        self.assertEqual(dropped[0]["duplicateReason"], "exact identity")

    def test_legacy_title_identity_rejects_material_update(self):
        candidate = {"slug": "monthly-close-checklist-2026-update", "title": "Monthly Close Checklist", "materialUpdate": {"date": "2026-07-28", "summary": "revised"}}
        fresh, dropped = dedupe([candidate], ["monthly-close-checklist"])
        self.assertEqual(fresh, [])
        self.assertEqual(dropped[0]["duplicateReason"], "exact identity")


class TestFindDuplicate(unittest.TestCase):
    def test_exact_identity_wins_over_earlier_semantic_tie(self):
        posts = [
            PostRecord("finance-ai", "Finance AI", "Overview", ("Finance AI",)),
            PostRecord("target-post", "Target Post", "Overview", ("Target Post",)),
        ]
        match = find_duplicate({"slug": "new-target", "title": "Target Post", "primaryKeyword": "Finance AI"}, posts, [], 0.5)
        self.assertEqual(match.slug, "target-post")
        self.assertEqual(match.reason, "exact identity")
    def test_finds_overlap_from_title_excerpt_and_keyword(self):
        posts = [
            PostRecord(
                "ai-finance-controls",
                "AI Finance Controls",
                "How to verify AI output",
                ("audit trail",),
            )
        ]
        candidate = {
            "slug": "controls-for-ai-finance",
            "title": "Controls for AI Finance",
            "intentSummary": "verify AI finance output with an audit trail",
            "primaryKeyword": "AI finance controls",
        }

        match = find_duplicate(candidate, posts, [], 0.50)

        self.assertIsNotNone(match)
        self.assertEqual(match.slug, "ai-finance-controls")
        self.assertEqual(match.source, "published")
        self.assertEqual(match.reason, "intent overlap")

    def test_rejects_recent_unpublished_topic(self):
        candidate = {
            "slug": "quickbooks-chatgpt",
            "title": "QuickBooks in ChatGPT",
            "intentSummary": "connect QuickBooks and ChatGPT",
            "primaryKeyword": "QuickBooks ChatGPT",
        }
        recent_topics = [
            {
                "slug": "quickbooks-in-chatgpt",
                "title": "QuickBooks inside ChatGPT",
                "intentSummary": "connect QuickBooks and ChatGPT",
            }
        ]

        match = find_duplicate(candidate, [], recent_topics, 0.60)

        self.assertIsNotNone(match)
        self.assertEqual(match.source, "recent-run")

    def test_dated_material_update_can_bypass_keyword_driven_similarity(self):
        posts = [
            PostRecord(
                "quickbooks-ai",
                "QuickBooks AI",
                "Available AI features",
                ("QuickBooks AI",),
            )
        ]
        candidate = {
            "slug": "quickbooks-ai-2026-update",
            "title": "QuickBooks AI 2026 Update",
            "intentSummary": "new July 2026 capabilities",
            "primaryKeyword": "QuickBooks AI",
            "materialUpdate": {
                "date": "2026-07-28",
                "summary": "transactional actions launched",
            },
        }

        self.assertIsNone(find_duplicate(candidate, posts, [], 0.40))

    def test_material_update_never_bypasses_exact_slug_or_title(self):
        posts = [
            PostRecord(
                "quickbooks-ai",
                "QuickBooks AI",
                "Available AI features",
                ("QuickBooks AI",),
            )
        ]
        update = {
            "date": "2026-07-28",
            "summary": "transactional actions launched",
        }

        slug_match = find_duplicate(
            {
                "slug": "quickbooks-ai",
                "title": "QuickBooks AI 2026 Update",
                "intentSummary": "new transactional actions",
                "primaryKeyword": "QuickBooks AI",
                "materialUpdate": update,
            },
            posts,
            [],
            0.40,
        )
        title_match = find_duplicate(
            {
                "slug": "quickbooks-ai-2026-update",
                "title": "QuickBooks AI",
                "intentSummary": "new transactional actions",
                "primaryKeyword": "QuickBooks AI",
                "materialUpdate": update,
            },
            posts,
            [],
            0.40,
        )

        self.assertEqual(slug_match.reason, "exact identity")
        self.assertEqual(title_match.reason, "exact identity")

    def test_material_update_requires_update_title_date_and_summary(self):
        posts = [
            PostRecord(
                "quickbooks-ai",
                "QuickBooks AI",
                "Available AI features",
                ("QuickBooks AI",),
            )
        ]
        base = {
            "slug": "quickbooks-ai-2026-update",
            "title": "QuickBooks AI 2026 Update",
            "intentSummary": "new July 2026 capabilities",
            "primaryKeyword": "QuickBooks AI",
        }
        incomplete_updates = [
            {
                **base,
                "title": "QuickBooks AI capabilities",
                "materialUpdate": {"date": "2026-07-28", "summary": "launched"},
            },
            {**base, "materialUpdate": {"summary": "launched"}},
            {**base, "materialUpdate": {"date": "2026-07-28"}},
            {**base, "materialUpdate": {"date": "", "summary": "launched"}},
            {**base, "materialUpdate": {"date": "2026-07-28", "summary": "  "}},
        ]

        for candidate in incomplete_updates:
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(find_duplicate(candidate, posts, [], 0.40))

    def test_material_update_requires_iso_date(self):
        posts = [PostRecord("quickbooks-ai", "QuickBooks AI", "Available AI features", ("QuickBooks AI",))]
        candidate = {
            "slug": "quickbooks-ai-2026-update", "title": "QuickBooks AI 2026 Update",
            "intentSummary": "new July 2026 capabilities", "primaryKeyword": "QuickBooks AI",
            "materialUpdate": {"date": "July 28, 2026", "summary": "transactional actions launched"},
        }
        self.assertIsNotNone(find_duplicate(candidate, posts, [], 0.40))

    def test_material_update_rejects_impossible_iso_date(self):
        posts = [PostRecord("quickbooks-ai", "QuickBooks AI", "Available AI features", ("QuickBooks AI",))]
        candidate = {"slug": "quickbooks-ai-2026-update", "title": "QuickBooks AI 2026 Update", "intentSummary": "new July capabilities", "primaryKeyword": "QuickBooks AI", "materialUpdate": {"date": "2026-99-99", "summary": "launched"}}
        self.assertIsNotNone(find_duplicate(candidate, posts, [], 0.40))

    def test_material_update_residual_intent_ignores_shared_primary_keyword(self):
        posts = [PostRecord("quickbooks-ai", "QuickBooks AI", "Available features", ("QuickBooks AI",))]
        candidate = {
            "slug": "quickbooks-ai-2026-update", "title": "QuickBooks AI 2026 Update",
            "intentSummary": "new transactional automation capabilities", "primaryKeyword": "QuickBooks AI",
            "materialUpdate": {"date": "2026-07-28", "summary": "transactional actions launched"},
        }
        self.assertIsNone(find_duplicate(candidate, posts, [], 0.40))

    def test_material_update_uses_selected_record_when_slug_collides(self):
        posts = [PostRecord("same-slug", "Old Topic", "Legacy intent", ("shared",))]
        recent = [{"slug": "same-slug", "title": "New Topic", "intentSummary": "new intent", "primaryKeyword": "new"}]
        candidate = {"slug": "new-candidate", "title": "New Topic 2026 Update", "intentSummary": "new intent", "primaryKeyword": "new", "materialUpdate": {"date": "2026-07-28", "summary": "launched"}}
        match = find_duplicate(candidate, posts, recent, 0.4)
        self.assertIsNotNone(match)
        self.assertEqual(match.source, "recent-run")

    def test_material_update_keyword_only_intent_is_not_treated_as_residual_overlap(self):
        posts = [PostRecord("quickbooks-ai", "QuickBooks AI", "Available features", ("QuickBooks AI",))]
        candidate = {"slug": "quickbooks-ai-2026-update", "title": "QuickBooks AI 2026 Update", "intentSummary": "QuickBooks AI", "primaryKeyword": "QuickBooks AI", "materialUpdate": {"date": "2026-07-28", "summary": "launched"}}
        self.assertIsNone(find_duplicate(candidate, posts, [], 0.4))

    def test_material_update_does_not_bypass_similar_residual_intent(self):
        posts = [
            PostRecord(
                "quickbooks-ai",
                "QuickBooks AI",
                "Available AI features",
                ("QuickBooks AI",),
            )
        ]
        candidate = {
            "slug": "quickbooks-ai-2026-update",
            "title": "QuickBooks AI 2026 Update",
            "intentSummary": "available AI features updated",
            "primaryKeyword": "QuickBooks AI",
            "materialUpdate": {
                "date": "2026-07-28",
                "summary": "feature availability changed",
            },
        }

        self.assertIsNotNone(find_duplicate(candidate, posts, [], 0.40))


if __name__ == "__main__":
    unittest.main()
