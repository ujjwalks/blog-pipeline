"""Deterministic content gate for blog-pipeline.

A generated blog file must pass validate_file() before it may be committed.
The checks are format-aware (json vs md/mdx per target.blogFormat) plus a
prose-cleanliness rule that applies everywhere: no AI-tell punctuation
(em/en dashes, curly quotes) or their HTML entities. Pure function core;
the CLI is a thin wrapper that loads config and existing slugs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from config import BLOG_FORMATS, ConfigError, load_config
from existing import list_slugs

# --- Gate thresholds ---

MIN_CONTENT_CHARS = 4000

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# JSON blog fields that must be present and non-empty strings.
REQUIRED_TEXT_FIELDS = (
    "slug",
    "title",
    "category",
    "excerpt",
    "author",
    "date",
    "format",
    "content",
)

# Required too, but with looser typing (structuredData may be a dict,
# order may be a number). coverImage must still be a string.
REQUIRED_OTHER_FIELDS = ("coverImage", "coverAlt", "order", "structuredData")

# --- Prose cleanliness (house rule: human-sounding prose) ---

BANNED_SEQUENCES = (
    ("—", "em dash"),
    ("–", "en dash"),
    ("’", "curly right single quote"),
    ("‘", "curly left single quote"),
    ("“", "curly left double quote"),
    ("”", "curly right double quote"),
    ("&mdash;", "em dash entity"),
    ("&ndash;", "en dash entity"),
    ("&ldquo;", "left double quote entity"),
    ("&rdquo;", "right double quote entity"),
    ("&rsquo;", "right single quote entity"),
)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_REQUIRED_KEYS = ("title", "date", "category")


def check_cleanliness(text: str, where: str) -> list:
    """Return one problem per banned sequence found, with its count."""
    problems: list = []
    for sequence, label in BANNED_SEQUENCES:
        count = text.count(sequence)
        if count:
            problems.append(f"{where}: contains {label} {sequence!r} x{count}")
    return problems


def _validate_json_blog(path: Path, raw: str, cfg: dict, existing_slugs: list) -> list:
    problems: list = []
    try:
        blog = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"not valid JSON: {exc}"]
    if not isinstance(blog, dict):
        return ["JSON root must be an object"]

    for field in REQUIRED_TEXT_FIELDS:
        value = blog.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field}: required non-empty string")
    for field in REQUIRED_OTHER_FIELDS:
        if field not in blog:
            problems.append(f"{field}: required")
    cover = blog.get("coverImage")
    if "coverImage" in blog and not isinstance(cover, str):
        problems.append("coverImage: must be a string")

    slug = blog.get("slug")
    if isinstance(slug, str) and slug and slug != path.stem:
        problems.append(f"slug {slug!r} does not match filename stem {path.stem!r}")
    if isinstance(slug, str) and slug in existing_slugs:
        problems.append(f"slug {slug!r} already exists on the site")

    category = blog.get("category")
    categories = cfg.get("target", {}).get("categories", [])
    if isinstance(category, str) and category and category not in categories:
        problems.append(f"category {category!r} not in {categories}")

    date = blog.get("date")
    if isinstance(date, str) and date and not DATE_RE.match(date):
        problems.append(f"date {date!r} must be YYYY-MM-DD")

    content = blog.get("content")
    if isinstance(content, str) and len(content) < MIN_CONTENT_CHARS:
        problems.append(
            f"content too short: {len(content)} chars (need >= {MIN_CONTENT_CHARS})"
        )

    if isinstance(content, str):
        problems.extend(check_cleanliness(content, "content"))
    excerpt = blog.get("excerpt")
    if isinstance(excerpt, str):
        problems.extend(check_cleanliness(excerpt, "excerpt"))
    return problems


def _validate_markdown_blog(raw: str) -> list:
    problems: list = []
    match = FRONTMATTER_RE.match(raw)
    if not match:
        problems.append("missing leading YAML frontmatter block (--- ... ---)")
        body = raw
    else:
        frontmatter = match.group(1)
        for key in FRONTMATTER_REQUIRED_KEYS:
            if not re.search(rf"^{key}\s*:\s*\S", frontmatter, re.MULTILINE):
                problems.append(f"frontmatter missing {key}:")
        body = raw[match.end():]
    problems.extend(check_cleanliness(body, "content"))
    return problems


def validate_file(path: str | Path, cfg: dict, existing_slugs: list) -> list:
    """Validate one generated blog file. Empty list == valid."""
    path = Path(path)
    if not path.is_file():
        return [f"file not found: {path}"]
    raw = path.read_text()

    fmt = cfg.get("target", {}).get("blogFormat")
    if fmt not in BLOG_FORMATS:
        return [f"target.blogFormat {fmt!r} not in {list(BLOG_FORMATS)}"]
    if fmt == "json":
        return _validate_json_blog(path, raw, cfg, existing_slugs)
    return _validate_markdown_blog(raw)


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print("usage: validate_blog.py <target-repo-path> <blog-file> [more files...]")
        return 2
    try:
        cfg = load_config(argv[1])
    except ConfigError as exc:
        print("INVALID CONFIG:")
        print(exc)
        return 1

    content_dir = Path(cfg["target"]["repoPath"]) / cfg["target"]["contentDir"]
    existing = set(list_slugs(content_dir))

    any_invalid = False
    for arg in argv[2:]:
        path = Path(arg)
        # A file already sitting in the content dir must not fail against itself.
        slugs = sorted(existing - {path.stem})
        problems = validate_file(path, cfg, slugs)
        if problems:
            any_invalid = True
            print(f"FAIL {path}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK   {path}")
    return 1 if any_invalid else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
