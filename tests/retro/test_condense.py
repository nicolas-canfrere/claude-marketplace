import contextlib
import io
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins/retro/skills/retro/scripts"))

import condense  # noqa: E402

SINCE = datetime(2026, 11, 20, tzinfo=timezone.utc)
_ids = itertools.count()


def stamp(minute=0, day=21):
    return f"2026-11-{day:02d}T10:{minute:02d}:00.000Z"


def user(text, day=21, **extra):
    return {"type": "user", "timestamp": stamp(day=day), "message": {"role": "user", "content": text}, **extra}


def assistant(text=None, tool_uses=(), day=21, **extra):
    content = [{"type": "text", "text": text}] if text else []
    content += [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input} for tool_id, name, tool_input in tool_uses]
    return {"type": "assistant", "timestamp": stamp(day=day), "message": {"role": "assistant", "content": content}, **extra}


def result(tool_id, content, is_error, day=21, **extra):
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": content, "is_error": is_error}
    return {"type": "user", "timestamp": stamp(day=day), "message": {"role": "user", "content": [block]}, **extra}


def call(name, tool_input, outcome, is_error, **extra):
    tool_id = f"toolu_{next(_ids)}"
    return [assistant(tool_uses=[(tool_id, name, tool_input)], **extra), result(tool_id, outcome, is_error, **extra)]


class ExtractSignalsTest(unittest.TestCase):
    def test_reports_a_tool_error_with_its_tool_and_input(self):
        entries = [user("lance les tests"), *call("Bash", {"command": "make tset"}, "make: *** No rule to make target", True)]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(["tool_error"], [s.kind for s in signals])
        self.assertIn("Bash", signals[0].detail)
        self.assertIn("make tset", signals[0].detail)
        self.assertIn("No rule", signals[0].detail)

    def test_reads_an_error_given_as_blocks(self):
        entries = call("Bash", {"command": "ls"}, [{"type": "text", "text": "boom"}], True)

        signals = condense.extract_signals(entries, SINCE)

        self.assertIn("boom", signals[0].detail)

    def test_reports_a_denial_instead_of_a_tool_error(self):
        entries = call("Edit", {"file_path": "a.php"}, "The user doesn't want to proceed with this tool use.", True)

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(["denial"], [s.kind for s in signals])

    def test_reports_a_repeated_call_after_a_failure(self):
        entries = [*call("Bash", {"command": "make ci"}, "failed", True), *call("Bash", {"command": "make ci"}, "ok", False)]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(["tool_error", "repeat"], [s.kind for s in signals])

    def test_does_not_report_a_repeated_call_after_a_success(self):
        entries = [*call("Bash", {"command": "make ci"}, "ok", False), *call("Bash", {"command": "make ci"}, "ok", False)]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual([], signals)

    def test_reports_an_interruption(self):
        entries = [assistant("Je lance."), user("[Request interrupted by user for tool use]")]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(["interrupt"], [s.kind for s in signals])

    def test_reports_a_correction_after_an_answer(self):
        entries = [user("ajoute un test"), assistant("Fait."), user("non, pas ça")]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(["correction"], [s.kind for s in signals])
        self.assertEqual("Fait.", signals[0].before_answer)

    def test_does_not_report_a_first_message_as_a_correction(self):
        entries = [user("non, je veux X")]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual([], signals)

    def test_ignores_entries_before_the_period(self):
        entries = call("Bash", {"command": "ls"}, "boom", True, day=19)

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual([], signals)

    def test_ignores_sidechain_entries(self):
        entries = call("Bash", {"command": "ls"}, "boom", True, isSidechain=True)

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual([], signals)

    def test_skips_a_malformed_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            path.write_text(json.dumps(user("bonjour")) + "\n" + '{"type": "us\n', encoding="utf-8")

            entries = condense.read_entries(path)

        self.assertEqual(1, len(entries))

    def test_clips_long_context(self):
        entries = [user("x" * 1000), *call("Bash", {"command": "ls"}, "boom", True)]

        signals = condense.extract_signals(entries, SINCE)

        self.assertEqual(301, len(signals[0].before_prompt))
        self.assertTrue(signals[0].before_prompt.endswith("…"))


class CondenseTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.projects = self.root / "projects"
        self.out = self.root / "out"
        self.projects.mkdir()

    def git_repo(self, name, remote=None):
        path = self.root / name
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        if remote:
            subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
        return path

    def session(self, cwd, entries, project="project", name=None, subdir=None):
        directory = self.projects / project / (subdir or "")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name or next(_ids)}.jsonl"
        path.write_text("".join(json.dumps({**entry, "cwd": str(cwd)}) + "\n" for entry in entries), encoding="utf-8")

    def run_main(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = condense.main(["--since", "2026-11-20", "--out", str(self.out), "--projects", str(self.projects)])
        self.assertEqual(0, status)
        return json.loads(output.getvalue())

    def test_writes_a_file_only_for_a_session_with_signals(self):
        repo = self.git_repo("app")
        self.session(repo, [user("bonjour"), assistant("Salut.")])
        self.session(repo, call("Bash", {"command": "ls"}, "boom", True))

        summary = self.run_main()

        self.assertEqual(2, summary["sessions"])
        self.assertEqual(1, summary["sessions_with_signals"])
        self.assertEqual(1, len(list(self.out.iterdir())))

    def test_groups_two_clones_of_the_same_remote(self):
        first = self.git_repo("app", remote="git@example.com:me/app.git")
        second = self.git_repo("app-copy", remote="git@example.com:me/app.git")
        self.session(first, call("Bash", {"command": "ls"}, "boom", True), project="a")
        self.session(second, call("Bash", {"command": "ls"}, "boom", True), project="b")

        summary = self.run_main()

        self.assertEqual(1, len(summary["repos"]))

    def test_classifies_a_missing_directory_out_of_repo(self):
        self.session(self.root / "gone", call("Bash", {"command": "ls"}, "boom", True))

        summary = self.run_main()

        self.assertEqual(["hors repo"], [repo["name"] for repo in summary["repos"]])

    def test_ignores_subagent_transcripts(self):
        repo = self.git_repo("app")
        self.session(repo, call("Bash", {"command": "ls"}, "boom", True), subdir="session/subagents", name="agent-x")

        summary = self.run_main()

        self.assertEqual(0, summary["sessions"])
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_ignores_sessions_older_than_the_period(self):
        repo = self.git_repo("app")
        self.session(repo, call("Bash", {"command": "ls"}, "boom", True, day=10))

        summary = self.run_main()

        self.assertEqual(0, summary["sessions"])

    def test_keeps_one_batch_under_the_limit(self):
        self.assertEqual([["a1", "b1"]], condense.batches({"a": [("a1", 10)], "b": [("b1", 10)]}, limit=100))

    def test_keeps_a_repo_together_when_it_fits(self):
        sizes = {"a": [("a1", 60)], "b": [("b1", 30), ("b2", 30)]}

        self.assertEqual([["a1"], ["b1", "b2"]], condense.batches(sizes, limit=100))

    def test_gives_an_oversized_file_its_own_batch(self):
        self.assertEqual([["a1"], ["a2"]], condense.batches({"a": [("a1", 250), ("a2", 10)]}, limit=100))


if __name__ == "__main__":
    unittest.main()
