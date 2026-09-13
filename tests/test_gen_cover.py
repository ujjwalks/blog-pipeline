import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gen_cover


class TestBuildHtml(unittest.TestCase):
    def test_uses_compact_tag_without_rendering_headline(self):
        html = gen_cover.build_html("A very long post title that belongs in page metadata", "For CPAs", "#7C3AED")
        self.assertNotIn("A very long post title", html)
        self.assertIn("For CPAs", html)
        self.assertIn("#7C3AED", html)

    def test_long_title_does_not_change_cover_layout(self):
        short = gen_cover.build_html("Short", "T", "#000000")
        long = gen_cover.build_html("x" * 90, "T", "#000000")
        self.assertEqual(short, long)

    def test_brand_split(self):
        html = gen_cover.build_html("T", "T", "#000000")
        self.assertIn("Fin<b>Board</b>", html)

    def test_no_chrome_needed_for_build(self):
        # build_html is pure; it must never touch subprocess.
        html = gen_cover.build_html("T", "T", "#123456")
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main()
