---
name: new-tab
description: Open a new herdr tab with a fresh, independent Claude session that receives the given text as its first prompt. Fire-and-forget; the current session does not wait.
argument-hint: <prompt>
disable-model-invocation: true
---

# New tab

Launch a separate Claude session in a new herdr tab, seeded with this prompt:

<prompt>
$ARGUMENTS
</prompt>

This is fire-and-forget: do not wait for, read, or monitor the new session.

## Steps

1. If the prompt is empty, stop and ask for one.
2. Create a temp file: `mktemp --suffix=.md` (Bash). Note its path.
3. Write the prompt, verbatim, to that file with the Write tool. Never inline it into a shell command.
4. Pick a short label (2-4 words, kebab-case) summarising the prompt.
5. Run, substituting `<label>` and `<file>`:

   ```bash
   pane=$(herdr tab create --cwd "$PWD" --label "<label>" --no-focus | jq -r .result.root_pane.pane_id) \
     && herdr pane run "$pane" 'claude "$(cat <file>; rm -f <file>)"' \
     && echo "$pane"
   ```

   The single quotes matter: `$(cat …)` must be expanded by the new tab's shell, not this one.
6. Reply with one line: the tab label and pane id. Nothing else.
