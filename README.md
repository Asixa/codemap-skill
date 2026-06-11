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
| `modules.json` | the **source of truth** (modules, deps, coupling, LoC, hash, score, findings) | `<project>/.claude/codemap/` |
| `architecture-map.html` | self-contained **interactive map** (health coloring, filters, dependency highlighting, audit report) | `<project>/docs/` |
| `architecture-audit.md` | the written **report** (per-layer scores, LoC table, worst offenders, themes) | `<project>/docs/` |

The HTML and MD are **generated** from `modules.json` and must never be hand-edited.

### Interactive map features
- Layered bands top→bottom along the data-flow; click a module to highlight what it
  **calls** (downstream) and what **depends on it** (upstream).
- Per-module **health score + grade (A–F)**, smell tags, and concrete `file:line` findings.
- Color modes: **coupling** or **health** (problems pop amber/red, healthy modules
  recede to a muted green — colorblind-friendly, the cue is saturation not just hue).
- **Filters**: by grade level (≤ B/C/D/F) and by issue tag; live match count.
- **Audit report** view: averages, grade spread, worst offenders, cross-cutting themes.
- **i18n**: set `meta.lang` to `"en"` or `"zh"` (module names are never translated).

## Requirements

- **Python 3** (standard library only — no `pip install`, no external packages).
- **Claude Code** (the skill orchestrates subagents for the audit/fix/test steps).
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
# what changed since last audit
python3 $S/scripts/scan.py --root . --state .claude/codemap/modules.json
# find modules to act on without reading the whole state (token-cheap, for agents)
python3 $S/scripts/query.py --state .claude/codemap/modules.json --max-grade C --format ids
python3 $S/scripts/query.py --state .claude/codemap/modules.json --tag dual-format
# regenerate the HTML + MD from the state
python3 $S/scripts/render.py --state .claude/codemap/modules.json \
  --template $S/assets/template.html \
  --out-html docs/architecture-map.html --out-md docs/architecture-audit.md
```

> On Windows use `python` instead of `python3`.

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

## Customizing the standard

The rubric, smell taxonomy (tags), severity levels, and the exact subagent prompts live
in `reference/STANDARDS.md` — edit there and every future audit uses the new standard.
Add a tag? Also add it to the `BAD_TAGS` set (and `TAGS_ZH` for a label) in
`assets/template.html` so the map colors and counts it.

## Notes

- `modules.json` is meant to be **committed** with your project — it's the audit history
  and what makes diffs/incrementality reviewable.
- The engine is **language-agnostic**: `paths` globs and LoC counting work for any stack;
  the audit subagent reads whatever code the globs point at.
