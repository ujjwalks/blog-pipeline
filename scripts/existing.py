"""Existing-content awareness for blog-pipeline.

Lists the slugs already published on the target site and dedupes new topic
candidates against them, so a run never proposes a topic the site already
covers. Pure functions throughout: list_slugs / normalize / dedupe each take
plain inputs and return plain outputs with no side effects.
"""

from __future__ import annotations

import re
import sys
import json
from dataclasses import dataclass
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


@dataclass(frozen=True)
class PostRecord:
    slug: str
    title: str
    excerpt: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateMatch:
    source: str
    slug: str
    title: str
    score: float
    reason: str


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


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _frontmatter(text: str) -> dict:
    """Read the small, predictable frontmatter subset used by blog posts."""
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}
    result: dict = {}
    current_list = None
    for line in lines[1:end]:
        if line.startswith((" ", "\t")) and current_list:
            item = line.strip()
            if item.startswith("-"):
                result[current_list].append(_scalar(item[1:]))
            continue
        current_list = None
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key, raw = key.strip(), raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            result[key] = [_scalar(item) for item in raw[1:-1].split(",") if item.strip()]
        elif not raw:
            result[key] = []
            current_list = key
        else:
            result[key] = _scalar(raw)
    return result


def load_post_records(content_dir: str | Path) -> list[PostRecord]:
    records = []
    directory = Path(content_dir)
    if not directory.is_dir():
        return records
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in CONTENT_EXTENSIONS:
            continue
        slug = path.stem
        title = excerpt = ""
        tags = []
        try:
            if path.suffix.lower() == ".json":
                fields = json.loads(path.read_text())
                if not isinstance(fields, dict):
                    fields = {}
            else:
                fields = _frontmatter(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            fields = {}
        slug = str(fields.get("slug") or slug)
        title = str(fields.get("title") or "")
        excerpt = str(fields.get("excerpt") or "")
        raw_tags = fields.get("tags", [])
        tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, (list, tuple)) else (str(raw_tags),) if raw_tags else ()
        records.append(PostRecord(slug, title, excerpt, tags))
    return sorted(records, key=lambda record: record.slug)


def comparison_text(item: dict | PostRecord) -> str:
    if isinstance(item, PostRecord):
        values = (item.slug, item.title, item.excerpt, *item.keywords)
    else:
        values = (item.get("slug", ""), item.get("title", ""), item.get("intentSummary", ""), item.get("primaryKeyword", ""))
    return " ".join(normalize(value).replace("-", " ") for value in values if value)


def _intent_tokens(item: dict | PostRecord) -> frozenset:
    if isinstance(item, PostRecord):
        values = (item.title, item.excerpt, *item.keywords)
    else:
        values = (item.get("title", ""), item.get("intentSummary", ""), item.get("primaryKeyword", ""))
    return frozenset(" ".join(normalize(value).replace("-", " ") for value in values if value).split())


def _comparison_parts(item: dict | PostRecord) -> tuple[frozenset, ...]:
    if isinstance(item, PostRecord):
        values = (item.title, item.excerpt, *item.keywords)
    else:
        values = (item.get("title", ""), item.get("intentSummary", ""), item.get("primaryKeyword", ""))
    return tuple(frozenset(normalize(value).replace("-", " ").split()) for value in values if value)


def find_duplicate(candidate: dict, posts: list[PostRecord], recent_topics: list[dict], threshold: float) -> DuplicateMatch | None:
    candidate_slug = normalize(candidate.get("slug", ""))
    candidate_title = normalize(candidate.get("title", ""))
    candidate_tokens = frozenset(comparison_text(candidate).split())
    matches = []
    items = [("published", post) for post in posts] + [("recent-run", topic) for topic in recent_topics]
    for source, item in items:
        slug = normalize(item.slug if isinstance(item, PostRecord) else item.get("slug", ""))
        title = normalize(item.title if isinstance(item, PostRecord) else item.get("title", ""))
        item_tokens = frozenset(comparison_text(item).split())
        score = max(
            [_jaccard(candidate_tokens, item_tokens), _jaccard(_intent_tokens(candidate), _intent_tokens(item))]
            + [_jaccard(a, b) for a in _comparison_parts(candidate) for b in _comparison_parts(item)]
        )
        exact = bool(candidate_slug and candidate_slug == slug) or bool(candidate_title and candidate_title == title)
        if exact or score >= threshold:
            matches.append(DuplicateMatch(source, slug, title, 1.0 if exact else score, "exact identity" if exact else "intent overlap"))
    if not matches:
        return None
    # Identity is authoritative, regardless of a preceding semantic match.
    exact_matches = [value for value in matches if value.reason == "exact identity"]
    closest = max(exact_matches or matches, key=lambda value: value.score)
    update = candidate.get("materialUpdate")
    update_framed = (
        isinstance(update, dict)
        and bool(str(update.get("date", "")).strip())
        and bool(str(update.get("summary", "")).strip())
        and bool(re.search(r"\b(update|new|changed|202\d)\b", candidate.get("title", ""), re.IGNORECASE))
        and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(update.get("date", "")).strip()))
    )
    if update_framed and closest.reason != "exact identity":
        # A material update is a bypass only when it introduces genuinely new
        # intent; retaining the old intent still indicates a duplicate.
        matched = next(item for source, item in items if normalize(item.slug if isinstance(item, PostRecord) else item.get("slug", "")) == closest.slug)
        shared_keyword = frozenset(normalize(candidate.get("primaryKeyword", "")).replace("-", " ").split())
        candidate_intent = frozenset(normalize(candidate.get("intentSummary", "")).replace("-", " ").split()) - shared_keyword
        matched_intent = _intent_tokens(matched) - shared_keyword
        if _jaccard(candidate_intent, matched_intent) < threshold:
            return None
    return closest


def dedupe(candidates: list, existing_slugs: list) -> tuple[list, list]:
    """Split candidates into (fresh, dropped) against existing slugs.

    A candidate is dropped when its slug (or normalized title) exactly matches
    an existing slug, or when the Jaccard overlap between its normalized title
    tokens and any existing slug's tokens reaches SIMILARITY_THRESHOLD.
    Dropped candidates get a "droppedBecause" explanation attached.
    """
    posts = [PostRecord(normalize(s), "", "", ()) for s in existing_slugs]

    fresh: list = []
    dropped: list = []
    for candidate in candidates:
        match = find_duplicate(candidate, posts, [], SIMILARITY_THRESHOLD)
        if match is None:
            fresh.append(candidate)
        else:
            reason = (f"{DROPPED_EXACT_SLUG}: {match.slug}" if match.reason == "exact identity"
                      else f"{DROPPED_SIMILAR_TITLE}: {match.slug} (overlap {match.score:.2f})")
            dropped.append({**candidate, "droppedBecause": reason,
                            "duplicateSource": match.source, "duplicateSlug": match.slug,
                            "duplicateTitle": match.title, "duplicateScore": match.score,
                            "duplicateReason": match.reason})
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
