---
name: codemap
description: >-
  Generate and incrementally maintain an interactive architecture map plus a
  per-module code-quality audit (health scores 0-100, smell findings, lines-of-code,
  and a clickable dependency graph) for any codebase. Use when the user wants to
  visualize a project's functional modules, audit or score code quality, check
  whether the architecture map is stale / up to date, incrementally refresh it after
  code changes, or auto-fix the findings of a specific module. Module audits are run
  by independent subagents against a fixed rubric. Triggers: "architecture map",
  "module map", "audit the codebase", "score the code", "visualize the project",
  "is the arch map current", "update the architecture diagram", "fix module X".
---

# Architecture Audit & Map

Builds and maintains three coupled artifacts for a project:

1. **`modules.json`** — the source of truth: every *functional* module (not file) with
   its paths, dependencies, coupling, LoC, content hash, score, grade, tags, findings.
2. **`architecture-map.html`** — a self-contained interactive map (layered modules,
   dependency highlighting, health coloring, audit-report view).
3. **`architecture-audit.md`** — the written report (per-layer scores, per-module LoC
   table, worst offenders, cross-cutting themes).

The HTML and MD are **always regenerated** from `modules.json` by `render.py`. Never
hand-edit them. The state file makes everything **incremental**: a content hash per
module tells us exactly what changed and what needs re-auditing.

## Standard

The scoring rubric, smell taxonomy, severity levels, and the required subagent prompt
are fixed in **`reference/STANDARDS.md`** — read it and follow it verbatim. The state
schema is in **`reference/DATA_MODEL.md`**. Do not improvise scoring or invent tags.

**The standard is configurable per project.** A machine-readable copy lives in
`reference/standard.json` (rubric, severities, coupling, and the tag list with
descriptions). A project may override it by placing its own `standard.json` next to the
state file (`<project>/.codemap/standard.json`) — `render.py` picks the project
file first, else the skill default, and injects it into the map's editable **Standard**
page. **Honor the project's tag set:** when `.codemap/standard.json` exists, audit
modules using *its* tags (including any custom tags the user added) — that is how users
capture their own definition of a problem. Keep `STANDARDS.md` (the prose + subagent
prompt) and `standard.json` (the machine copy) in sync if you change the defaults.

## Conventions

- `SKILL_DIR` = this skill's directory. Scripts are at `SKILL_DIR/scripts/*.py`,
  template at `SKILL_DIR/assets/template.html`. Use python3, stdlib only.
- **Everything lives under `<project>/.codemap/`** — one folder, not `.claude/`:
  - `config.json` — the user's saved preferences (UI language, output location, title…).
  - `modules.json` — the state (source of truth).
  - `standard.json` — optional per-project custom audit standard.
  - `architecture-map.html` + `architecture-audit.md` — the generated outputs (default).

  The output location is a user preference: if they want the HTML/MD committed/visible,
  let them point it at `docs/` instead (ask — see `generate` step 0). Set
  `meta.htmlPath` / `meta.mdPath` to wherever the outputs land so the reciprocal links
  are correct (both outputs sit in the same dir, so the in-page link uses the basename).
- A re-render command (run after any state change):
  ```
  python3 SKILL_DIR/scripts/render.py --state <state> \
    --template SKILL_DIR/assets/template.html \
    --out-html <htmlPath> --out-md <mdPath>
  ```

## Targeting modules without reading the whole state (`query.py`)

`modules.json` can be large. To decide what to audit/fix/test, DO NOT read the whole
file — use `scripts/query.py` to select exactly the modules you need and get back just
ids, file globs, or findings. This keeps agent context small.

```
# ids of every C-and-below module (feed a fix/audit loop)
python3 SKILL_DIR/scripts/query.py --state <state> --max-grade C --format ids
# modules carrying a specific problem (compact table)
python3 SKILL_DIR/scripts/query.py --state <state> --tag dual-format
# only the file globs to read for the D/F modules → read just those files
python3 SKILL_DIR/scripts/query.py --state <state> --max-grade D --format paths
# the exact findings to fix for one tag, as text
python3 SKILL_DIR/scripts/query.py --state <state> --tag glue --format findings
# what needs re-auditing
python3 SKILL_DIR/scripts/query.py --state <state> --needs-audit --format ids
```

Filters (AND-combined): `--max-grade {A..F}` (that grade and worse), `--min-score/--max-score`,
`--tag T` (repeatable; ANY, or `--match-all`), `--sev HIGH|MED|LOW`, `--band`, `--coupling`,
`--needs-audit`. Output `--format`: `ids | paths | findings | table | json | count`. Use
`--format paths` to read ONLY the relevant source, and `--format ids` to drive the
per-module subagent loop — never load the full `modules.json` just to pick targets.

## Hard rules

1. **Every module score comes from an independent subagent.** One subagent audits one
   module against its `paths`, using the prompt in `reference/STANDARDS.md`. Never score
   inline in the main thread; never copy one module's score to another. Spawn them in
   parallel (one message, multiple Agent calls — Explore or general-purpose).
