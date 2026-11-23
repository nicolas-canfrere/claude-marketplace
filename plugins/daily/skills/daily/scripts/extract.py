#!/usr/bin/env python3
"""Extract a compact digest of one day's Claude Code sessions.

Usage: extract.py [YYYY-MM-DD]   (defaults to today, local time)

Reads ~/.claude/projects/*/*.jsonl (subagent transcripts excluded) and keeps,
for each session active that day: project, branch, title, PR links, and each
user prompt with the last assistant text that answered it.
"""
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
PROMPT_MAX = 500
ANSWER_MAX = 800


def day_bounds(day):
    start = datetime.combine(day, time.min).astimezone()
    end = datetime.combine(day, time.max).astimezone()
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parse_ts(raw):
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
    return ""


def is_human_prompt(entry):
    if entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, list) and any(b.get("type") == "tool_result" for b in content):
        return False
    text = text_of(content).strip()
    return bool(text) and not text.startswith(("<local-command", "<system-reminder", "<task-notification"))


def clip(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def digest(path, start, end):
    title, launch_dir, cwd, branch, prs, turns = None, None, None, None, {}, []
    for line in path.open(encoding="utf-8"):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = entry.get("type")
        launch_dir = launch_dir or entry.get("cwd")
        if kind == "ai-title":
            title = entry.get("aiTitle")
        if kind == "pr-link":
            prs[entry["prUrl"]] = None
        if kind not in ("user", "assistant") or "timestamp" not in entry:
            continue
        if not start <= parse_ts(entry["timestamp"]) <= end:
            continue
        cwd = entry.get("cwd") or cwd
        branch = entry.get("gitBranch") or branch
        if kind == "user" and is_human_prompt(entry):
            local = parse_ts(entry["timestamp"]).astimezone().strftime("%H:%M")
            turns.append({"time": local, "prompt": clip(text_of(entry["message"]["content"]), PROMPT_MAX), "answer": ""})
        elif kind == "assistant" and turns and not entry.get("isSidechain"):
            answer = text_of(entry.get("message", {}).get("content")).strip()
            if answer:
                turns[-1]["answer"] = clip(answer, ANSWER_MAX)
    if not turns:
        return None
    return {"session": path.stem, "launch_dir": launch_dir, "cwd": cwd, "branch": branch, "title": title, "prs": list(prs), "turns": turns}


def main():
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    start, end = day_bounds(day)
    sessions = []
    for path in PROJECTS.glob("*/*.jsonl"):
        if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < start:
            continue
        session = digest(path, start, end)
        if session:
            sessions.append(session)
    sessions.sort(key=lambda s: s["turns"][0]["time"])
    json.dump({"date": day.isoformat(), "sessions": sessions}, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
