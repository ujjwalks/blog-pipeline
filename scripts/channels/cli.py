"""CLI review-channel adapter for blog-pipeline.

The zero-setup fallback: gate messages print to stdout between clear markers,
and the human's pick is supplied inline as a sub-command argument to the next
stage. read_reply therefore always returns None -- there is no out-of-band
transport to poll. Useful before any Slack setup, and in interactive sessions
where the operator is already looking at the terminal.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from channels.base import (
    Channel,
    format_confirmation,
    format_previews,
    format_topics,
)

MARKER_BEGIN = "===== blog-pipeline: {kind} ====="
MARKER_END = "===== end {kind} ====="


def _emit(kind: str, message: str) -> None:
    print(MARKER_BEGIN.format(kind=kind))
    print(message)
    print(MARKER_END.format(kind=kind))


class CliChannel(Channel):
    def post_topics(self, run: dict, cfg: dict) -> None:
        _emit("topics", format_topics(run))

    def post_previews(self, run: dict, cfg: dict) -> None:
        _emit("previews", format_previews(run))

    def post_confirmation(self, run: dict, cfg: dict) -> None:
        _emit("confirmation", format_confirmation(run))

    def read_reply(self, run: dict, cfg: dict) -> str | None:
        """CLI gate is inline-arg only; there is never a reply to poll."""
        return None