2. **Scripts are deterministic; only decomposition, auditing, and theme-synthesis are
   model work.** `scan.py` / `render.py` / `apply_audit.py` never make quality judgments.
3. **`modules.json` is the only thing you edit by hand** (structure/decomposition).
   HTML/MD are generated. Run `scan.py --write` before every render so LoC/hashes are fresh.
4. **Functional modules, not files.** A module is a capability (a store, a handler
   group, a feature folder, a plugin). Map each to a glob set in `paths`. Give every
   module a 1-line `desc` ("what it does", shown on click) authored in `meta.lang`
   (set `meta.lang` to `"zh"`/`"en"`; it localizes the UI chrome — module names/ids are
   never translated).
5. **Four separate, independent subagent roles — never merge two:**
   **auditor** (scores quality), **test-author** (writes tests), **fixer** (changes
   code), **acceptance/verifier** (proves no regression). A fix is accepted ONLY when an
   independent acceptance subagent shows the pre-fix green tests are still green and the
   build/typecheck is clean. A fixer may not write/edit its own tests or grade its own
   work — that defeats the gate.

---

## Command: `generate` (first build)

Use when no `modules.json` exists yet (this is also "init").

0. **Ask the user for preferences first** (use the AskUserQuestion tool), then save them to
   `<project>/.codemap/config.json`:
   - **UI language** — `en` or `zh` (localizes the map chrome + report; module names are
     never translated). → `meta.lang`.
   - **Output location** — where the HTML/MD go. Default `.codemap/` (kept with the tool
     data); offer `docs/` if they want them committed/visible. → `meta.htmlPath` / `meta.mdPath`.
   - **Project title** (defaults to the repo/folder name) and an optional one-line subtitle,
     in the chosen language. → `meta.project` / `meta.subtitle`.

   Write `config.json` like:
   ```json
   {"lang":"zh","project":"My App","subtitle":"…","outputDir":".codemap",
    "htmlFile":"architecture-map.html","mdFile":"architecture-audit.md"}
   ```
   and apply it to `meta` when you build `modules.json`. Re-read `config.json` on later
   runs so preferences persist.
1. **Decompose the project into functional modules.** Explore the tree (parallel Explore
   agents for big repos). Identify capabilities and group them into **bands** (visual
   layers in data-flow order, e.g. UI → stores → transport → │wire│ → app → handlers →
   core → persistence → plugins). For each module record `id, label, band, path, paths
   (globs), coupling, deps, desc`. Add `bands`, `spine` (the critical request path), and
   `meta` (project, htmlPath, mdPath, spineDesc). Write this to `modules.json` (no scores
   yet). Coupling = structural centrality (low/med/high/core); core = the spine hubs.
2. **Compute size:** `python3 scripts/scan.py --root <proj> --state <state> --write`.
   It reports every module as `unaudited`.
