# codemap

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that builds and
incrementally maintains an **interactive architecture map + per-module code-quality
audit** for any codebase.

It decomposes a project into *functional* modules (not files), draws their dependency
graph as a layered, clickable HTML page, and scores each module 0–100 for code health —
hunting for monkeypatching, fallbacks, legacy/dead code, stubs, dual-format handling,
bloat, duplication, and glue. Every module's score comes from an **independent
subagent** against a fixed rubric. It's **incremental**: a per-module content hash means
re-runs only re-audit what changed.

## What you get

Three coupled artifacts, kept in sync:

| File | What | Where (default) |
|---|---|---|
| `config.json` | your saved **preferences** (UI language, output location, title) | `<project>/.codemap/` |
| `modules.json` | the **source of truth** (modules, deps, coupling, LoC, hash, score, findings) | `<project>/.codemap/` |
| `architecture-map.html` | self-contained **interactive map** (health coloring, filters, dependency highlighting, audit report) | `<project>/.codemap/` |
| `architecture-audit.md` | the written **report** (per-layer scores, LoC table, worst offenders, themes) | `<project>/.codemap/` |

Everything lives in **`<project>/.codemap/`** by default. On first run (`generate`) the
tool asks your preferences — UI language, output location (point it at `docs/` if you
want the HTML/MD committed/visible), project title — and saves them to
`.codemap/config.json`. The HTML and MD are **generated** from `modules.json` and must
never be hand-edited.

### Interactive map features
- Layered bands top→bottom along the data-flow; click a module to highlight what it
  **calls** (downstream) and what **depends on it** (upstream).
- Per-module **health score + grade (A–F)**, smell tags, and concrete `file:line` findings.
- Color modes: **coupling** or **health** (problems pop amber/red, healthy modules
  recede to a muted green — colorblind-friendly, the cue is saturation not just hue).
- **Filters**: by grade level (≤ B/C/D/F) and by issue tag; live match count.
- **Audit report** view: averages, grade spread, worst offenders, cross-cutting themes.
- **Standard page**: a built-in "Standard" view explaining the score→grade rubric, the
  finding severities, and every smell tag — so the scores are self-documenting.
- **i18n**: set `meta.lang` to `"en"` or `"zh"` (module names are never translated).

## Languages

Language-agnostic. The scripts count LoC and hash bytes for **any** text source, and
`paths` are plain globs, so it works for Python, **TypeScript/JS, Rust, C#/.NET, C/C++**,
Go, Java, Swift, and more. Build/test/generated trees are excluded out of the box
(`target/`, `bin/`, `obj/`, `node_modules/`, `cmake-build*`, `__pycache__/`, `dist/`,
`*.d.ts`, `*.Designer.cs`, …). The audit rubric names *behaviors*, not syntax —
`reference/STANDARDS.md` maps each smell to its per-language form (e.g. `any-escape` =
`as any` / `dynamic` / `void*` / `reinterpret_cast` / `unsafe`).

## Requirements

