"""Tests for scripts/validate_blog.py: the deterministic pre-commit gate."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from config import validate_config  # noqa: E402
from validate_blog import MIN_CONTENT_CHARS, validate_file  # noqa: E402


def make_config(blog_format="json"):
    """Minimal config kept honest against config.validate_config."""
    cfg = {
        "target": {
            "repoPath": "/tmp/x",
            "contentDir": "content/blog",
            "blogFormat": blog_format,
            "categories": ["accounting"],
        },
        "personas": [{"id": "controller", "name": "The Controller"}],
        "reviewChannel": {"type": "cli"},
        "review": {"mode": "vercel-preview"},
        "deploy": {"mode": "git-push", "remote": "origin", "target": "main"},
    }
    errors = validate_config(cfg)
    assert not errors, f"fixture config must be valid, got: {errors}"
    return cfg


def make_blog(**overrides):
    blog = {
        "slug": "monthly-close-checklist",
        "title": "The Monthly Close Checklist",
        "category": "accounting",
        "excerpt": "A practical close checklist for small accounting teams.",
        "author": "controller",
        "date": "2026-07-18",
        "format": "json",
        "content": "Close the books faster. " * (MIN_CONTENT_CHARS // 20),
        "coverImage": "/images/blog/monthly-close-checklist.png",
        "coverAlt": "A desk calendar marked with close dates",
        "order": 1,
        "structuredData": {"@type": "Article"},
    }
    blog.update(overrides)
    return blog


class ValidateBlogTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg = make_config()

    def tearDown(self):
        self._tmp.cleanup()

    def write_json_blog(self, blog, filename=None):
        path = self.tmp / (filename or f"{blog['slug']}.json")
        path.write_text(json.dumps(blog))
        return path

    # --- JSON format ---

    def test_valid_json_blog_passes(self):
        path = self.write_json_blog(make_blog())
        self.assertEqual(validate_file(path, self.cfg, []), [])

    def test_missing_field_fails(self):
        blog = make_blog()
        del blog["excerpt"]
        path = self.write_json_blog(blog)
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("excerpt" in p for p in problems))

    def test_bad_category_fails(self):
        path = self.write_json_blog(make_blog(category="astrology"))
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("category" in p for p in problems))

    def test_duplicate_slug_fails(self):
        path = self.write_json_blog(make_blog())
        problems = validate_file(path, self.cfg, ["monthly-close-checklist"])
        self.assertTrue(any("already exists" in p for p in problems))

    def test_slug_filename_mismatch_fails(self):
        path = self.write_json_blog(make_blog(), filename="some-other-name.json")
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("filename stem" in p for p in problems))

    def test_bad_date_fails(self):
        path = self.write_json_blog(make_blog(date="July 18, 2026"))
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("YYYY-MM-DD" in p for p in problems))

    def test_short_content_fails(self):
        path = self.write_json_blog(make_blog(content="Too short."))
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("too short" in p for p in problems))

    def test_not_json_fails(self):
        path = self.tmp / "monthly-close-checklist.json"
        path.write_text("{not json")
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("not valid JSON" in p for p in problems))

    # --- Prose cleanliness ---

    def test_em_dash_in_content_fails_with_count(self):
        blog = make_blog()
        blog["content"] += " one — two — three"
        path = self.write_json_blog(blog)
        problems = validate_file(path, self.cfg, [])
        matches = [p for p in problems if "em dash" in p]
        self.assertEqual(len(matches), 1)
        self.assertIn("x2", matches[0])

    def test_curly_apostrophe_fails(self):
        blog = make_blog()
        blog["content"] += " it’s fine"
        path = self.write_json_blog(blog)
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("curly right single quote" in p for p in problems))

    def test_mdash_entity_fails(self):
        blog = make_blog()
        blog["content"] += " a&mdash;b"
        path = self.write_json_blog(blog)
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any("em dash entity" in p for p in problems))

    def test_curly_quote_in_excerpt_fails(self):
        blog = make_blog(excerpt="“Quoted” excerpt here.")
        path = self.write_json_blog(blog)
        problems = validate_file(path, self.cfg, [])
        self.assertTrue(any(p.startswith("excerpt:") for p in problems))

    # --- Markdown formats ---

    def test_md_with_frontmatter_passes(self):
        cfg = make_config(blog_format="md")
        path = self.tmp / "monthly-close-checklist.md"
        path.write_text(
            "---\n"
            "title: The Monthly Close Checklist\n"
            "date: 2026-07-18\n"
            "category: accounting\n"
            "---\n"
            "Close the books faster with a repeatable checklist.\n"
        )
        self.assertEqual(validate_file(path, cfg, []), [])

    def test_md_missing_frontmatter_fails(self):
        cfg = make_config(blog_format="md")
        path = self.tmp / "monthly-close-checklist.md"
        path.write_text("Just a body with no frontmatter.\n")
        problems = validate_file(path, cfg, [])
        self.assertTrue(any("frontmatter" in p for p in problems))

    def test_md_body_cleanliness_enforced(self):
        cfg = make_config(blog_format="md")
        path = self.tmp / "monthly-close-checklist.md"
        path.write_text(
            "---\n"
            "title: T\n"
            "date: 2026-07-18\n"
            "category: accounting\n"
            "---\n"
            "A body with an em dash — right here.\n"
        )
        problems = validate_file(path, cfg, [])
        self.assertTrue(any("em dash" in p for p in problems))

    def test_missing_file_fails(self):
        problems = validate_file(self.tmp / "nope.json", self.cfg, [])
        self.assertTrue(any("file not found" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
