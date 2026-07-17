# blog-pipeline — Design Spec

**Date:** 2026-07-15
**Status:** Approved for planning
**Repo:** `ujjwalks-ai/blog-pipeline` (new, open-source, MIT). Symlinked into `~/.claude/skills/blog-pipeline`.

## 1. Purpose

A generic, config-driven Claude Code skill that runs a daily blog production
pipeline end to end:

> research relevant topics per audience → post a top-N topic list to the
> configured **review channel** → human picks topics → draft the blogs → post
> per-blog preview links → human approves → deploy to production.

The **review gate is mandatory** — nothing drafts or deploys without human
approval — but the *channel* that carries the review (Slack, a CLI prompt, email,
etc.) is chosen by the user in `setup`, not fixed to any one service. Slack is
the shipped default implementation.

The skill is **target-agnostic**. It hardcodes nothing about any one website.
FinBoard is simply its first configured user (shipped as
`examples/config.filled.example.json`). This mirrors the `skill-doctor` philosophy:
the skill is portable, open-source, and driven entirely by a config file plus
the model's judgment.

### Non-goals

- It does not host a server or maintain a long-running process. Claude Code is
  not persistent; the pipeline is a set of **stateless stages** with human gates
  that happen on the configured review channel between stages.
- It does not generate cover images (a future extension may). Blogs reference an
  image URL supplied by the target's config default or left for manual add.
- It is not a CMS. It writes blog files into the target repo's existing content
  directory in the target's existing format; deploy is the target's existing
  git/Vercel flow.

## 2. Design principles (inherited from skill-doctor)

1. **Express as code what you can.** Deterministic, repeatable operations live
   in tested `scripts/` (Python, stdlib-only where possible). Judgment —
   choosing relevant topics, ranking them, writing the blog prose — lives in the
   `SKILL.md` body and is done by the model.
2. **Three-tier loading.** `SKILL.md` stays short and routes to `references/`
   for detail loaded only when needed.
3. **No hardcoded secrets or operator paths.** Config stores env-var *names*,
   never secret values. Target paths come from config, not from source, so a
   teammate can run the skill against their own site.
4. **Config carries business logic, code carries machinery.** Personas, schema,
   categories, authors, cadence — all config. The scripts only parse, validate,
   run, and store.

## 3. Repository layout

```
blog-pipeline/
├── SKILL.md                        # routing + judgment (research ranking, blog writing)
├── scripts/                        # deterministic, unit-tested
│   ├── config.py                   #   load / validate / write config.json (schema-checked)
│   ├── existing.py                 #   list target's existing blog slugs; dedupe candidates
│   ├── validate_blog.py            #   assert a generated blog file matches the target schema
│   ├── channels/                   #   review-channel adapters (post list / read reply)
│   │   ├── base.py                 #     adapter interface
│   │   ├── slack.py                #     Slack (webhook + bot token) — default
│   │   └── cli.py                  #     stdout + arg — zero-setup fallback
│   ├── runstate.py                 #   per-run state machine read/write
│   └── install_cron.py             #   install crontab / launchd entry from config
├── references/
│   ├── personas.md                 #   default persona seed + how personas steer research
│   ├── blog-schema.md              #   target-agnostic schema description + house-style guide
│   └── pipeline.md                 #   stage + gate state-machine spec
├── examples/
│   ├── config.example.json         #   annotated template
│   ├── config.filled.example.json  #   fully filled worked example (first user, sanitized)
│   ├── sample-run.json             #   a run file mid-pipeline
│   └── sample-blog.json            #   a validated blog file
├── assets/
│   └── deploy.sh.tmpl              #   deploy-script template rendered by setup
├── tests/                          #   python -m unittest: config, validate_blog, existing, runstate
├── README.md
├── LICENSE                         # MIT
└── .gitignore
```

## 4. Sub-commands

The user invokes the skill and names a sub-command (or the cron calls one). The
`SKILL.md` body routes to the right stage.

| Command | Trigger | Responsibility |
|---|---|---|
| `setup` | interactive, once | Build/edit personas; ask topics-per-run, blogs-per-run, frequency, cron time, gate mode, review mechanism, deploy method, review channel; write `config.json`; render `deploy.sh`; install cron. |
| `research` | cron entry | Research per persona → dedupe vs existing slugs → rank → produce top-N topics → post numbered list to the review channel → save run file (`awaiting_topic_approval`). |
| `draft` | after topic pick | Read the Slack reply (or arg) → for each selected topic, write a blog file → validate → commit to `blog/draft-<date>` branch → push → post per-blog preview URLs to Slack (`awaiting_content_approval`). |
| `deploy` | after content approval | Run the rendered deploy script (merge draft branch → main → prod) → confirm in Slack (`published`). |
| `status` | anytime | Print the current run's state and next action. |

### Pick argument contract

Both gates accept the human's selection through one canonical parser
(`runstate.parse_picks`), so the manual and poll paths behave identically:

