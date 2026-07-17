"""Existing-content awareness for blog-pipeline.

Lists the slugs already published on the target site and dedupes new topic
candidates against them, so a run never proposes a topic the site already
covers. Pure functions throughout: list_slugs / normalize / dedupe each take
plain inputs and return plain outputs with no side effects.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from config import ConfigError, load_config

# Content file extensions that carry one blog per file (stem == slug).
CONTENT_EXTENSIONS = (".json", ".md", ".mdx")

# Token-set (Jaccard) similarity at or above this drops a candidate as a
# near-duplicate of an existing slug.
SIMILARITY_THRESHOLD = 0.8

# Reasons attached to dropped candidates.
DROPPED_EXACT_SLUG = "exact slug match"
DROPPED_SIMILAR_TITLE = "title too similar to existing slug"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize(text) -> str:
    """Lowercase and collapse every non-alphanumeric run to a single hyphen."""
    return _NON_ALNUM_RE.sub("-", str(text or "").lower()).strip("-")


def list_slugs(content_dir: str | Path) -> list[str]:
    """Slugs of existing posts: content-file stems, sorted and deduped."""
    directory = Path(content_dir)
    if not directory.is_dir():
        return []
    slugs = {
        path.stem
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in CONTENT_EXTENSIONS
    }
    return sorted(slugs)


def _tokens(slug: str) -> frozenset:
    return frozenset(t for t in normalize(slug).split("-") if t)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe(candidates: list, existing_slugs: list) -> tuple[list, list]:
    """Split candidates into (fresh, dropped) against existing slugs.

    A candidate is dropped when its slug (or normalized title) exactly matches
    an existing slug, or when the Jaccard overlap between its normalized title
    tokens and any existing slug's tokens reaches SIMILARITY_THRESHOLD.
    Dropped candidates get a "droppedBecause" explanation attached.
    """
    existing = [normalize(s) for s in existing_slugs]
    existing_token_sets = [(s, _tokens(s)) for s in existing]

    fresh: list = []
    dropped: list = []
    for candidate in candidates:
        slug = normalize(candidate.get("slug", ""))
        title_slug = normalize(candidate.get("title", ""))

        reason = None
        if slug and slug in existing:
            reason = f"{DROPPED_EXACT_SLUG}: {slug}"
        elif title_slug and title_slug in existing:
            reason = f"{DROPPED_EXACT_SLUG}: {title_slug}"
        else:
            title_tokens = _tokens(title_slug)
            for existing_slug, tokens in existing_token_sets:
                score = _jaccard(title_tokens, tokens)
                if score >= SIMILARITY_THRESHOLD:
                    reason = (
                        f"{DROPPED_SIMILAR_TITLE}: {existing_slug} "
                        f"(overlap {score:.2f})"
                    )
                    break

        if reason is None:
            fresh.append(candidate)
        else:
            dropped.append({**candidate, "droppedBecause": reason})
    return fresh, dropped


def main(argv):
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print("usage: existing.py <target-repo-path>   # list existing blog slugs")
        return 2
    try:
        cfg = load_config(argv[1])
    except ConfigError as exc:
        print("INVALID CONFIG:")
        print(exc)
        return 1
    content_dir = Path(cfg["target"]["repoPath"]) / cfg["target"]["contentDir"]
    slugs = list_slugs(content_dir)
    print(f"{len(slugs)} existing slug(s) in {content_dir}")
    for slug in slugs:
        print(f"  {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