- **Python 3** (standard library only — no `pip install`, no external packages).
- **An AI coding agent** to drive the audit/fix/test steps — **Claude Code** (native
  skill) or **any other agent that can read instructions and spawn sub-tasks**, e.g.
  OpenAI **Codex** (see [Using with Codex / other agents](#using-with-codex--other-agents)).
- A browser to open the generated HTML. That's it.

## Install

A skill is just a folder under `~/.claude/skills/`. Clone this repo into it:

```bash
git clone <this-repo-url> ~/.claude/skills/codemap
```

(Windows PowerShell: `git clone <url> $env:USERPROFILE\.claude\skills\codemap`.)

Restart Claude Code (or start a new session). The skill appears as `/codemap`.

## Usage

Talk to Claude in natural language, or use the subcommands. Claude reads `SKILL.md`
and runs the scripts; the **audit / fix / test** steps spawn independent subagents.

| Command | Does |
|---|---|
| `/codemap generate` | first build: decompose → scan → audit every module → render |
| `/codemap check` | read-only: is the map stale? lists drifted / new / deleted modules |
| `/codemap update` | incremental: re-audit only changed modules, re-render |
| `/codemap test <module>` | generate tests (regression net) for a module |
| `/codemap fix <module>` | regression-gated fix: lock baseline → fix → independent acceptance → re-score |

You can also run the deterministic scripts directly (no AI needed for these):

```bash
S=~/.claude/skills/codemap
# what changed since last audit — incl. a `git` block listing the commits since the
# last codemap run (meta.rev) and which modules they touched
python3 $S/scripts/scan.py --root . --state .codemap/modules.json
# after an update, cache the current HEAD as the new baseline for next time
python3 $S/scripts/scan.py --root . --state .codemap/modules.json --stamp-rev
# find modules to act on without reading the whole state (token-cheap, for agents)
python3 $S/scripts/query.py --state .codemap/modules.json --max-grade C --format ids
python3 $S/scripts/query.py --state .codemap/modules.json --tag dual-format
# regenerate the HTML + MD from the state
python3 $S/scripts/render.py --state .codemap/modules.json \
  --template $S/assets/template.html \
  --out-html .codemap/architecture-map.html --out-md .codemap/architecture-audit.md
```

> On Windows use `python` instead of `python3`.

## Using with Codex / other agents

The skill mechanism is Claude-specific, but the **engine is tool-agnostic**: the four
scripts are deterministic stdlib Python, and the workflow + rubric are plain Markdown
(`SKILL.md`, `reference/STANDARDS.md`). Any capable agent can drive it.

**OpenAI Codex** auto-reads an `AGENTS.md` in the working directory — this repo ships one
that points Codex at the workflow and rubric. To use codemap from Codex (or Cursor,
Aider, etc.):

1. Make the tool available — clone this repo somewhere the agent can read it, e.g.
   `git clone <url> ~/.codemap` (or vendor it into your project).
2. Tell the agent: *"Use the codemap tool at `<path>` to build/update the architecture
   map for this project. Follow its `SKILL.md`; score each module with a separate
   sub-task using `reference/STANDARDS.md`."*
3. The agent runs the same commands shown above (`scan.py` → per-module audit →
   `apply_audit.py` → `render.py`), using `query.py` to pick targets cheaply.

The deterministic parts (scan / query / render / apply_audit) you can also run **by
hand** with no agent at all — only the *scoring*, *fixing*, and *test-writing* need a
model, and those just follow `reference/STANDARDS.md`.

## How it works

```
modules.json  ──scan.py──▶  + LoC & content hash per module (stale = hash != auditedHash)
     │                       (decomposition + descriptions are authored by the model)
     │◀─apply_audit.py──   one INDEPENDENT subagent's score per module (fixed rubric)
     │◀─query.py──────────  token-cheap targeting (by grade / tag / severity / staleness)
     └──render.py────────▶  architecture-map.html + architecture-audit.md
```

- **Four separate subagent roles, never merged**: *auditor* (scores), *test-author*
  (writes tests), *fixer* (changes code), *acceptance/verifier* (proves no regression).
  A `fix` is accepted only when an independent acceptance subagent shows the pre-fix
  green tests are still green and the build is clean.
- Tests are excluded from a module's audit scope (they're the regression net, tracked
  separately in the module's `tests` field).

## Repository layout

```
codemap/
  SKILL.md                 # the orchestration instructions Claude reads
  README.md                # this file
  reference/
    STANDARDS.md           # the scoring rubric, smell taxonomy, severity, subagent prompts
    DATA_MODEL.md          # the modules.json schema
  scripts/                 # deterministic, stdlib-only Python
    scan.py                # LoC + content hash + staleness report
    query.py               # filter modules (grade/tag/severity/...) → ids/paths/findings
    apply_audit.py         # merge one subagent's audit result into the state
    render.py              # modules.json → HTML + MD
  assets/
    template.html          # the interactive map shell (data injected at render time)
```

## Customizing the standard (capture your own "what's a problem")

The standard is **data, not code** — it lives in `reference/standard.json` (rubric,
severities, coupling, and the issue tags with descriptions). Two ways to customize:

- **In the map**: open the **Standard** page (header button), click **Edit**, change any
  description, add your own tags (`+ Tag`), then **Export** → save the downloaded
  `standard.json` to `<project>/.codemap/standard.json`. Edits are kept in the
  browser until you export. Custom tags flow through the whole map (cards, filters,
  report) and are used by future audits.
- **By file**: copy `reference/standard.json` to `<project>/.codemap/standard.json`
  and edit it. `render.py` prefers the project file over the skill default.

The prose version + the exact subagent audit prompt live in `reference/STANDARDS.md`
(keep the two in sync when changing the shipped defaults).

## "Fix this" buttons & automation

Each module's detail panel has a **Copy fix prompt** button — it copies `/codemap fix
<module>` to the clipboard for you to paste into Claude Code (or adapt for Codex). The
page intentionally does **not** auto-launch an agent: a generated static HTML has no
privileged channel to the Claude CLI/agent, and auto-launching the CLI is fragile and
increasingly restricted. Copy-to-clipboard is the robust, future-proof bridge.

## Notes

- `modules.json` is meant to be **committed** with your project — it's the audit history
  and what makes diffs/incrementality reviewable.
- The engine is **language-agnostic**: `paths` globs and LoC counting work for any stack;
  the audit subagent reads whatever code the globs point at.
