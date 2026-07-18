# Blog schema and house style

The skill is target-agnostic. The target's schema comes from `config.json`:
`target.blogFormat` (`json` | `md` | `mdx`), `target.categories`, and
`target.authors`. This file describes the common shape each format maps to and
the house style every draft follows regardless of format.
`scripts/validate_blog.py` is the deterministic gate; a draft that fails it is
never committed.

## JSON shape (blogFormat: json)

One file per post at `<contentDir>/<slug>.json`. The filename stem must equal
the slug.

| Field | Type | Notes |
|---|---|---|
| `slug` | string | kebab-case, unique across the site, equals filename stem |
| `title` | string | the h2 that opens the post |
| `category` | string | must be one of `target.categories` |
| `excerpt` | string | 1 to 2 sentences, used in listings and meta description |
| `author` | string | display name |
| `authorId` | string | must resolve against `target.authors`; pick the author whose `category` matches the post |
| `date` | string | `YYYY-MM-DD`. Set to the PUBLISH date at deploy time, not the draft date; the deploy stage re-stamps it. |
| `coverImage` | string | URL; often a placeholder at draft time, see below |
| `coverAlt` | string | descriptive alt text for the cover |
| `format` | string | content markup format, e.g. `"md"` |
| `order` | number | sort position in listings |
| `structuredData` | object | JSON-LD, at minimum a `FAQPage` mirroring the FAQ section |
| `content` | string | the full post body, at least 4000 characters |

## Markdown frontmatter (blogFormat: md | mdx)

One file per post at `<contentDir>/<slug>.md` (or `.mdx`). YAML frontmatter
carries the same fields; the body below the frontmatter is the `content`.
`title`, `date`, and `category` are required in frontmatter; carry the rest
(`excerpt`, `author`, `coverImage`, `structuredData`, ...) as the target's
existing posts do. When in doubt, open an existing post in `contentDir` and
match it.

## House style

Learned from production use. Follow all of it for every draft.

- **Length:** 1900 to 2700 words.
- **Opening:** an h2 with the title, then a direct human intro. No throat
  clearing, no "in today's fast-paced world". State the problem and who has
  it within the first two sentences.
- **Structure:** h2 sections with h3 subsections where needed. Short
  paragraphs, 2 to 4 sentences.
- **One table**, placed where it earns its place: a comparison, a benchmark, a
  deadline calendar. Do not add a table to have a table.
- **FAQ section** with 4 to 5 question-and-answer pairs. The FAQ text in the
  body MUST mirror the `structuredData` FAQPage word for word. Drift between
  the two is a bug.
- **Internal links** to 2 to 3 existing posts on the site (use the slugs from
  `scripts/existing.py`). Link where the reader would actually want the
  detour, not in a "related posts" dump.
- **One CTA at the end**, tied to what the target site sells. One, not three.
- **Write for AI search (GEO):** make key passages citable and
  self-contained. A paragraph that defines a term or states a benchmark should
  survive being quoted alone, with the subject named in the passage rather
  than carried by a pronoun from the previous paragraph.

## Humanization rules

Enforced by `scripts/validate_blog.py`, not optional. A draft that violates
them fails the gate and is not committed.

- **No em or en dashes**, and none of their HTML entities. Restructure the
  sentence with commas, periods, or parentheses. Ranges become words: "6 to
  10 clients", not a dash.
- **No curly quotes or curly apostrophes.** Straight `'` and `"` only.
- **No formulaic AI phrases:** "Let's break it down", "seamless", "robust",
  "leverage", "streamline", "dive into", and their kin. If a sentence could
  open any vendor's blog, rewrite it.
- **No exclamation marks.**
- **Contractions welcome.** "Don't" reads human; "do not" reads like a
  compliance memo. Use them.
- **Vary sentence length.** A run of same-length sentences is the loudest AI
  tell. Follow a long sentence with a short one.

## Cover images

Cover images are often placeholders at draft time (the config default or a
stock URL). That is fine, but flag it: the review post for each draft must say
whether the cover is a placeholder so the human can swap it before or after
deploy. Never present a placeholder as final.
