"""Per-run state machine for blog-pipeline.

One JSON file per run date at <repo>/.blog-pipeline/runs/YYYY-MM-DD.json.
Every stage is idempotent: it loads the run, checks the status, and resumes.
Illegal transitions raise, so a stage can never silently skip a human gate.

Also home to parse_picks(), the single parser both gate paths (inline arg and
fetched channel reply) feed into -- so manual and poll behave identically.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from config import runs_dir

# --- States (canonical order) ---

RESEARCHING = "researching"
AWAITING_TOPIC_APPROVAL = "awaiting_topic_approval"
DRAFTING = "drafting"
AWAITING_CONTENT_APPROVAL = "awaiting_content_approval"
DEPLOYING = "deploying"
PUBLISHED = "published"

STATES = (
    RESEARCHING,
    AWAITING_TOPIC_APPROVAL,
    DRAFTING,
    AWAITING_CONTENT_APPROVAL,
    DEPLOYING,
    PUBLISHED,
)

# Legal transitions. published is terminal. A no-op day (nothing new found)
# jumps researching -> published directly.
TRANSITIONS = {
    RESEARCHING: (AWAITING_TOPIC_APPROVAL, PUBLISHED),
    AWAITING_TOPIC_APPROVAL: (DRAFTING,),
    DRAFTING: (AWAITING_CONTENT_APPROVAL,),
    AWAITING_CONTENT_APPROVAL: (DEPLOYING,),
    DEPLOYING: (PUBLISHED,),
    PUBLISHED: (),
}


class RunStateError(Exception):
    pass


def run_path(repo_path: str | Path, date: str) -> Path:
    # A run id is a date, optionally suffixed with a content type so parallel
    # pipelines (blogs, templates) each get one run per day: "2026-07-18",
    # "2026-07-18-templates".
    if not re.match(r"^\d{4}-\d{2}-\d{2}(-[a-z][a-z0-9-]*)?$", date):
        raise RunStateError(f"run id must be YYYY-MM-DD[-type], got {date!r}")
    return runs_dir(repo_path) / f"{date}.json"


def load_run(repo_path: str | Path, date: str) -> dict | None:
    path = run_path(repo_path, date)
    if not path.exists():
        return None
    run = json.loads(path.read_text())
    if run.get("status") not in STATES:
        raise RunStateError(f"{path}: unknown status {run.get('status')!r}")
    # Headless research agents write minimal run files; fill optional keys so
    # every reader can rely on the full shape.
    for key, default in (("topics", []), ("selected", []), ("drafted", []),
                         ("deploy", {}), ("history", [])):
        run.setdefault(key, default)
    return run


def save_run(repo_path: str | Path, run: dict) -> Path:
    path = run_path(repo_path, run["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    return path


def create_run(repo_path: str | Path, date: str) -> dict:
    """Start a run for the date. Idempotent: returns the existing run if any."""
    existing = load_run(repo_path, date)
    if existing is not None:
        return existing
    run = {
        "date": date,
        "status": RESEARCHING,
        "topics": [],       # [{title, persona, angle, keyword, rationale}]
        "selected": [],     # indices into topics (0-based) after topic approval
        "drafted": [],      # [{slug, file, previewUrl}]
        "deploy": {},       # {branch, commit, prodUrls: []}
        "history": [],      # [{status, at}] appended by advance()
    }
    save_run(repo_path, run)
    return run


def advance(run: dict, new_status: str, at: str | None = None) -> dict:
    """Move the run to new_status, enforcing the state machine."""
    current = run["status"]
    if new_status == current:
        return run  # idempotent re-entry
    allowed = TRANSITIONS.get(current, ())
    if new_status not in allowed:
        raise RunStateError(
            f"illegal transition {current} -> {new_status} (allowed: {list(allowed)})"
        )
    run["status"] = new_status
    entry = {"status": new_status}
    if at:
        entry["at"] = at
    run["history"].append(entry)
    return run


# --- Pick parsing (shared by both gate paths) ---

def parse_picks(text: str, items: list, cap: int) -> tuple[list, list]:
    """Parse a human's selection reply against the posted items.

    Accepts: "all" | 1-based indices ("1,3,5" / "1 3 5") | slugs/titles.
    Returns (indices, problems): 0-based indices capped at `cap`, and a list
    of tokens that matched nothing (never silently dropped).
    """
    problems: list = []
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return [], ["empty selection"]
    if cleaned == "all":
        return list(range(min(len(items), cap))), []

    tokens = [t for t in re.split(r"[\s,]+", cleaned) if t]
    indices: list = []
    for tok in tokens:
        if tok.isdigit():
            i = int(tok) - 1
            if 0 <= i < len(items):
                indices.append(i)
            else:
                problems.append(f"index out of range: {tok}")
            continue
        # slug or title fragment match
        matches = [
            i for i, item in enumerate(items)
            if tok == str(item.get("slug", "")).lower()
            or tok in str(item.get("title", "")).lower()
        ]
        if len(matches) == 1:
            indices.append(matches[0])
        elif not matches:
            problems.append(f"no item matches: {tok}")
        else:
            problems.append(f"ambiguous (matches {len(matches)} items): {tok}")

    deduped = list(dict.fromkeys(indices))
    if len(deduped) > cap:
        problems.append(f"selection capped at {cap} (asked for {len(deduped)})")
        deduped = deduped[:cap]
    return deduped, problems


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print("usage: runstate.py <target-repo-path> <YYYY-MM-DD>   # show run status")
        return 2
    run = load_run(argv[1], argv[2])
    if run is None:
        print(f"no run for {argv[2]}")
        return 1
    print(f"date: {run['date']}  status: {run['status']}")
    print(f"topics: {len(run['topics'])}  selected: {run['selected']}  drafted: {len(run['drafted'])}")
    for h in run["history"]:
        print(f"  -> {h['status']}" + (f" at {h['at']}" if "at" in h else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
