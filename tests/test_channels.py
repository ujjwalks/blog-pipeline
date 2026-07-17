"""Tests for the review-channel adapters and the scheduler installer.

No network, no crontab writes: Slack HTTP is stubbed by patching
urllib.request.urlopen; install_cron is exercised only through its pure
line-builder and the --dry-run path.
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from channels.base import (  # noqa: E402
    ChannelError,
    TOPICS_INSTRUCTION,
    format_previews,
    format_topics,
    get_channel,
)
from channels.cli import CliChannel  # noqa: E402
from channels.slack import SlackChannel  # noqa: E402
import install_cron  # noqa: E402

UNSET_WEBHOOK_ENV = "TEST_BLOG_WEBHOOK_UNSET_XYZ"
SET_WEBHOOK_ENV = "TEST_BLOG_WEBHOOK_SET_XYZ"
SET_BOT_TOKEN_ENV = "TEST_BLOG_BOT_TOKEN_XYZ"
WEBHOOK_URL = "https://example.invalid/webhook/abc"


def make_cfg(channel_type="slack", webhook_env=SET_WEBHOOK_ENV):
    return {
        "target": {
            "repoPath": "/tmp/example-site",
            "contentDir": "content/blog",
            "blogFormat": "mdx",
            "categories": ["accounting"],
        },
        "personas": [{"id": "controller", "name": "Controller Cathy"}],
        "cron": "0 12 * * *",
        "scheduler": "crontab",
        "reviewChannel": {
            "type": channel_type,
            "slack": {
                "channelId": "C123456",
                "webhookEnv": webhook_env,
                "botTokenEnv": SET_BOT_TOKEN_ENV,
            },
        },
    }


def make_run():
    return {
        "date": "2026-07-18",
        "status": "awaiting_topic_approval",
        "topics": [
            {
                "title": "Month-end close checklist",
                "persona": "controller",
                "angle": "seasonal close tasks",
                "keyword": "month end close checklist",
                "rationale": "Q3 close is approaching",
            },
            {
                "title": "QBO vs Xero for multi-entity",
                "persona": "controller",
                "angle": "tool comparison",
                "keyword": "qbo vs xero consolidation",
                "rationale": "high search interest",
            },
        ],
        "selected": [],
        "drafted": [
            {"slug": "month-end-close", "file": "a.mdx", "previewUrl": "https://preview.example/blog/month-end-close"},
        ],
        "deploy": {},
        "history": [],
    }


class FakeResponse:
    def __init__(self, body=b"ok", status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestGetChannel(unittest.TestCase):
    def test_dispatch_cli(self):
        self.assertIsInstance(get_channel(make_cfg("cli")), CliChannel)

    def test_dispatch_slack(self):
        self.assertIsInstance(get_channel(make_cfg("slack")), SlackChannel)

    def test_email_raises(self):
        with self.assertRaises(ChannelError) as ctx:
            get_channel(make_cfg("email"))
        self.assertIn("email adapter not implemented", str(ctx.exception))

    def test_unknown_raises(self):
        with self.assertRaises(ChannelError):
            get_channel(make_cfg("carrier-pigeon"))


class TestFormatting(unittest.TestCase):
    def test_format_topics_numbering_and_instruction(self):
        text = format_topics(make_run())
        self.assertIn("1. Month-end close checklist", text)
        self.assertIn("2. QBO vs Xero for multi-entity", text)
        self.assertIn("controller", text)
        self.assertIn("month end close checklist", text)  # target prompt
        self.assertIn("Q3 close is approaching", text)  # why now
        self.assertTrue(text.endswith(TOPICS_INSTRUCTION))
        self.assertIn("Reply with numbers to draft, e.g. 1,3,5 or all", text)

    def test_format_previews_lists_slug_and_url(self):
        text = format_previews(make_run())
        self.assertIn("1. month-end-close", text)
        self.assertIn("https://preview.example/blog/month-end-close", text)


class TestCliChannel(unittest.TestCase):
    def test_post_topics_prints(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            CliChannel().post_topics(make_run(), make_cfg("cli"))
        out = buf.getvalue()
        self.assertIn("1. Month-end close checklist", out)
        self.assertIn(TOPICS_INSTRUCTION, out)

    def test_read_reply_is_none(self):
        self.assertIsNone(CliChannel().read_reply(make_run(), make_cfg("cli")))


class TestSlackChannel(unittest.TestCase):
    def test_post_raises_when_env_missing(self):
        cfg = make_cfg(webhook_env=UNSET_WEBHOOK_ENV)
        os.environ.pop(UNSET_WEBHOOK_ENV, None)
        with self.assertRaises(ChannelError) as ctx:
            SlackChannel().post_topics(make_run(), cfg)
        # Error names the env var; never a URL/value.
        self.assertIn(UNSET_WEBHOOK_ENV, str(ctx.exception))
        self.assertNotIn("http", str(ctx.exception))

    def test_post_happy_path(self):
        run = make_run()
        with mock.patch.dict(os.environ, {SET_WEBHOOK_ENV: WEBHOOK_URL}), \
                mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as m:
            SlackChannel().post_topics(run, make_cfg())
        request = m.call_args[0][0]
        self.assertEqual(request.full_url, WEBHOOK_URL)  # URL came from env
        payload = json.loads(request.data.decode("utf-8"))
        self.assertIn("Month-end close checklist", payload["text"])
        self.assertIn(TOPICS_INSTRUCTION, payload["text"])
        self.assertTrue(run["channel"]["posted"])

    def _read(self, messages, run=None):
        body = json.dumps({"ok": True, "messages": messages}).encode("utf-8")
        with mock.patch.dict(os.environ, {SET_BOT_TOKEN_ENV: "token-value"}), \
                mock.patch("urllib.request.urlopen", return_value=FakeResponse(body=body)):
            return SlackChannel().read_reply(run or make_run(), make_cfg())

    def test_read_reply_none_when_no_messages(self):
        self.assertIsNone(self._read([]))

    def test_read_reply_returns_human_text(self):
        messages = [
            {"bot_id": "B01", "text": "1. Month-end close checklist ..."},
            {"user": "U42", "text": "1,2"},
        ]
        self.assertEqual(self._read(messages), "1,2")


class TestInstallCron(unittest.TestCase):
    def test_build_cron_line(self):
        line = install_cron.build_cron_line(make_cfg(), "/tmp/example-site", command="my-cmd")
        self.assertEqual(
            line,
            "0 12 * * * cd /tmp/example-site && my-cmd # blog-pipeline:/tmp/example-site",
        )

    def test_build_cron_line_default_command(self):
        line = install_cron.build_cron_line(make_cfg(), "/tmp/example-site")
        self.assertIn('claude -p "Run the blog-pipeline research stage', line)
        self.assertTrue(line.endswith("# blog-pipeline:/tmp/example-site"))

    def test_install_dry_run_never_shells_out(self):
        with mock.patch.object(install_cron.subprocess, "run") as m:
            summary = install_cron.install(
                make_cfg(), "/tmp/example-site", command="my-cmd", dry_run=True
            )
        m.assert_not_called()
        self.assertIn("[dry-run]", summary)
        self.assertIn(
            "0 12 * * * cd /tmp/example-site && my-cmd # blog-pipeline:/tmp/example-site",
            summary,
        )


if __name__ == "__main__":
    unittest.main()
