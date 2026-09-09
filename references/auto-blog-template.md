# Unattended Blog Artifact

Read this reference only for `daily-auto`. Return a structured editorial
artifact; the caller performs every side effect.

## Topic decision

Evaluate current questions across the configured personas. A candidate needs a
dated reason to publish now, a recognizable search question, strong audience
fit, at least two current authoritative sources including one primary source,
and a natural FinBoard connection.

Scores are integers from 0 to 5 for `freshness`, `audienceFit`,
`sourceAuthority`, `searchSharingPotential`, and `productRelevance`. Use the
configured minimum total, source-authority floor, and similarity threshold.
Return `nothing_publishable` when no candidate clears every floor.

Before drafting, compare the proposed slug, normalized title, primary keyword,
and intent summary with every existing article and recent run topic. A dated
update is distinct only when it covers a material change and its remaining
intent differs after the shared keyword is removed. Exact slug or title matches
never qualify.

## Source contract

For changing claims, record the source URL, publisher, publication or update
date, supported claim, and authority class. Prefer product documentation,
regulators, standards setters, tax authorities, and original announcements.
Link the dated primary source in the why-now section near the claim it supports.
Do not infer product behavior from search snippets.

## Article structure

The final HTML article has this shape:

1. Open with a direct answer of 40 to 60 words. Put the primary keyword
   naturally in this paragraph, the title, excerpt, and descriptive cover alt.
2. Add a why-now `h2` section containing the matching source date and link.
3. Use 3 to 6 substantive `h2` sections in total. Add a comparison table only
   when readers need to compare repeated fields across choices.
4. Include an accounting-controls `h2` section. Separate what comes from source
   data, what deterministic calculation produces, what a reviewer checks, and
   who owns the decision. Respect debit/credit polarity and flow versus
   point-in-time distinctions when the topic involves financial measures.
5. State limits and common mistakes neutrally. Do not disparage competitors or
   present unsupported certainty.
6. End with a Frequently Asked Questions `h2` containing 4 to 5 visible `h3`
   questions. Their answers must exactly match the FAQPage structured data.
7. Include 2 to 4 contextual links to routes that exist in the target FinBoard
   repository.
8. After the educational answer, include exactly one relevant FinBoard call to
   action linking to the configured production base URL.

Use clear sentences, specific nouns, and evidence near changing claims. Follow
the prose-cleanliness rules in `references/blog-schema.md`.

## FinBoard JSON contract

Return the exact field vocabulary defined by
`scripts/auto_artifact.py:ARTIFACT_JSON_SCHEMA`. The blog document uses:

- `author: "FinBoard Team"` and `authorId: "finboard-team"`;
- one configured category key;
- the caller-supplied local publish date for `date`, `datePublished`, and
  `dateModified`;
- `format: "html"`;
- `/blog/covers/<slug>.png` and a unique, descriptive cover alt;
- BlogPosting structured data whose canonical URL and image agree with the
  slug and cover; and
- FAQPage structured data identical to the visible FAQ section.

The cover object contains a short audience tag and a readable six-digit hex
accent. Never reuse another article's cover.

## Output boundary

Return only the structured envelope. Do not write the article or cover, call a
shell, use Git, deploy, reveal credentials, or send a notification. The runner
will reject any output that fails the schema, content, duplicate, path, build,
or production checks.
