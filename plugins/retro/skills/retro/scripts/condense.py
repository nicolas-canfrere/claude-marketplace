#!/usr/bin/env python3
"""Condense Claude Code session transcripts into their signals, for a retrospective.

A signal is what tells that a session went wrong somewhere: a tool error, a call repeated after a failure, an
interruption, a permission refused by the user, a message that probably corrects the agent. Each one comes with the
turn before it, so that it can be understood without the whole transcript.
"""
import json
from dataclasses import dataclass
from datetime import datetime
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
        time = moment.astimezone().strftime("%H:%M")

        def emit(kind: str, detail: str) -> None:
            if in_period:
                signals.append(Signal(kind, time, detail, clip(last_prompt), clip(last_answer)))

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
