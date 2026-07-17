"""Scheduler installer for blog-pipeline.

Installs the daily research trigger described by config (cfg["cron"] +
cfg["scheduler"]). Three mechanisms:

- crontab       -- managed line in the user's crontab, tagged with a marker
                   comment so install is idempotent and uninstall is surgical.
- launchd       -- writes a LaunchAgent plist; prints the `launchctl load`
                   command rather than running it (loading is an operator act).
- schedule-skill-- installs nothing; prints instructions for the Claude Code
                   /schedule skill.

Line building is a pure function (build_cron_line) so tests never touch a
real crontab. Only install()/uninstall() shell out.

CLI:
    python3 install_cron.py <target-repo-path> [--uninstall] [--dry-run]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from config import ConfigError, load_config

DEFAULT_COMMAND = 'claude -p "Run the blog-pipeline research stage for this repo"'
MARKER_PREFIX = "# blog-pipeline:"
LAUNCHD_LABEL_PREFIX = "ai.ujjwalks.blog-pipeline"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"

# Only the simple "M H * * *" (daily at H:M) form maps onto StartCalendarInterval.
DAILY_CRON_RE = re.compile(r"^\s*(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*\s*$")

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>cd {repo_path} &amp;&amp; {command}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
</dict>
</plist>
"""


def _marker(repo_path: str) -> str:
    return f"{MARKER_PREFIX}{repo_path}"


def build_cron_line(cfg: dict, repo_path: str, command: str | None = None) -> str:
    """Pure: the exact crontab line for this repo. Testable without subprocess."""
    cron = cfg.get("cron")
    if not cron:
        raise ConfigError(["cron: required to install a schedule (e.g. '0 12 * * *')"])
    cmd = command or DEFAULT_COMMAND
    return f"{cron} cd {repo_path} && {cmd} {_marker(repo_path)}"


def _launchd_slug(repo_path: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", Path(repo_path).name.lower()).strip("-") or "site"


def parse_daily_cron(cron: str) -> tuple[int, int]:
    """Parse a "M H * * *" cron into (hour, minute); raise on anything else."""
    m = DAILY_CRON_RE.match(cron or "")
    if not m:
        raise ConfigError(
            [f"cron: launchd scheduler supports only daily 'M H * * *' schedules, got {cron!r}"]
        )
    minute, hour = int(m.group(1)), int(m.group(2))
    if minute > 59 or hour > 23:
        raise ConfigError([f"cron: minute/hour out of range in {cron!r}"])
    return hour, minute


def _read_crontab() -> list[str]:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []  # no crontab yet
    return result.stdout.splitlines()


def _write_crontab(lines: list[str]) -> None:
    content = "\n".join(lines) + ("\n" if lines else "")
    result = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    if result.returncode != 0:
        raise ConfigError([f"crontab write failed: {result.stderr.strip()}"])


def install(cfg: dict, repo_path: str, command: str | None = None, dry_run: bool = False) -> str:
    """Install the schedule for cfg["scheduler"]. Returns a human summary."""
    scheduler = cfg.get("scheduler", "crontab")

    if scheduler == "crontab":
        line = build_cron_line(cfg, repo_path, command)
        if dry_run:
            return f"[dry-run] would install crontab line:\n{line}"
        marker = _marker(repo_path)
        lines = [l for l in _read_crontab() if marker not in l]
        lines.append(line)
        _write_crontab(lines)
        return f"installed crontab line:\n{line}"

    if scheduler == "launchd":
        hour, minute = parse_daily_cron(cfg.get("cron"))
        label = f"{LAUNCHD_LABEL_PREFIX}.{_launchd_slug(repo_path)}"
        plist_path = LAUNCH_AGENTS_DIR / f"{label}.plist"
        content = PLIST_TEMPLATE.format(
            label=label,
            repo_path=repo_path,
            command=(command or DEFAULT_COMMAND).replace("&", "&amp;"),
            hour=hour,
            minute=minute,
        )
        if dry_run:
            return f"[dry-run] would write {plist_path} (daily {hour:02d}:{minute:02d})"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(content)
        return (
            f"wrote {plist_path}\n"
            f"load it with:\n  launchctl load {plist_path}"
        )

    if scheduler == "schedule-skill":
        return (
            "scheduler is 'schedule-skill' -- nothing installed locally.\n"
            "In Claude Code, run the /schedule skill with:\n"
            f"  cron:   {cfg.get('cron')}\n"
            f"  prompt: Run the blog-pipeline research stage for {repo_path}"
        )

    raise ConfigError([f"scheduler: unknown value {scheduler!r}"])


def uninstall(repo_path: str, dry_run: bool = False) -> str:
    """Remove this repo's marker line from the crontab."""
    marker = _marker(repo_path)
    lines = _read_crontab()
    kept = [l for l in lines if marker not in l]
    removed = len(lines) - len(kept)
    if dry_run:
        return f"[dry-run] would remove {removed} crontab line(s) with marker {marker}"
    if removed:
        _write_crontab(kept)
    return f"removed {removed} crontab line(s) with marker {marker}"


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    unknown = flags - {"--uninstall", "--dry-run"}
    if len(args) != 1 or unknown or "-h" in argv or "--help" in flags:
        print("usage: install_cron.py <target-repo-path> [--uninstall] [--dry-run]")
        return 2
    repo = args[0]
    dry_run = "--dry-run" in flags
    try:
        if "--uninstall" in flags:
            print(uninstall(repo, dry_run=dry_run))
        else:
            print(install(load_config(repo), repo, dry_run=dry_run))
        return 0
    except ConfigError as exc:
        print(f"error:\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
