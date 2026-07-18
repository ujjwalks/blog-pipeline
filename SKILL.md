---
name: blog-pipeline
description: >-
  Runs a recurring blog production pipeline for any website: research topic
  ideas per audience persona, post a top-N list to a review channel (Slack or
  CLI), draft the approved topics in the site's blog format, push a preview
  for human review, then deploy to production. Use when the user asks to set
  up or run a blog pipeline, research blog topics, draft or publish scheduled
  blogs, review drafted posts, or advance a pending blog run ("run research",
  "draft the picks", "deploy the approved posts", "blog pipeline status") --
  even if they only say "do the daily blogs".
---

# blog-pipeline

A config-driven pipeline with two mandatory human gates. All business choices
(target site, personas, cadence, channels, deploy) live in
`<repo>/.blog-pipeline/config.json` -- never in this skill. Stages are
stateless and idempotent; state lives in `<repo>/.blog-pipeline/runs/<date>.json`.

Route on the sub-command the user asked for (default: `status`):

| Sub-command | When |
|---|---|
| `setup` | first use, or changing personas/cadence/channels |
| `research` | the scheduled entry point; produces the topic list |
| `draft` | after the human picked topics on the review channel |
| `deploy` | after the human approved the previews |
| `status` | anything else -- show where the run is stuck |

Validate config before any stage: `python3 scripts/config.py <repo>`.
Show run state: `python3 scripts/runstate.py <repo> <date>`.

## setup (interactive)

Walk the user through, one question at a time; write with
`config.write_config()` (it refuses invalid configs). Capture: target repo
path + content dir + blog format + categories/authors; personas (seed from
`references/personas.md`, let them edit); topicsPerRun (default 10);
blogsPerRun (default 3); cron schedule + scheduler; review channel
(slack -> needs channelId + two env var NAMES, never values; cli works with
zero setup); gate modes (manual/poll); review mode; deploy mode/remote/branch.
Then render `assets/deploy.sh.tmpl` into the target repo (fill the
`{{PLACEHOLDERS}}`), `chmod +x` it, and install the schedule with
`python3 scripts/install_cron.py <repo>`.

## research

1. `python3 scripts/existing.py <repo>` -- existing slugs; never propose a
   topic that duplicates one.
2. Judgment: before choosing search angles, read `references/personas.md` --
   it defines each persona's pains and what a winning topic looks like. Then
   for each persona, WebSearch what that audience is asking NOW (pains,
   deadlines, tool comparisons, regulation changes). Spread the top
   `topicsPerRun` across personas; prefer topics with a concrete target
   search prompt.
3. Post the numbered list via the review channel
   (`python3 scripts/channels/slack.py post ...` or `cli.py`), each item:
   title, persona, angle, target prompt, why-now.
4. Create the run and advance to `awaiting_topic_approval`.

If every candidate dedupes away: post "nothing new today", advance
researching -> published (legal no-op), stop.

## draft

1. Read picks: inline arg, or fetch the reply
   (`channels/slack.py read ...`). Both go through `runstate.parse_picks` --
   report unmatched tokens, never drop silently.
2. Judgment: write each blog in the target's format following
   `references/blog-schema.md` (house style, humanization rules, FAQ +
   structured data). Drafting in parallel subagents is fine; validation is not
   optional: `python3 scripts/validate_blog.py <repo> <file>` per file --
   it enforces schema AND prose cleanliness (no em dashes, no curly quotes).
3. Commit valid drafts to `<branchPrefix><date>`, push, obtain preview URLs
   per `review.mode`, and VERIFY each returns HTTP 200 -- a 302/401 means the
   preview sits behind auth (e.g. Vercel deployment protection); surface that
   instead of posting dead links.
4. Post preview links to the channel; advance to `awaiting_content_approval`.

## deploy

Before merging, re-stamp each publishing blog's `date` (and any
`datePublished`/`dateModified` in its structured data) to TODAY -- drafts
carry their draft date, and publishing a stale date misdates the post.
Re-validate after stamping. Then run the generated deploy script
(`bash <repo>/scripts/blog-deploy.sh`). It
guards a clean tree, merges the draft branch, pushes to the prod branch.
Verify the published URLs return 200 on the live domain, post confirmation to
the channel, advance deploying -> published.

## Gates

Both gates honor `gates.*` from config: `manual` means the human runs the
next sub-command; `poll` means a scheduled invocation reads the channel reply
and advances. Never draft without topic approval; never deploy without
content approval. Full state machine: `references/pipeline.md`.