3. **Audit — one independent subagent per module, in parallel.** For each id in
   `needs_audit`, spawn a subagent with the `reference/STANDARDS.md` prompt (filled with
   the module's label/paths). Collect each JSON result and apply it:
   `python3 scripts/apply_audit.py --state <state> --id <id> --json '<result>' [--rev <git rev>]`.
   Batch the audits (dozens of modules → many parallel agents, but stay within sane
   concurrency; chunk if needed).
4. **Synthesize `reportThemes`** (4–7 cross-cutting patterns) from the collected findings
   and write them into `modules.json`.
5. **Render:** run the render command. Then **stamp the git baseline** so future updates
   can diff from here: `python3 scripts/scan.py --root <proj> --state <state> --stamp-rev`.
   Report the result: avg score, grade spread, worst offenders, and the two artifact paths.

## Command: `check` (is the map current? — read-only)

Use when the user asks "is the architecture map up to date / still accurate?".

1. `python3 scripts/scan.py --root <proj> --state <state>` (no `--write`).
2. Read the JSON: report `up_to_date`, the **stale** list (code changed since audit),
   **unaudited** (new modules with no score), and **empty** (paths match nothing →
   likely deleted modules). The `git` block shows the **commits since the last codemap
   run** (`meta.rev`) and which modules they touched — surface those commits so the user
   sees recent history at a glance. Do **not** modify anything; offer to run `update`.
3. Also sanity-check for *new* capabilities not yet in `modules.json` (a quick look at
   new top-level dirs / large new files). New modules are model-discovered, not scan-detected.

## Command: `update` (incremental refresh, git-aware)

Use after code changes, or when `check` found drift. Re-audits only what changed, and
uses git to show recent history and scope the work.

1. **Reconcile structure first** (cheap): if modules were added/removed/renamed, edit
   `modules.json` (add new module entries with `paths`; drop `empty` ones; fix globs).
2. **Scan + git diff:** `python3 scripts/scan.py --root <proj> --state <state> --write`.
   Read the report's **`git`** block: `commits` (since `meta.rev`, the last run) and
   `changed_modules` (modules those commits touched). Show the user the recent commits —
   this is the fast "what changed" view. The audit set is `needs_audit` (= stale +
   unaudited); content-hash staleness already includes everything `changed_modules` lists
   (plus any uncommitted edits), so re-audit `needs_audit`. If `git` is null the project
   isn't a git repo — fall back to content-hash staleness only.
3. **Re-audit only those modules**, each with its own independent subagent (same protocol
   as `generate` step 3). Apply each via `apply_audit.py --id <id> --rev <head>`. Fresh
   modules keep their cached audit — that is the whole point of the content hash.
4. **Refresh `reportThemes`** if the changes are material (otherwise keep them).
5. **Render**, then **stamp the baseline**:
   `python3 scripts/scan.py --root <proj> --state <state> --stamp-rev` caches the current
   HEAD into `meta.rev`, so the next `update`/`check` diffs from here. Summarize which
   modules were re-scored and how their score moved, with the commits that caused it.

## Command: `test <module>` (generate tests)

A **test-author subagent** generates tests for a module — independently of fixing. This
is also the prerequisite for a safe `fix` (it builds the regression net). Two modes:

- **characterization** (default before a fix): lock the module's CURRENT observable
  behavior so a later change can't silently alter it. Assert "same as today", not
  "correct".
- **coverage**: add missing unit tests for the module's public surface and the behaviors
  named in its `findings`.

Steps:
1. **Detect the repo's test framework + location** (pytest / jest / vitest / go test / …)
   from existing tests near the module; match their style and placement. Do NOT invent a
   new framework or harness.
2. **One test-author subagent** writes tests against the module's `paths`, runs them, and
   iterates until green on the CURRENT (unmodified) code. It reports: files added, what
   behavior is now locked, and a coverage note. If a test only passes by asserting a known
   bug, it must FLAG the bug, not bake it in as desired behavior.
3. **Tests are real source** — they stay in the tree (they are the regression net). Record
   their globs in the module's `tests` field in `modules.json`. Re-run `scan.py --write`
   and `render.py` (test LoC is tracked but excluded from the module's own audit scope).

Keep test-author distinct from fixer and auditor.

## Command: `fix <module-or-finding>` (auto-fix, regression-gated)

Use when the user says "fix the findings in module X" / "auto-fix the worst offenders".
A fix is **only accepted if an independent acceptance subagent proves no regression.**
Four separate subagents (hard rule 5): test-author → fixer → acceptance → auditor.

1. **Scope (via `query.py`).** Resolve the target set with `query.py` instead of reading
   the whole state — e.g. `--max-grade C --tag dual-format --format ids` for "all C-and-
   below dual-format modules", then `--format findings` for just the findings to fix and
   `--format paths` for just the files to read. Confirm with the user before risky fixes
   (duplication merges, dual-format removal touching a protocol, deleting "dead" code —
   first verify it is truly unused).
2. **Baseline (test-author subagent).** Ensure the module has tests that lock its CURRENT
   behavior; if coverage is thin, run `test <module>` (characterization mode) first. Run
   the module's tests + the narrowest build/typecheck on the UNMODIFIED code and record
   the **green baseline** (which tests pass, build/type status, key outputs). If you can't
   get a green baseline, STOP and tell the user — auto-fixing without a behavioral net is
   not safe.
3. **Fix (fixer subagent, `isolation: "worktree"`).** Give it the module's paths, findings,
   and `reference/STANDARDS.md` rules; implement the fix and preserve behavior. The fixer
   **must not edit tests** (no moving the goalposts) and must not touch files outside its
   paths without flagging.
4. **Acceptance gate (independent verifier subagent — NOT the fixer).** Re-run the SAME
   baseline tests + build/typecheck on the fixed code. Return
   `{pass: bool, regressions: [...], evidence: "..."}`. **PASS only if every
   baseline-green test is still green and there are no new build/type errors.** On FAIL:
   report the regression with evidence and revert / hand back to the fixer — do not accept.
5. **Re-audit (auditor subagent, independent).** Only after PASS: re-score the module →
   `scan.py --write` → `apply_audit.py` → render. Show **before/after score AND the
   acceptance evidence** (tests run, all green, build clean).
6. **Never auto-commit unless asked.** Report honestly — a fix that fails the gate is
   reported as failed, not merged. Record the outcome in the module's `lastFix` field.

---

## Notes

- **Coupling vs score are independent** (structural vs quality) — see DATA_MODEL.md. The
  map can color by either (toggle in the header).
- **Big repos:** parallelize decomposition (Explore) and auditing (one agent per module).
  Chunk audits if there are many dozens of modules.
- **Determinism:** same `modules.json` → identical HTML/MD. Commit `modules.json` so the
  audit history and incremental diffs are reviewable.
- **Languages:** the engine is language-agnostic — `paths` globs and LoC counting work
  for any stack; the subagent reads whatever code the globs point at.
