# claude-marketplace

Personal Claude Code plugins.

## Installation

Add the marketplace, from GitHub or a local clone:

```bash
claude plugin marketplace add nicolas-canfrere/claude-marketplace
# or
claude plugin marketplace add /path/to/claude-marketplace
```

Then install a plugin:

```bash
claude plugin install <plugin-name>@nicolas-canfrere
```

## Plugins

| Plugin | Description |
|---|---|
| [`new-tab`](plugins/new-tab) | Open a new herdr tab running a fresh Claude session seeded with a prompt |
| [`architecture-improvements`](plugins/architecture-improvements) | Find where a codebase would gain from deeper modules, then dig into one lead |
| [`retro`](plugins/retro) | Review the Claude Code sessions of a period and improve the agent's environment |

### new-tab

```
/new-tab:new-tab <prompt>
```

Opens a new [herdr](https://herdr.dev) tab in the current directory and starts an interactive `claude` session there, with `<prompt>` as its first message. Fire-and-forget: the calling session does not wait for or read the new one, and the new session does not inherit the caller's context.

Requirements: running inside herdr, `jq` on the `PATH`.

### architecture-improvements

```
/architecture-improvements:architecture-improvements [scope]
```

Reviews a codebase, or the given scope, through module depth (John Ousterhout, *A Philosophy of Software Design*): shallow modules, information leakage, rules duplicated across sibling modules. It reads the repo's own rules first (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, ADRs), targets the git hot spots when no scope is given, and reports each lead with its `file:line` evidence, in the conversation and as a standalone HTML page. It then digs into the lead you pick, through `superpowers:brainstorming` when installed. It never changes application code.

### retro

```
/retro:retro [days | YYYY-MM-DD]
```

Reads every Claude Code session of a period (7 days by default), across repos, and improves the agent's environment. A bundled script (`scripts/condense.py`, Python 3 standard library) reduces each transcript to its signals: tool errors, calls repeated after a failure, interruptions, refused permissions, probable corrections. A finding is kept only when it recurs in at least two sessions or cost a lot once. Each action goes to the strongest destination: an automatic check of the repo (described, not built), the repo's docs, the global instructions, then memory. It also proposes removing instructions that change nothing. It applies the actions you choose, never in a repo with uncommitted changes, and never commits.

Optional: set `GOTCHAS_DIR` per machine, in `~/.claude/settings.json` (`"env": { "GOTCHAS_DIR": "/path/to/gotchas" }`). The retro then reads the gotchas in `status: inbox`, and records outcomes as `status: compiled` or `status: rejected`, so that a refused proposal does not come back.

## Structure

```
.claude-plugin/
└── marketplace.json        # Marketplace manifest, lists every plugin
plugins/
└── <plugin-name>/
    ├── .claude-plugin/
    │   └── plugin.json     # Plugin metadata
    └── skills/
        └── <skill-name>/
            └── SKILL.md
```

## Adding a plugin

1. Create `plugins/<plugin-name>/` following the structure above.
2. Add an entry to `plugins` in `.claude-plugin/marketplace.json` with `"source": "./plugins/<plugin-name>"`.
3. Validate:

   ```bash
   claude plugin validate .
   claude plugin validate plugins/<plugin-name>
   ```

Plugin `name`s are install slugs: do not rename a published plugin.
