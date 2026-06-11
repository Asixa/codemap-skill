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

## Conventions

- `SKILL_DIR` = this skill's directory. Scripts are at `SKILL_DIR/scripts/*.py`,
  template at `SKILL_DIR/assets/template.html`. Use python3, stdlib only.
- Default artifact locations (override if the user/project prefers): state (the data)
  at `<project>/.claude/codemap/modules.json`; the generated outputs at
  `<project>/dev_docs/architecture-map.html` and `dev_docs/architecture-audit.md`. The
  state lives under `.claude/` (tooling data, kept out of the docs tree); only the two
  human-facing artifacts go in `dev_docs/`. Set `meta.htmlPath` / `meta.mdPath` so the
  reciprocal links are correct.
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

Use when no `modules.json` exists yet.

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
5. **Render:** run the render command. Report the result: avg score, grade spread, worst
   offenders, and the two artifact paths.

## Command: `check` (is the map current? — read-only)

Use when the user asks "is the architecture map up to date / still accurate?".

1. `python3 scripts/scan.py --root <proj> --state <state>` (no `--write`).
2. Read the JSON: report `up_to_date`, the **stale** list (code changed since audit),
   **unaudited** (new modules with no score), and **empty** (paths match nothing →
   likely deleted modules). Do **not** modify anything. Tell the user exactly which
   modules drifted and offer to run `update`.
3. Also sanity-check for *new* capabilities not yet in `modules.json` (a quick look at
   new top-level dirs / large new files). New modules are model-discovered, not scan-detected.

## Command: `update` (incremental refresh)

Use after code changes, or when `check` found drift. Only re-audits what changed.

1. **Reconcile structure first** (cheap): if modules were added/removed/renamed, edit
   `modules.json` (add new module entries with `paths`; drop `empty` ones; fix globs).
2. `python3 scripts/scan.py --root <proj> --state <state> --write` → get `needs_audit`
   (= stale + unaudited).
3. **Re-audit only those modules**, each with its own independent subagent (same
   protocol as `generate` step 3). Apply each via `apply_audit.py`. Fresh modules keep
   their cached audit untouched — that is the whole point of the content hash.
4. **Refresh `reportThemes`** if the changes are material (otherwise keep them).
5. **Render.** Summarize what changed: which modules were re-scored and how their score moved.

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
