#!/usr/bin/env python3
"""Condense Claude Code session transcripts into their signals, for a retrospective.

A signal is what tells that a session went wrong somewhere: a tool error, a call repeated after a failure, an
interruption, a permission refused by the user, a message that probably corrects the agent. Each one comes with the
turn before it, so that it can be understood without the whole transcript.
"""
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path

CLIP = 300
INPUT_CLIP = 200
CORRECTION_MARKERS = (
    "non,", "non ", "pas ça", "c'est faux", "tu te trompes", "je t'ai dit", "j'ai dit", "arrête", "stop",
    "annule", "reviens", "remets", "revert", "au lieu de", "pourquoi tu", "ne fais pas", "n'ajoute pas",
    "no,", "wrong", "don't", "undo", "that's not",
)
NOT_HUMAN_PREFIXES = ("<system-reminder", "<local-command", "<task-notification", "<command-name>")
INTERRUPT_PREFIX = "[Request interrupted by user"
DENIAL_TEXT = "The user doesn't want to proceed"
LIMIT = 150000
OUT_OF_REPO = ("hors repo", "hors repo")


@dataclass
class Signal:
    kind: str
    time: str
    detail: str
    before_prompt: str
    before_answer: str


def read_entries(path: Path) -> list[dict]:
    entries = []
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                # A session still being written ends with a partial line.
                continue
    return entries


def clip(text: str, limit: int = CLIP) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def parse_time(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
    return ""


def blocks(entry: dict, kind: str) -> list[dict]:
    content = entry.get("message", {}).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == kind]


def human_text(entry: dict) -> str | None:
    if entry.get("type") != "user" or entry.get("isMeta") or blocks(entry, "tool_result"):
        return None
    text = text_of(entry.get("message", {}).get("content")).strip()
    if not text or text.startswith(NOT_HUMAN_PREFIXES):
        return None
    return text


def is_correction(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CORRECTION_MARKERS)


def extract_signals(entries: list[dict], since: datetime) -> list[Signal]:
    signals: list[Signal] = []
    calls: dict[str, tuple[str, dict]] = {}
    failed_calls: set[tuple[str, str]] = set()
    last_prompt, last_answer, answered = "", "", False

    for entry in entries:
        if entry.get("isSidechain") or entry.get("type") not in ("user", "assistant") or "timestamp" not in entry:
            continue
        moment = parse_time(entry["timestamp"])
        in_period = moment >= since
        hour = moment.astimezone().strftime("%H:%M")

        def emit(kind: str, detail: str) -> None:
            if in_period:
                signals.append(Signal(kind, hour, detail, clip(last_prompt), clip(last_answer)))

        if entry["type"] == "assistant":
            for use in blocks(entry, "tool_use"):
                name, tool_input = use.get("name", "?"), use.get("input", {})
                calls[use.get("id", "")] = (name, tool_input)
                if (name, json.dumps(tool_input, sort_keys=True)) in failed_calls:
                    emit("repeat", f"{name} {clip(json.dumps(tool_input, ensure_ascii=False), INPUT_CLIP)}")
            text = text_of(entry.get("message", {}).get("content")).strip()
            if text:
                last_answer, answered = text, True
            continue

        for outcome in blocks(entry, "tool_result"):
            if not outcome.get("is_error"):
                continue
            error = text_of(outcome.get("content"))
            name, tool_input = calls.get(outcome.get("tool_use_id", ""), ("?", {}))
            failed_calls.add((name, json.dumps(tool_input, sort_keys=True)))
            if DENIAL_TEXT in error:
                emit("denial", f"{name} {clip(json.dumps(tool_input, ensure_ascii=False), INPUT_CLIP)}")
            else:
                emit("tool_error", f"{name} {clip(json.dumps(tool_input, ensure_ascii=False), INPUT_CLIP)} → {clip(error)}")

        text = human_text(entry)
        if text is None:
            continue
        if text.startswith(INTERRUPT_PREFIX):
            emit("interrupt", clip(text))
        elif answered and is_correction(text):
            emit("correction", clip(text))
        last_prompt = text

    return signals


def git(*args: str) -> str | None:
    completed = subprocess.run(["git", *args], capture_output=True, text=True)
    return completed.stdout.strip() if completed.returncode == 0 and completed.stdout.strip() else None


