# blog-pipeline

**A config-driven Claude Code skill that runs a recurring blog production
pipeline for any website.** It researches topic ideas per audience persona,
posts a top-N list to your review channel, drafts the topics you pick in your
site's own blog format, pushes a preview for review, and deploys on your
approval. Nothing about any one website is hardcoded; the target site,
personas, cadence, channels, and deploy method all live in a config file that
travels with the site repo.

> research -> topic list -> human picks -> draft -> preview links -> human approves -> deploy

## The two mandatory gates

Nothing drafts without topic approval, and nothing deploys without content
approval. The state machine (`scripts/runstate.py`) enforces this: the
drafting state is only reachable after a human picks topics, and deploying is
only reachable after a human approves the previews. Each gate runs in `manual`
mode (you reply, then run the next sub-command) or `poll` mode (a scheduled
invocation reads your channel reply and advances), configured independently.

## Quickstart

```bash
git clone git@github.com:ujjwalks-ai/blog-pipeline.git
ln -s "$(pwd)/blog-pipeline" ~/.claude/skills/blog-pipeline
```

Then in a Claude Code session:

> Set up the blog pipeline for my site

The interactive `setup` stage walks you through personas, cadence, review
channel, and deploy, writes the config, renders the deploy script into your
repo, and installs the cron entry. If you chose Slack, export the two env
vars whose names you gave during setup (webhook URL and bot token), for
example `BLOG_PIPELINE_SLACK_WEBHOOK` and `BLOG_PIPELINE_SLACK_BOT_TOKEN`.
Done; the next scheduled run posts a topic list to your channel.

## Sub-commands

| Sub-command | When |
|---|---|
| `setup` | first use, or changing personas, cadence, or channels |
| `research` | the scheduled entry point; produces and posts the topic list |
| `draft` | after you picked topics on the review channel |
| `deploy` | after you approved the previews |
| `status` | anything else; shows where the current run is stuck |

Say it in plain words ("do the daily blogs", "draft picks 1 and 3", "deploy
the approved posts") and the skill routes to the right stage.

## How state works

Two files, both in the target site's repo so they travel with it:

- `<repo>/.blog-pipeline/config.json` holds every business choice: target
  paths and blog format, categories and authors, personas, topics and blogs
  per run, cron schedule, gate modes, review channel, deploy method. Validated
  by `scripts/config.py`; secrets are referenced by env var name only, and a
  config containing a secret value is rejected.
- `<repo>/.blog-pipeline/runs/YYYY-MM-DD.json` is the per-run state file:
  status, topics, picks, drafted files with preview URLs, deploy result, and
  a full status history. Every stage is idempotent; re-running a stage resumes
  from the recorded status. See `references/pipeline.md` for the state
  machine.

## The deterministic/judgment split

Same philosophy as [skill-doctor](https://github.com/ujjwalks-ai/skill-doctor):
express as code what you can, and let the model do only what needs judgment.

Scripts (deterministic, unit-tested, stdlib-only): config validation, existing
slug listing and dedupe, blog file validation (schema plus prose cleanliness,
including the no-em-dash rule), run-state transitions, pick parsing, channel
adapters, cron install, deploy.

Model (judgment, guided by `SKILL.md` and `references/`): which topics matter
to which persona right now, how to rank them, and the blog prose itself.

If a business behavior needs to change, you edit config or a reference file,
not code.

## Slack note

Post as a **bot** (webhook plus bot token), not as yourself. Slack does not
notify you about your own messages, so a pipeline that posts through an MCP
connection or any user-identity token notifies nobody, and the review gate
silently stalls. With a bot identity the operator gets a real notification
when the topic list or preview links land.

## Development

```bash
python3 -m unittest discover -s tests
```

Tests are stdlib `unittest` with no network. Live Slack, cron install, and
deploy are integration-tested manually.

## Roadmap

- **v1:** Slack and CLI review channels, git-push and Vercel CLI deploys
- **later:** email review-channel adapter
- **later:** cover image generation

## Credit

The design follows *The Art of Writing Skills* (three-tier loading, config
over code, description-as-gate) and is a sibling of
[skill-doctor](https://github.com/ujjwalks-ai/skill-doctor), which audits
skills built this way, including this one.

**Get the book -> [The Art of Writing Skills](https://topmate.io/ujjwal_k_singh/2199504)**

## License

MIT, see [LICENSE](LICENSE).
