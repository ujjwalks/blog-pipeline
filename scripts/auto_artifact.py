"""Strict, deterministic boundary for unattended blog model output."""

from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from existing import PostRecord, find_duplicate
from validate_blog import MIN_CONTENT_CHARS, check_cleanliness

PUBLISH_OUTCOME = "publish"
NO_TOPIC_OUTCOME = "nothing_publishable"
AUTHOR_NAME = "FinBoard Team"
AUTHOR_ID = "finboard-team"
SCORE_KEYS = (
    "freshness",
    "audienceFit",
    "sourceAuthority",
    "searchSharingPotential",
    "productRelevance",
)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TAG_RE = re.compile(r"<[^>]+>")
H2_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
FAQ_RE = re.compile(r"<h3\b[^>]*>(.*?)</h3>\s*<p\b[^>]*>(.*?)</p>", re.I | re.S)
HREF_RE = re.compile(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", re.I)
FIRST_PARAGRAPH_RE = re.compile(r"^\s*<p\b[^>]*>(.*?)</p>", re.I | re.S)

TOPIC_REQUIRED = (
    "slug", "title", "persona", "angle", "primaryKeyword",
    "intentSummary", "whyNow", "scores", "sources",
)
BLOG_REQUIRED = (
    "slug", "title", "category", "excerpt", "author", "authorId", "date",
    "coverImage", "coverAlt", "format", "order", "structuredData", "content",
)
SOURCE_REQUIRED = ("url", "publisher", "publishedOrUpdated", "claim", "authority")
COVER_REQUIRED = ("tag", "accent")


def _object_schema(required, properties):
    return {
        "type": "object",
        "required": list(required),
        "additionalProperties": False,
        "properties": properties,
    }


_TEXT = {"type": "string", "minLength": 1}
_SCORES_SCHEMA = _object_schema(
    SCORE_KEYS,
    {key: {"type": "integer", "minimum": 0, "maximum": 5} for key in SCORE_KEYS},
)
_SOURCE_SCHEMA = _object_schema(
    SOURCE_REQUIRED,
    {
        "url": {"type": "string", "format": "uri"},
        "publisher": _TEXT,
        "publishedOrUpdated": {"type": "string", "format": "date"},
        "claim": _TEXT,
        "authority": {"enum": ["primary", "authoritative", "secondary"]},
    },
)
_TOPIC_SCHEMA = _object_schema(
    TOPIC_REQUIRED,
    {
        "slug": _TEXT,
        "title": _TEXT,
        "persona": _TEXT,
        "angle": _TEXT,
        "primaryKeyword": _TEXT,
        "intentSummary": _TEXT,
        "whyNow": _TEXT,
        "scores": _SCORES_SCHEMA,
        "sources": {"type": "array", "minItems": 2, "items": _SOURCE_SCHEMA},
        "materialUpdate": _object_schema(("date", "summary"), {"date": {"type": "string", "format": "date"}, "summary": _TEXT}),
    },
)
_BLOG_SCHEMA = _object_schema(
    BLOG_REQUIRED,
    {
        **{key: _TEXT for key in BLOG_REQUIRED if key not in ("order", "structuredData")},
        "order": {"type": ["integer", "number"]},
        "structuredData": {"type": "object"},
    },
)
_COVER_SCHEMA = _object_schema(COVER_REQUIRED, {"tag": _TEXT, "accent": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"}})

ARTIFACT_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "oneOf": [
        _object_schema(
            ("outcome", "topic", "blog", "cover"),
            {"outcome": {"const": PUBLISH_OUTCOME}, "topic": _TOPIC_SCHEMA, "blog": _BLOG_SCHEMA, "cover": _COVER_SCHEMA},
        ),
        _object_schema(
            ("outcome", "reason"),
            {"outcome": {"const": NO_TOPIC_OUTCOME}, "reason": _TEXT},
        ),
    ],
}


def _codex_schema_node(node, path=()):
    if isinstance(node, list):
        return [_codex_schema_node(value, path) for value in node]
    if not isinstance(node, dict):
        return node
    if path[-1:] == ("structuredData",):
        return {"type": "string"}
    result = {
        key: _codex_schema_node(value, path + (key,))
        for key, value in node.items()
        if key not in {"$schema", "format"}
    }
    if "oneOf" in result:
        result["anyOf"] = result.pop("oneOf")
    if "const" in result:
        result["type"] = "string"
    properties = result.get("properties")
    if isinstance(properties, dict):
        if path[-1:] == ("topic",):
            properties.pop("materialUpdate", None)
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


def codex_output_schema() -> dict:
    """Return the Codex-compatible transport schema for a direct artifact."""
    publish, _ = _codex_schema_node(ARTIFACT_JSON_SCHEMA)["anyOf"]
    nullable = lambda value: {"anyOf": [value, {"type": "null"}]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["outcome", "reason", "topic", "blog", "cover"],
        "properties": {
            "outcome": {"type": "string", "enum": [PUBLISH_OUTCOME, NO_TOPIC_OUTCOME]},
            "reason": {"type": "string"},
            "topic": nullable(publish["properties"]["topic"]),
            "blog": nullable(publish["properties"]["blog"]),
            "cover": nullable(publish["properties"]["cover"]),
        },
    }


def _normalize_codex_artifact(artifact: dict) -> dict:
    normalized = dict(artifact)
    outcome = normalized.get("outcome")
    if outcome == NO_TOPIC_OUTCOME:
        return {"outcome": outcome, "reason": normalized.get("reason")}
    if outcome == PUBLISH_OUTCOME:
        normalized.pop("reason", None)
        structured = normalized.get("blog", {}).get("structuredData") if isinstance(normalized.get("blog"), dict) else None
        if isinstance(structured, str):
            try:
                normalized["blog"] = {**normalized["blog"], "structuredData": json.loads(structured)}
            except json.JSONDecodeError as exc:
                raise ValueError(f"Model structuredData is not valid JSON: {exc}") from exc
    return normalized


def parse_model_output(raw: str) -> dict:
    try:
        wrapper = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Model response is not valid JSON: {exc}") from exc
    if not isinstance(wrapper, dict):
        raise ValueError("Model response must be a JSON object")
    if "outcome" in wrapper:
        return _normalize_codex_artifact(wrapper)
    value = wrapper.get("structured_output")
    if value is None and isinstance(wrapper.get("artifact"), str):
        try:
            value = json.loads(wrapper["artifact"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model artifact is not valid JSON: {exc}") from exc
    if value is None and isinstance(wrapper.get("result"), str):
        try:
            value = json.loads(wrapper["result"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model result is not valid structured JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model response has no object structured_output")
    return value


def safe_child(root: Path, relative: Path) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"artifact path escapes configured root: {relative}")
    return resolved


def safe_artifact_paths(repo: Path, cfg: dict, artifact: dict) -> tuple[Path, Path]:
    blog = artifact.get("blog")
    if not isinstance(blog, dict):
        raise ValueError("publish artifact has no blog object")
    slug = blog.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"invalid slug: {slug!r}")
    article = safe_child(repo, Path(cfg["target"]["contentDir"]) / f"{slug}.json")
    cover = safe_child(repo, Path("frontend/public/blog/covers") / f"{slug}.png")
    return article, cover


def _plain(value) -> str:
    return html.unescape(TAG_RE.sub(" ", str(value or ""))).replace("\xa0", " ").strip()


def _nonempty_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_date(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _https_url(value) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _required_object(value, required, allowed, where, errors):
    if not isinstance(value, dict):
        errors.append(f"{where}: must be an object")
        return False
    missing = [key for key in required if key not in value]
    extra = sorted(set(value) - set(allowed))
    errors.extend(f"{where}.{key}: required" for key in missing)
    errors.extend(f"{where}.{key}: unexpected field" for key in extra)
    return not missing


def _graph_nodes(blog, errors):
    structured = blog.get("structuredData")
    if not isinstance(structured, dict):
        errors.append("blog.structuredData: must be an object")
        return None, None
    graph = structured.get("@graph")
    nodes = graph if isinstance(graph, list) else [structured]
    posting = next((node for node in nodes if isinstance(node, dict) and node.get("@type") == "BlogPosting"), None)
    faq = next((node for node in nodes if isinstance(node, dict) and node.get("@type") == "FAQPage"), None)
    if posting is None:
        errors.append("blog.structuredData: BlogPosting node required")
    if faq is None:
        errors.append("blog.structuredData: FAQPage node required")
    return posting, faq


def _validate_sources(topic, cfg, errors):
    sources = topic.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        errors.append("topic.sources: at least two sources required")
        return
    primary = 0
    for index, source in enumerate(sources):
        where = f"topic.sources[{index}]"
        if not _required_object(source, SOURCE_REQUIRED, SOURCE_REQUIRED, where, errors):
            continue
        for key in ("publisher", "claim"):
            if not _nonempty_text(source.get(key)):
                errors.append(f"{where}.{key}: non-empty text required")
        if not _https_url(source.get("url")):
            errors.append(f"{where}.url: https URL required")
        if not _valid_date(source.get("publishedOrUpdated")):
            errors.append(f"{where}.publishedOrUpdated: valid YYYY-MM-DD required")
        if source.get("authority") == "primary":
            primary += 1
        elif source.get("authority") not in ("authoritative", "secondary"):
            errors.append(f"{where}.authority: must be primary, authoritative, or secondary")
    if primary == 0:
        errors.append("topic.sources: at least one primary source required")


def _validate_scores(topic, cfg, errors):
    scores = topic.get("scores")
    if not _required_object(scores, SCORE_KEYS, SCORE_KEYS, "topic.scores", errors):
        return
    for key in SCORE_KEYS:
        value = scores.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5:
            errors.append(f"topic.scores.{key}: integer from 0 through 5 required")
    numeric = [scores.get(key) for key in SCORE_KEYS if isinstance(scores.get(key), int) and not isinstance(scores.get(key), bool)]
    if len(numeric) == len(SCORE_KEYS) and sum(numeric) < cfg["automation"]["minTopicScore"]:
        errors.append(f"topic.scores: total must reach {cfg['automation']['minTopicScore']}")
    authority = scores.get("sourceAuthority")
    if isinstance(authority, int) and authority < cfg["automation"]["minSourceAuthority"]:
        errors.append(f"topic.scores.sourceAuthority: must reach {cfg['automation']['minSourceAuthority']}")


def _section(content, predicate):
    headings = list(H2_RE.finditer(content))
    for index, match in enumerate(headings):
        if predicate(_plain(match.group(1)).lower()):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            return content[match.end():end]
    return None


def _validate_faq(content, faq, errors):
    faq_section = _section(content, lambda heading: "frequently asked" in heading or heading == "faq")
    visible = [(_plain(question), _plain(answer)) for question, answer in FAQ_RE.findall(faq_section or "")]
    if not 4 <= len(visible) <= 5:
        errors.append("blog.content: 4 to 5 visible FAQs required")
    entities = faq.get("mainEntity") if isinstance(faq, dict) else None
    schema_pairs = []
    if isinstance(entities, list):
        for entity in entities:
            answer = entity.get("acceptedAnswer") if isinstance(entity, dict) else None
            if isinstance(answer, dict):
                schema_pairs.append((_plain(entity.get("name")), _plain(answer.get("text"))))
    if visible != schema_pairs:
        errors.append("blog.structuredData: FAQ answers must exactly match visible FAQ content")


def _validate_internal_links(content, cfg, errors):
    links = list(dict.fromkeys(href for href in HREF_RE.findall(content) if href.startswith("/") and not href.startswith("//")))
    if not 2 <= len(links) <= 4:
        errors.append("blog.content: 2 to 4 contextual internal links required")
    repo = Path(cfg.get("target", {}).get("repoPath", ""))
    if not repo.is_dir():
        errors.append(f"blog.content: configured repository does not exist: {repo}")
        return
    for href in links:
        clean = href.split("?", 1)[0].split("#", 1)[0].strip("/")
        if clean.startswith("blog/"):
            slug = clean.split("/", 1)[1]
            content_dir = repo / cfg["target"]["contentDir"]
            exists = any((content_dir / f"{slug}{extension}").is_file() for extension in (".json", ".md", ".mdx"))
        else:
            route = repo / "frontend/src/app" / clean
            exists = any((route / f"page{extension}").is_file() for extension in (".js", ".jsx", ".ts", ".tsx"))
        if not exists:
            errors.append(f"blog.content: internal link does not resolve locally: {href}")


def validate_artifact(artifact: dict, cfg: dict, publish_date: str, existing_posts: list[PostRecord], recent_topics: list[dict]) -> list[str]:
    errors = []
    if not isinstance(artifact, dict):
        return ["artifact: must be an object"]
    outcome = artifact.get("outcome")
    if outcome == NO_TOPIC_OUTCOME:
        _required_object(artifact, ("outcome", "reason"), ("outcome", "reason"), "artifact", errors)
        if not _nonempty_text(artifact.get("reason")):
            errors.append("artifact.reason: non-empty text required")
        return errors
    if outcome != PUBLISH_OUTCOME:
        return [f"artifact.outcome: must be {PUBLISH_OUTCOME!r} or {NO_TOPIC_OUTCOME!r}"]
    if not _required_object(artifact, ("outcome", "topic", "blog", "cover"), ("outcome", "topic", "blog", "cover"), "artifact", errors):
        return errors
    topic, blog, cover = artifact.get("topic"), artifact.get("blog"), artifact.get("cover")
    if not _required_object(topic, TOPIC_REQUIRED, (*TOPIC_REQUIRED, "materialUpdate"), "topic", errors):
        return errors
    if not _required_object(blog, BLOG_REQUIRED, BLOG_REQUIRED, "blog", errors):
        return errors
    cover_valid = _required_object(cover, COVER_REQUIRED, COVER_REQUIRED, "cover", errors)
    _validate_scores(topic, cfg, errors)
    _validate_sources(topic, cfg, errors)
    for field in TOPIC_REQUIRED:
        if field not in ("scores", "sources") and not _nonempty_text(topic.get(field)):
            errors.append(f"topic.{field}: non-empty text required")
    material_update = topic.get("materialUpdate")
    if material_update is not None:
        if _required_object(material_update, ("date", "summary"), ("date", "summary"), "topic.materialUpdate", errors):
            if not _valid_date(material_update.get("date")):
                errors.append("topic.materialUpdate.date: valid YYYY-MM-DD required")
            if not _nonempty_text(material_update.get("summary")):
                errors.append("topic.materialUpdate.summary: non-empty text required")
    for field in BLOG_REQUIRED:
        if field not in ("order", "structuredData") and not _nonempty_text(blog.get(field)):
            errors.append(f"blog.{field}: non-empty text required")
    order = blog.get("order")
    if not isinstance(order, (int, float)) or isinstance(order, bool):
        errors.append("blog.order: number required")
    if not isinstance(blog.get("structuredData"), dict):
        errors.append("blog.structuredData: object required")
    if cover_valid:
        if not _nonempty_text(cover.get("tag")):
            errors.append("cover.tag: non-empty text required")
        if not isinstance(cover.get("accent"), str) or not HEX_RE.fullmatch(cover["accent"]):
            errors.append("cover.accent: six-digit hex color required")

    slug = blog.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        errors.append("blog.slug: canonical lowercase hyphenated slug required")
    if topic.get("slug") != slug:
        errors.append("topic.slug: must match blog.slug")
    final_candidate = {**topic, "title": blog.get("title", ""), "intentSummary": " ".join((str(topic.get("intentSummary", "")), str(blog.get("excerpt", ""))))}
    duplicate = find_duplicate(final_candidate, existing_posts, recent_topics, cfg["automation"]["similarityThreshold"])
    if duplicate:
        errors.append(f"topic: duplicate of {duplicate.source} {duplicate.slug} (score {duplicate.score:.2f})")

    if blog.get("author") != AUTHOR_NAME:
        errors.append(f"blog.author: must equal {AUTHOR_NAME!r}")
    if blog.get("authorId") != AUTHOR_ID:
        errors.append(f"blog.authorId: must equal {AUTHOR_ID!r}")
    if blog.get("date") != publish_date:
        errors.append(f"blog.date: must equal local publish date {publish_date}")
    if blog.get("category") not in cfg["target"]["categories"]:
        errors.append("blog.category: not in configured categories")
    if blog.get("format") != "html":
        errors.append("blog.format: must equal 'html' for JSON blog content")
    expected_cover = f"/blog/covers/{slug}.png"
    if blog.get("coverImage") != expected_cover:
        errors.append(f"blog.coverImage: must equal {expected_cover}")

    content = blog.get("content") if isinstance(blog.get("content"), str) else ""
    if len(content) < MIN_CONTENT_CHARS:
        errors.append(f"blog.content: must contain at least {MIN_CONTENT_CHARS} characters")
    errors.extend(check_cleanliness(content, "blog.content"))
    errors.extend(check_cleanliness(str(blog.get("excerpt", "")), "blog.excerpt"))
    opening_match = FIRST_PARAGRAPH_RE.search(content)
    opening = _plain(opening_match.group(1)) if opening_match else ""
    word_count = len(opening.split())
    if not 40 <= word_count <= 60:
        errors.append("blog.content: opening answer must contain 40 to 60 words")
    h2_count = len(H2_RE.findall(content))
    if not 3 <= h2_count <= 6:
        errors.append("blog.content: 3 to 6 h2 sections required")
    controls_section = _section(
        content,
        lambda heading: "control" in heading and not ("why" in heading and "now" in heading),
    )
    if controls_section is None:
        errors.append("blog.content: accounting controls section required")
    lower_content = _plain(controls_section or "").lower()
    for term in ("source data", "calculation", "review", "decision"):
        if term not in lower_content:
            errors.append(f"blog.content: accounting control term missing: {term}")
    primary_keyword = str(topic.get("primaryKeyword", "")).lower()
    for where, value in (("title", blog.get("title")), ("excerpt", blog.get("excerpt")), ("opening", opening), ("coverAlt", blog.get("coverAlt"))):
        if primary_keyword and primary_keyword not in str(value or "").lower():
            errors.append(f"blog.{where}: primary keyword must appear naturally")
    if not _nonempty_text(blog.get("coverAlt")) or len(str(blog.get("coverAlt", "")).split()) < 5:
        errors.append("blog.coverAlt: descriptive alt text required")

    posting, faq = _graph_nodes(blog, errors)
    base_url = cfg["automation"]["productionBaseUrl"].rstrip("/")
    canonical = f"{base_url}/blog/{slug}"
    image_url = f"{base_url}{expected_cover}"
    if posting:
        page = posting.get("mainEntityOfPage")
        page_url = page.get("@id") if isinstance(page, dict) else page
        if page_url != canonical:
            errors.append("blog.structuredData: canonical article URL must match slug")
        if posting.get("image") != image_url:
            errors.append("blog.structuredData: image URL must match coverImage")
        if posting.get("datePublished") != publish_date or posting.get("dateModified") != publish_date:
            errors.append("blog.structuredData: published and modified dates must equal local publish date")
        author = posting.get("author")
        if not isinstance(author, dict) or author.get("name") != AUTHOR_NAME:
            errors.append("blog.structuredData: canonical FinBoard Team author required")
    if faq:
        _validate_faq(content, faq, errors)
    _validate_internal_links(content, cfg, errors)
    primary_urls = [source.get("url") for source in topic.get("sources", []) if isinstance(source, dict) and source.get("authority") == "primary"]
    if primary_urls and not any(url in content for url in primary_urls):
        errors.append("blog.content: at least one primary source must be linked near its claim")
    why_section = _section(content, lambda heading: "why" in heading and "now" in heading)
    why_hrefs = set(HREF_RE.findall(why_section or ""))
    linked_dated_source = any(
        isinstance(source, dict)
        and source.get("url") in why_hrefs
        and source.get("publishedOrUpdated") in _plain(why_section or "")
        for source in topic.get("sources", [])
    )
    if why_section is None or not linked_dated_source:
        errors.append("blog.content: dated why-now section with a source link required")
    cta_urls = [href.rstrip("/") for href in HREF_RE.findall(content) if href.rstrip("/") == base_url]
    if len(cta_urls) != 1:
        errors.append("blog.content: exactly one FinBoard call to action required")
    try:
        article_path, cover_path = safe_artifact_paths(Path(cfg["target"]["repoPath"]), cfg, artifact)
        if article_path.exists():
            errors.append(f"blog.slug: article path already exists: {article_path.name}")
        if cover_path.exists():
            errors.append(f"blog.coverImage: cover path already exists: {cover_path.name}")
    except (KeyError, ValueError) as exc:
        errors.append(f"artifact paths: {exc}")
    return errors