- `all` → every posted item, capped at `blogsPerRun`.
- comma/space list of 1-based indices → `1,3,5` or `1 3 5`.
- comma/space list of slugs → matched against the run file's posted items.

`SKILL.md` passes the operator's inline arg to the same parser that the
review-channel adapter feeds the fetched reply into. Out-of-range or unmatched
picks are reported, not silently dropped.

### Gate advancement (configurable)

Each of the two human gates (topic approval, content approval) uses the **same**
manual/poll mechanism, selected independently via `gates.topicApproval` and
`gates.contentApproval`:

- **manual** — the human runs the next sub-command themselves after replying on
  the review channel. Simplest, fully in the operator's control.
- **poll** — a lightweight scheduled job re-invokes the skill, which reads the
  review channel for the approval reply and auto-advances.

Both cron time and gate mode are chosen in `setup` and stored in config.

## 5. Configuration schema

`config.json` (validated by `scripts/config.py`):

```jsonc
{
  "target": {
    "repoPath": "/abs/path/to/site",        // where the site repo lives
    "contentDir": "frontend/content/blog",   // dir holding blog files
    "blogFormat": "json",                    // json | md | mdx
    "categories": ["accounting", "tech"],    // valid category keys
    "authors": [                             // author registry for auto-resolve
      { "id": "vaishnav-gupta", "category": "accounting" },
      { "id": "ujjwal-singh",   "category": "tech" }
    ],
    "defaultCoverImage": "https://…"
  },
  "personas": [
    { "id": "cpa", "name": "CPAs & accounting firms",
      "pains": ["month-end close", "multi-client reporting"],
      "keywords": ["QBO", "consolidation"] }
    // … solopreneur, restaurant, hospital, construction, accountant
  ],
  "topicsPerRun": 10,
  "blogsPerRun": 3,
  "frequency": "daily",
  "cron": "0 12 * * *",
  "scheduler": "crontab",                    // crontab | launchd | schedule-skill
  "gates": { "topicApproval": "manual", "contentApproval": "manual" },
  "reviewChannel": {                         // where topic lists & preview links go
    "type": "slack",                         // slack | cli | email | …
    "slack": {
      "channelId": "C0…",
      "webhookEnv": "BLOG_PIPELINE_SLACK_WEBHOOK",   // env var NAME, not value
      "botTokenEnv": "BLOG_PIPELINE_SLACK_BOT_TOKEN"
    }
  },
  "review": { "mode": "vercel-preview", "branchPrefix": "blog/draft-" },
  "deploy": { "mode": "git-push", "script": "scripts/blog-deploy.sh",
              "remote": "origin", "target": "main" }
}
```

Config location: `<target.repoPath>/.blog-pipeline/config.json` so it travels
with the site repo, not the skill repo.

### Enumerated values (single source of truth, no magic strings)

`scripts/config.py` defines these enums and validates against them:

- `target.blogFormat` ∈ `json | md | mdx`
- `scheduler` ∈ `crontab | launchd | schedule-skill`
- `gates.topicApproval`, `gates.contentApproval` ∈ `manual | poll`
- `reviewChannel.type` ∈ `slack | cli | email` (Slack shipped in v1)
- `review.mode` ∈ `vercel-preview | local-dev | inline`
- `deploy.mode` ∈ `git-push | vercel-cli`

`deploy.remote` + `deploy.target` name the git remote and prod branch the deploy
script pushes to (e.g. `origin` / `main`). The deploy-script template reads both
from config rather than inferring them.

## 6. Run-state machine

Per-run file: `<repoPath>/.blog-pipeline/runs/YYYY-MM-DD.json`, managed by
`scripts/runstate.py`. States:

```
researching
  → awaiting_topic_approval   (topics posted to review channel)
  → drafting
  → awaiting_content_approval (preview URLs posted to review channel)
  → deploying
  → published
```

The file records: date, status, `topics[]` (title, persona, angle, keyword,
rationale), `selected[]` (indices/slugs the human picked), `drafted[]` (slug,
file path, preview URL), `deploy` (branch, commit, prod URL), and timestamps.
Every stage is **idempotent** and keyed by date, so re-running a stage is safe
(it reads the file, resumes from the recorded status).

## 7. Stage detail

### 7.1 research (judgment + code)
- Code: `existing.py` lists all current blog slugs from `contentDir`.
- Model: for each persona, WebSearch for timely, relevant angles (accounting
  standards changes, seasonal close tasks, tool comparisons, pain points). Draw a
  candidate pool, drop anything whose slug/topic duplicates an existing post,
  rank for relevance + freshness + audience spread, and select the top
  `topicsPerRun`.
- Code: the review-channel adapter posts a numbered list; `runstate.py` writes
  the run file.

### 7.2 draft (judgment + code)
- Code: the review-channel adapter reads the human's reply (e.g. `1,3,5` or
  `all`), capped at `blogsPerRun`.
- Model: for each selected topic, write a full blog in the target's format,
  following `references/blog-schema.md` house style; category set, author
  auto-resolved from category, slug generated, excerpt, structured data.
