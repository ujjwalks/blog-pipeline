"""Config loader/validator for blog-pipeline.

The config carries ALL business choices (target site, personas, cadence,
channels, gates, deploy). Code stays generic; this module is the single
definition of the config vocabulary. Secrets are referenced by environment
variable NAME only -- a config containing a secret VALUE is rejected.

Config lives at <target.repoPath>/.blog-pipeline/config.json so it travels
with the site repo, not the skill repo.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# --- Canonical enums (single source of truth; mirrored nowhere) ---

BLOG_FORMATS = ("json", "md", "mdx")
SCHEDULERS = ("crontab", "launchd", "schedule-skill")
GATE_MODES = ("manual", "poll")
CHANNEL_TYPES = ("slack", "cli", "email")
REVIEW_MODES = ("vercel-preview", "local-dev", "inline")
DEPLOY_MODES = ("git-push", "vercel-cli")

CONFIG_DIRNAME = ".blog-pipeline"
CONFIG_FILENAME = "config.json"
RUNS_DIRNAME = "runs"

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")

# Patterns that indicate a secret VALUE was pasted where an env NAME belongs.
SECRET_VALUE_PATTERNS = (
    re.compile(r"hooks\.slack\.com"),
    re.compile(r"xox[abprs]-"),
    re.compile(r"https?://"),
)


class ConfigError(Exception):
    """Raised when a config fails validation. str(err) lists every problem."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(f"- {e}" for e in self.errors))


def config_path(repo_path: str | Path) -> Path:
    return Path(repo_path) / CONFIG_DIRNAME / CONFIG_FILENAME


def runs_dir(repo_path: str | Path) -> Path:
    return Path(repo_path) / CONFIG_DIRNAME / RUNS_DIRNAME


def _require(cfg: dict, dotted: str, errors: list) -> object:
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            errors.append(f"missing required field: {dotted}")
            return None
        node = node[part]
    return node


def _check_enum(value, allowed: tuple, dotted: str, errors: list) -> None:
    if value is not None and value not in allowed:
        errors.append(f"{dotted}: {value!r} not in {list(allowed)}")


def _check_env_name(value, dotted: str, errors: list) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not ENV_NAME_RE.match(value):
        errors.append(
            f"{dotted}: must be an ENVIRONMENT VARIABLE NAME (e.g. BLOG_SLACK_WEBHOOK), got {value!r}"
        )
        return
    for pat in SECRET_VALUE_PATTERNS:
        if pat.search(value):
            errors.append(f"{dotted}: looks like a secret VALUE, store the env var name instead")


def validate_config(cfg: dict) -> list:
    """Return a list of human-readable problems. Empty list == valid."""
    errors: list = []
    if not isinstance(cfg, dict):
        return ["config root must be a JSON object"]

    repo = _require(cfg, "target.repoPath", errors)
    if repo is not None and not str(repo).startswith("/"):
        errors.append("target.repoPath: must be an absolute path")
    _require(cfg, "target.contentDir", errors)
    fmt = _require(cfg, "target.blogFormat", errors)
    _check_enum(fmt, BLOG_FORMATS, "target.blogFormat", errors)
    cats = _require(cfg, "target.categories", errors)
    if cats is not None and (not isinstance(cats, list) or not cats):
        errors.append("target.categories: must be a non-empty list of category keys")

    personas = _require(cfg, "personas", errors)
    if personas is not None:
        if not isinstance(personas, list) or not personas:
            errors.append("personas: must be a non-empty list")
        else:
            for i, p in enumerate(personas):
                for field in ("id", "name"):
                    if not isinstance(p, dict) or not p.get(field):
                        errors.append(f"personas[{i}].{field}: required")

    for field, default in (("topicsPerRun", 10), ("blogsPerRun", 3)):
        val = cfg.get(field, default)
        if not isinstance(val, int) or val < 1:
            errors.append(f"{field}: must be a positive integer")

    _check_enum(cfg.get("scheduler"), SCHEDULERS, "scheduler", errors)

    gates = cfg.get("gates", {})
    for gate in ("topicApproval", "contentApproval"):
        _check_enum(gates.get(gate, "manual"), GATE_MODES, f"gates.{gate}", errors)

    channel = _require(cfg, "reviewChannel.type", errors)
    _check_enum(channel, CHANNEL_TYPES, "reviewChannel.type", errors)
    if channel == "slack":
        slack = cfg.get("reviewChannel", {}).get("slack", {})
        if not slack.get("channelId"):
            errors.append("reviewChannel.slack.channelId: required for slack channel")
        _check_env_name(slack.get("webhookEnv"), "reviewChannel.slack.webhookEnv", errors)
        _check_env_name(slack.get("botTokenEnv"), "reviewChannel.slack.botTokenEnv", errors)

    review = cfg.get("review", {})
    _check_enum(review.get("mode"), REVIEW_MODES, "review.mode", errors)

    deploy = cfg.get("deploy", {})
    _check_enum(deploy.get("mode"), DEPLOY_MODES, "deploy.mode", errors)
    for field in ("remote", "target"):
        if deploy and not deploy.get(field):
            errors.append(f"deploy.{field}: required (e.g. origin / main)")

    return errors


def load_config(repo_path: str | Path) -> dict:
    """Load and validate the config for a target repo. Raises ConfigError."""
    path = config_path(repo_path)
    if not path.exists():
        raise ConfigError([f"no config at {path} -- run the setup stage first"])
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError([f"config is not valid JSON: {exc}"])
    errors = validate_config(cfg)
    if errors:
        raise ConfigError(errors)
    return cfg


def write_config(cfg: dict, repo_path: str | Path) -> Path:
    """Validate then write. Never writes an invalid config."""
    errors = validate_config(cfg)
    if errors:
        raise ConfigError(errors)
    path = config_path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    return path


def main(argv):
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print("usage: config.py <target-repo-path>   # validate the target's config")
        return 2
    try:
        cfg = load_config(argv[1])
    except ConfigError as exc:
        print("INVALID:")
        print(exc)
        return 1
    print(f"OK: {config_path(argv[1])}")
    print(f"  personas: {[p['id'] for p in cfg['personas']]}")
    print(f"  topics/run: {cfg.get('topicsPerRun', 10)}  blogs/run: {cfg.get('blogsPerRun', 3)}")
    print(f"  channel: {cfg['reviewChannel']['type']}  review: {cfg.get('review', {}).get('mode')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
