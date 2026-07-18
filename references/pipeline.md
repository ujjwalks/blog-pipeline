# Pipeline state machine

One run per date, stored at `<repo>/.blog-pipeline/runs/YYYY-MM-DD.json` and
managed by `scripts/runstate.py`. Every stage is idempotent: it loads the run,
checks the status, and resumes. Illegal transitions raise, so no stage can
skip a human gate.

```
researching
  -> awaiting_topic_approval    (gate 1: human picks topics)
  -> drafting
  -> awaiting_content_approval  (gate 2: human approves previews)
  -> deploying
  -> published

researching -> published        (no-op day: every candidate deduped away)
```

`published` is terminal. Re-running a stage whose work is already recorded is
a no-op (`advance` to the current status returns unchanged).

## What each stage reads and writes

| Stage | Reads | Writes on the run file |
|---|---|---|
| research | config personas, existing slugs (`scripts/existing.py`), web | creates the run; fills `topics[]` (title, persona, angle, keyword, rationale); posts the numbered list to the channel; advances to `awaiting_topic_approval`. If nothing survives dedupe: posts "nothing new today", advances straight to `published` |
| draft | `topics[]`, the human's picks (inline arg or channel reply) | fills `selected[]` (0-based indices into `topics`); advances to `drafting`; after writing, validating, committing, and pushing: fills `drafted[]` (`slug`, `file`, `previewUrl`); posts preview links; advances to `awaiting_content_approval` |
| deploy | `drafted[]`, the human's approval | advances to `deploying`; runs the rendered deploy script; fills `deploy` (`branch`, `commit`, `prodUrls`); posts confirmation; advances to `published` |
| status | the run file | nothing; prints status, history, and the next action |

Every `advance()` appends `{status, at}` to `history[]`, so the run file is
its own audit trail.

## The two gates

Both gates are mandatory. The skill never drafts without topic approval and
never deploys without content approval; `runstate.py` enforces this because
`drafting` is only reachable from `awaiting_topic_approval` and `deploying`
only from `awaiting_content_approval`.

Each gate's mode comes from config, independently:
`gates.topicApproval` and `gates.contentApproval`, each `manual` | `poll`.

- **manual:** the human replies on the review channel, then runs the next
  sub-command (`draft` or `deploy`) themselves. The reply can also be passed
  inline as the sub-command argument, skipping the channel read entirely.
- **poll:** a scheduled invocation re-enters the skill, reads the channel
  reply via the adapter's `read_reply`, and advances if an approval is found.
  No reply yet means no advance; the run stays at the gate.

## Pick argument contract

Both gate paths (inline argument and fetched channel reply) feed the same
parser, `runstate.parse_picks`, so manual and poll behave identically.
Accepted forms:

- `all` -- every posted item, capped at `blogsPerRun`
- 1-based indices -- `1,3,5` or `1 3 5`
- slugs (or unambiguous title fragments) -- matched against the run's posted
  items

The parser returns 0-based indices plus a list of problems. Unmatched,
out-of-range, or ambiguous tokens are reported back to the human, never
silently dropped. Selections over the cap are truncated and the truncation is
reported.

## Error handling

From design spec section 11. The rule everywhere: fail loudly at the current
status, never advance past a failure.

- **Review-channel post fails:** the stage aborts with the run file left at
  its prior status. Re-running the stage retries the post. No state is lost
  because the state only advances after a successful post.
- **`validate_blog.py` fails on a draft:** skip that blog, keep the rest,
  report exactly which file failed and why. An invalid file is never
  committed or pushed.
- **Preview sits behind auth:** verify every preview URL returns HTTP 200
  before posting. A 302 or 401 (for example Vercel deployment protection)
  means the link is dead for the reviewer; surface that to the operator
  instead of posting dead links.
- **Preview build fails:** the draft branch stays for inspection; deploy is
  never auto-triggered on a failed preview.
- **Dirty tree at deploy:** the deploy script refuses to run and aborts with
  a clear message. Commit or stash, then re-run `deploy`.

## Operational rules learned in production

- **One run per date.** `runs/<date>.json` is the unit; research must never
  overwrite an existing day's file. A completed earlier run stays as the
  record; a same-day re-research only happens if the operator archives the
  old file deliberately.
- **The daily cap is per day, not per run.** `blogsPerRun` bounds publishes
  per calendar day across all runs. If the quota is spent, a fresh topic
  list still gets posted, but its picks deploy the next day and the post
  should say so.
- **`run["channel"].posted` is the anti-repost marker.** Whichever transport
  posts the review message (bot script, session Slack tools, CLI) sets
  `run["channel"] = {"posted": true}` and saves. Session hooks use this
  field to decide whether anything is pending.
- **Publish dates are stamped at deploy.** Drafts carry their draft date;
  the deploy stage re-stamps `date` (and structuredData dates) to the
  publish day and re-validates before merging.
