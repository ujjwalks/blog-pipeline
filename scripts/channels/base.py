"""Review-channel adapter seam for blog-pipeline.

The review channel is the pipe through which topic lists and preview links go
out and approvals come back. The *what* (post a list, read the reply) is fixed
here; the *how* (Slack, CLI, email) is an adapter chosen by
cfg["reviewChannel"]["type"]. Formatting is shared so every adapter posts the
exact same message a human replies to -- parse_picks() in runstate.py then
parses that reply identically regardless of transport.

Adapters must never print or log secret values; secrets are env var NAMES in
config and are resolved only inside the adapter that needs them.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `channels.*`, `config`, `runstate` importable whether this module is
# imported as part of the package or run from inside scripts/channels/.
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


class ChannelError(Exception):
    """Raised when a channel cannot post or read (config, env, or HTTP)."""


class Channel:
    """Adapter interface. Subclasses implement transport, nothing else.

    Every method takes (run, cfg): the run dict from runstate.load_run and the
    validated config from config.load_config. post_* methods may annotate the
    run dict (e.g. run["channel"]) -- the caller is responsible for saving it.
    """

    def post_topics(self, run: dict, cfg: dict) -> None:
        raise NotImplementedError

    def post_previews(self, run: dict, cfg: dict) -> None:
        raise NotImplementedError

    def post_confirmation(self, run: dict, cfg: dict) -> None:
        raise NotImplementedError

    def read_reply(self, run: dict, cfg: dict) -> str | None:
        """Poll gate only. Returns the human's reply text, or None if no
        reply has arrived yet. Manual gates bypass this entirely (the pick is
        passed as a sub-command arg)."""
        raise NotImplementedError


# --- Shared formatting (single source of truth for gate messages) ---

TOPICS_INSTRUCTION = "Reply with numbers to draft, e.g. 1,3,5 or all"
PREVIEWS_INSTRUCTION = "Reply 'approve' to publish, or numbers to publish a subset"


def format_topics(run: dict) -> str:
    """Numbered topic list: title -- persona -- angle -- target prompt -- why now."""
    lines = [f"Blog topics for {run['date']}:"]
    for i, t in enumerate(run.get("topics", []), start=1):
        parts = [
            t.get("title", "(untitled)"),
            t.get("persona", ""),
            t.get("angle", ""),
            t.get("keyword", ""),
            t.get("rationale", ""),
        ]
        lines.append(f"{i}. " + " — ".join(p for p in parts if p))
    lines.append(TOPICS_INSTRUCTION)
    return "\n".join(lines)


def format_previews(run: dict) -> str:
    """Numbered slug + preview URL per drafted blog, asking for approval."""
    lines = [f"Draft previews for {run['date']}:"]
    for i, d in enumerate(run.get("drafted", []), start=1):
        lines.append(f"{i}. {d.get('slug', '(no slug)')} — {d.get('previewUrl', '(no preview URL)')}")
    lines.append(PREVIEWS_INSTRUCTION)
    return "\n".join(lines)


def format_confirmation(run: dict) -> str:
    """Published URLs after deploy."""
    urls = run.get("deploy", {}).get("prodUrls", [])
    lines = [f"Published for {run['date']}:"]
    if urls:
        lines.extend(f"- {u}" for u in urls)
    else:
        lines.append("- (no URLs recorded)")
    return "\n".join(lines)


# --- Dispatch ---

def get_channel(cfg: dict) -> Channel:
    """Return the adapter for cfg["reviewChannel"]["type"].

    Imports lazily so channels.slack / channels.cli can import this module
    without a cycle, and so an unused adapter's dependencies never load.
    """
    ctype = cfg.get("reviewChannel", {}).get("type")
    if ctype == "slack":
        from channels.slack import SlackChannel
        return SlackChannel()
    if ctype == "cli":
        from channels.cli import CliChannel
        return CliChannel()
    if ctype == "email":
        raise ChannelError("email adapter not implemented in v1")
    raise ChannelError(f"unknown reviewChannel.type: {ctype!r}")
