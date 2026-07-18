import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gen_cover


class TestBuildHtml(unittest.TestCase):
    def test_contains_title_tag_accent(self):
        html = gen_cover.build_html("My Post Title", "For CPAs", "#7C3AED")
        self.assertIn("My Post Title", html)
        self.assertIn("For CPAs", html)
        self.assertIn("#7C3AED", html)

    def test_long_title_shrinks_font(self):
        short = gen_cover.build_html("Short", "T", "#000000")
        long = gen_cover.build_html("x" * 90, "T", "#000000")
        self.assertIn("font-size:54px", short)
        self.assertIn("font-size:46px", long)

    def test_brand_split(self):
        html = gen_cover.build_html("T", "T", "#000000")
        self.assertIn("Fin<b>Board</b>", html)

    def test_no_chrome_needed_for_build(self):
        # build_html is pure; it must never touch subprocess.
        html = gen_cover.build_html("T", "T", "#123456")
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main()
