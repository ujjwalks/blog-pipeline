"""Slack review-channel adapter for blog-pipeline.

Posts gate messages via an incoming webhook and reads replies via the Slack
Web API (conversations.history) with a bot token.

Design note -- why a bot, not MCP/user-identity posting: Slack never notifies
you of your OWN messages. If the pipeline posted as the operator (via an MCP
user token or similar), the topic list and preview links would land silently
and the gate would stall until the operator happened to open the channel. A
bot identity can @mention the operator and trigger a real notification, which
is the whole point of a review gate. So posts deliberately come from a bot.

Secrets: config stores env var NAMES (webhookEnv, botTokenEnv); values are
read from os.environ here and are never printed, logged, or echoed in errors.
HTTP error messages carry only the status code -- response bodies can echo
the webhook URL.

CLI (cron-safe, no interactivity):
    python3 slack.py post <repo> <date> topics|previews|confirmation
    python3 slack.py read <repo> <date>
Exit codes: 0 ok, 1 error, 3 (read) no reply yet.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from channels.base import (
    Channel,
    ChannelError,
    format_confirmation,
    format_previews,
    format_topics,
)
from config import ConfigError, load_config
from runstate import load_run, save_run

HTTP_TIMEOUT_SECONDS = 10
CONVERSATIONS_HISTORY_URL = "https://slack.com/api/conversations.history"
HISTORY_LIMIT = 50

# CLI vocabulary (mirrors nothing; the single definition)
CMD_POST = "post"
CMD_READ = "read"
POST_KINDS = ("topics", "previews", "confirmation")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_REPLY = 3


def _slack_cfg(cfg: dict) -> dict:
    return cfg.get("reviewChannel", {}).get("slack", {})


def _env_secret(env_name: str | None, what: str) -> str:
    """Resolve a secret by env var NAME. Errors name the variable, never the value."""
    if not env_name:
        raise ChannelError(f"reviewChannel.slack.{what}: no env var name configured")
    value = os.environ.get(env_name)
    if not value:
        raise ChannelError(f"environment variable {env_name} is not set (needed for {what})")
    return value


def _http_json(request: urllib.request.Request) -> dict:
    """Execute a request; return parsed JSON body ({} if not JSON).

    Raises ChannelError carrying only the HTTP status -- never the body or
    URL, which could echo the webhook secret.
    """
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", 200)
            if not 200 <= status < 300:
                raise ChannelError(f"slack HTTP {status}")
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise ChannelError(f"slack HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ChannelError(f"slack request failed: {exc.reason}") from None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


class SlackChannel(Channel):
    def _post(self, message: str, run: dict, cfg: dict) -> None:
        webhook_url = _env_secret(_slack_cfg(cfg).get("webhookEnv"), "webhookEnv")
        request = urllib.request.Request(
            webhook_url,
            data=json.dumps({"text": message}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _http_json(request)
        # Webhooks return no message ts; record that (and when) we posted so
        # read_reply can scope its scan. Caller saves the run.
        run["channel"] = {
            "posted": True,
            "postedAt": datetime.now(timezone.utc).isoformat(),
        }

    def post_topics(self, run: dict, cfg: dict) -> None:
        self._post(format_topics(run), run, cfg)

    def post_previews(self, run: dict, cfg: dict) -> None:
        self._post(format_previews(run), run, cfg)

    def post_confirmation(self, run: dict, cfg: dict) -> None:
        self._post(format_confirmation(run), run, cfg)

    def read_reply(self, run: dict, cfg: dict) -> str | None:
        """Newest human (non-bot) message since our post, or None."""
        slack = _slack_cfg(cfg)
        channel_id = slack.get("channelId")
        if not channel_id:
            raise ChannelError("reviewChannel.slack.channelId: required to read replies")
        token = _env_secret(slack.get("botTokenEnv"), "botTokenEnv")

        params = {"channel": channel_id, "limit": str(HISTORY_LIMIT)}
        posted_ts = run.get("channel", {}).get("postedTs")
        if posted_ts:
            params["oldest"] = str(posted_ts)
        request = urllib.request.Request(
            CONVERSATIONS_HISTORY_URL + "?" + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        data = _http_json(request)
        if not data.get("ok"):
            raise ChannelError(f"slack API error: {data.get('error', 'unknown')}")

        # conversations.history returns newest first; take the first human,
        # plain-text message (skip anything a bot posted, including our own).
        for msg in data.get("messages", []):
            if msg.get("bot_id") or msg.get("subtype"):
                continue
            text = (msg.get("text") or "").strip()
            if text:
                return text
        return None


def main(argv):
    usage = (
        "usage: slack.py post <target-repo-path> <YYYY-MM-DD> topics|previews|confirmation\n"
        "       slack.py read <target-repo-path> <YYYY-MM-DD>"
    )
    if len(argv) < 4 or argv[1] not in (CMD_POST, CMD_READ):
        print(usage)
        return 2
    command, repo, date = argv[1], argv[2], argv[3]

    try:
        cfg = load_config(repo)
        run = load_run(repo, date)
        if run is None:
            print(f"no run for {date} in {repo}")
            return EXIT_ERROR
        channel = SlackChannel()

        if command == CMD_POST:
            if len(argv) != 5 or argv[4] not in POST_KINDS:
                print(usage)
                return 2
            kind = argv[4]
            {
                "topics": channel.post_topics,
                "previews": channel.post_previews,
                "confirmation": channel.post_confirmation,
            }[kind](run, cfg)
            save_run(repo, run)
            print(f"posted {kind} for {date}")
            return EXIT_OK

        reply = channel.read_reply(run, cfg)
        if reply is None:
            print("no reply yet")
            return EXIT_NO_REPLY
        print(reply)
        return EXIT_OK
    except (ChannelError, ConfigError) as exc:
        print(f"error: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv))