- Code: `validate_blog.py` asserts the file matches the schema (required fields,
  valid category, unique slug). Then commit to the draft branch and push; the
  target's Vercel project auto-builds a preview. The review-channel adapter posts
  one preview URL per blog (`<previewBase>/blog/<slug>`).

### 7.3 deploy (code)
- Code: on approval, run the rendered `deploy.sh` — verify clean tree, merge the
  draft branch into `deploy.target`, push (Vercel builds prod), print the
  deployment URL. The review-channel adapter posts confirmation. `runstate.py` →
  `published`.

## 8. Review channel (pluggable, Slack default)

The review channel is the seam through which topic lists and preview links go out
and approvals come back. It is a small **adapter interface** so the *what* (post
a list, read the reply) is fixed while the *how* (Slack, CLI, email) is
configurable via `reviewChannel.type`:

```
post_topics(run)      → publish the numbered topic list
post_previews(run)    → publish per-blog preview URLs
read_reply(run)       → fetch the human's pick/approval (poll gate only)
post_confirmation(run)→ announce the deploy
```

**`scripts/channels/slack.py`** is the v1 implementation, self-contained and
cron-safe:
- **post** via an incoming webhook (`webhookEnv`).
- **read** replies via the bot token (`botTokenEnv`, `conversations.history` /
  `conversations.replies` on `channelId`).

Secrets are read from environment variables *named* in config; values never touch
the repo. A `cli` adapter (prints to stdout, reads the pick as a sub-command arg)
ships as the zero-setup fallback so the pipeline is usable before any Slack setup.
In an interactive session the operator can always paste picks as a sub-command
arg, bypassing the read path entirely.

## 9. Deploy script generation

`setup` renders `assets/deploy.sh.tmpl` into `<repoPath>/scripts/blog-deploy.sh`
with the target's branch names and remote filled in. The script is committed to
the *target* repo (not the skill repo). Generic steps: guard clean tree →
checkout/merge draft branch → push to prod branch → emit deployment URL. If the
target uses `vercel --prod` instead of git-push auto-deploy, setup captures that
and the template branches accordingly.

## 10. Testing

`tests/` (stdlib `unittest`, no network):
- `test_config.py` — schema validation: rejects missing target fields, bad
  format enum, secret *values* placed in config (must be env names).
- `test_validate_blog.py` — accepts a good blog, rejects missing required
  fields / invalid category / duplicate slug.
- `test_existing.py` — slug listing + dedupe against a fixture content dir.
- `test_runstate.py` — legal state transitions; illegal transition raises;
  idempotent re-write.
- `test_channels.py` — the `cli` adapter posts/reads without network; the Slack
  adapter is unit-tested against a stubbed HTTP layer (no live calls).

Live Slack, cron install, and deploy are integration-tested manually (documented
in README) since they touch external systems.

### Acceptance gate — skill-doctor

Because `blog-pipeline` is itself a Claude Code skill, its `SKILL.md` must pass
`skill-doctor` before the work is considered done:

```
python3 ~/self/skill-doctor/scripts/audit.py ~/self/blog-pipeline --json
```

Every `error` and `warn` finding is resolved (frontmatter/name/description
correctness, no hardcoded secrets, no hardcoded operator paths, body not bloated,
references properly routed). The description is then judged against skill-doctor's
gate rubric (states *what it does* **and** *when to use it*, enumerates the words
the operator would type, closes the escape hatch). Finally, skill-doctor's paired
eval scaffolding produces candidate trigger prompts + assertions; the skill is
not called good on the static audit alone.

## 11. Error handling

- Review-channel post fails → abort the stage, leave run file at prior status,
  surface the error. Re-running the stage retries.
- No new topics (all candidates dedupe out) → post "nothing new today" to the
  review channel,
  mark run `published` (no-op) so cron doesn't loop.
- `validate_blog.py` fails on a draft → skip that blog, keep the rest, report
  which failed; do not push an invalid file.
- Vercel preview build fails → the branch stays; operator inspects; deploy is
  never auto-triggered on a failed preview.
- Deploy guard finds a dirty tree → abort with a clear message.

## 12. FinBoard as first user

`examples/config.filled.example.json` fills the schema for the first user (FinBoard), sanitized:
`repoPath=<site repo>`, `contentDir=frontend/content/blog`,
`blogFormat=json`, categories `accounting`/`tech`, authors `vaishnav-gupta`
(accounting) / `ujjwal-singh` (tech), Vercel preview review, deploy by
git-push to `main` on `finboard-dev/app`. Personas: accounting firm,
solopreneur, restaurant, hospital, construction, CPA/accountant. `blogsPerRun=3`,
`topicsPerRun=10`, cron `0 12 * * *`.

## 13. Open items deferred (YAGNI)

- Cover-image generation (could later call an image skill).
- Multi-channel publish (LinkedIn/X) — out of scope for v1.
- Analytics feedback loop to bias future topic selection — future.
```