@lru_cache(maxsize=None)
def repo_of(cwd: str | None) -> tuple[str, str]:
    """(key, display name) of the git repo a session ran in; two clones of the same remote are one repo."""
    if not cwd or not Path(cwd).is_dir():
        return OUT_OF_REPO
    root = git("-C", cwd, "rev-parse", "--show-toplevel")
    if root is None:
        return OUT_OF_REPO
    return git("-C", root, "remote", "get-url", "origin") or root, root


def batches(sizes: dict[str, list[tuple[str, int]]], limit: int = LIMIT) -> list[list[str]]:
    """Reading batches of at most `limit` characters; a repo that fits stays whole, a file is never cut."""
    result: list[list[str]] = []
    current: list[str] = []
    used = 0

    def close() -> None:
        nonlocal current, used
        if current:
            result.append(current)
        current, used = [], 0

    for files in sizes.values():
        if used + sum(size for _, size in files) > limit:
            close()
        for name, size in files:
            if used + size > limit:
                close()
            current.append(name)
            used += size
    close()
    return result


def in_period(entry: dict, since: datetime) -> bool:
    return (
        entry.get("type") in ("user", "assistant")
        and not entry.get("isSidechain")
        and "timestamp" in entry
        and parse_time(entry["timestamp"]) >= since
    )


def render(session_id: str, repo: str, entries: list[dict], period: list[dict], signals: list[Signal]) -> str:
    branch = next((entry["gitBranch"] for entry in reversed(period) if entry.get("gitBranch")), "-")
    title = next((entry["aiTitle"] for entry in reversed(entries) if entry.get("type") == "ai-title"), "-")
    first = parse_time(period[0]["timestamp"]).astimezone()
    last = parse_time(period[-1]["timestamp"]).astimezone()
    turns = sum(1 for entry in period if human_text(entry) is not None)
    lines = [
        f"session {session_id} · {repo} · {branch} · {title}",
        f"{first:%Y-%m-%d %H:%M} → {last:%H:%M} · {turns} tours",
        "",
    ]
    for signal in signals:
        lines += [
            f"[{signal.time}] {signal.kind}: {signal.detail}",
            f"  avant · humain: {signal.before_prompt}",
            f"  avant · claude: {signal.before_answer}",
        ]
    return "\n".join(lines) + "\n"


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", Path(text).name).strip("-") or "session"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, type=date.fromisoformat, help="first day of the period, YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path, help="directory for the condensed sessions")
    parser.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--limit", type=int, default=LIMIT)
    args = parser.parse_args(argv)
    since = datetime.combine(args.since, time.min).astimezone()
    args.out.mkdir(parents=True, exist_ok=True)

    repos: dict[str, dict] = {}
    sessions = with_signals = 0
    # One level only: subagent transcripts live in <session>/subagents/ and are left out.
    for path in sorted(args.projects.glob("*/*.jsonl")):
        if datetime.fromtimestamp(path.stat().st_mtime).astimezone() < since:
            continue
        entries = read_entries(path)
        period = [entry for entry in entries if in_period(entry, since)]
        if not period:
            continue
        sessions += 1
        key, name = repo_of(next((entry["cwd"] for entry in period if entry.get("cwd")), None))
        repo = repos.setdefault(key, {"key": key, "name": name, "sessions": 0, "files": [], "chars": 0})
        repo["sessions"] += 1
        signals = extract_signals(entries, since)
        if not signals:
            continue
        with_signals += 1
        text = render(path.stem, name, entries, period, signals)
        target = args.out / f"{slug(name)}--{path.stem}.txt"
        target.write_text(text, encoding="utf-8")
        repo["files"].append((str(target), len(text)))
        repo["chars"] += len(text)

    ordered = sorted(repos.values(), key=lambda repo: repo["name"])
    summary = {
        "since": args.since.isoformat(),
        "limit": args.limit,
        "sessions": sessions,
        "sessions_with_signals": with_signals,
        "total_chars": sum(repo["chars"] for repo in ordered),
        "repos": [{**repo, "files": [name for name, _ in repo["files"]]} for repo in ordered],
        "batches": batches({repo["key"]: repo["files"] for repo in ordered if repo["files"]}, args.limit),
    }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
