#!/usr/bin/env python3
"""apply_audit.py — validate + merge one subagent's audit result into modules.json.

A module audit is produced by an INDEPENDENT subagent (see reference/STANDARDS.md) and
returned as a small JSON object:

    {"score": 72, "grade": "C",
     "tags": ["duplication","legacy"],
     "findings": [{"sev":"HIGH","loc":"path/file.py:120","text":"..."}, ...]}

This script REJECTS bad audits before they pollute the state. It checks:
  * score in 0..100 and grade in A..F;
  * grade matches the score band (rubric: 90+ A, 75+ B, 60+ C, 40+ D, else F);
  * every tag is in the effective standard (standard.json next to the state, else the
    skill default) — including any custom tags the project added;
  * `clean` does not coexist with any other tag, and requires score >= 75;
  * a module with problem tags has at least one finding (file:line evidence);
  * every finding has a non-empty sev/loc/text.

On success it writes score/grade/tags/findings and stamps `auditedHash` = current
`contentHash` (run scan.py --write FIRST), plus `auditedAt` / `auditedRev`.

Accepts the result inline (--json '...'), from a file (--json-file path), or stdin.
Stdlib only.
"""
import argparse, datetime, json, os, sys

VALID_GRADES = {"A", "B", "C", "D", "F"}
# fallback tag set if no standard.json is found (mirrors reference/standard.json)
DEFAULT_TAGS = {"monkeypatch", "fallback", "silent-except", "legacy", "dual-format",
                "stub", "fake-output", "duplication", "bloat", "glue", "any-escape",
                "over-fit", "god-component", "placeholder", "clean"}


def grade_for(score):
    return ("A" if score >= 90 else "B" if score >= 75 else
            "C" if score >= 60 else "D" if score >= 40 else "F")


def load_standard_tags(state_path):
    """Return the set of allowed tag ids from the effective standard."""
    cands = [os.path.join(os.path.dirname(os.path.abspath(state_path)), "standard.json"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference", "standard.json")]
    for c in cands:
        if os.path.isfile(c):
            try:
                s = json.load(open(c, encoding="utf-8"))
                ids = {t["id"] for t in s.get("tags", []) if "id" in t}
                if ids:
                    return ids
            except (ValueError, OSError):
                pass
    return set(DEFAULT_TAGS)


def fail(msg):
    sys.exit("apply_audit: REJECTED — " + msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--id", required=True, help="module id to update")
    ap.add_argument("--json", help="audit result as an inline JSON string")
    ap.add_argument("--json-file", help="audit result JSON file")
    ap.add_argument("--rev", default="", help="git rev being audited (optional)")
    args = ap.parse_args()

    if args.json_file:
        result = json.load(open(args.json_file, encoding="utf-8"))
    elif args.json:
        result = json.loads(args.json)
    else:
        result = json.load(sys.stdin)

    state = json.load(open(args.state, encoding="utf-8"))
    mod = next((m for m in state.get("modules", []) if m["id"] == args.id), None)
    if mod is None:
        fail(f"module id not found: {args.id}")

    # --- score / grade ---
    try:
        score = int(result["score"])
    except (KeyError, TypeError, ValueError):
        fail("missing/invalid integer 'score'")
    if not (0 <= score <= 100):
        fail(f"score out of range 0..100: {score}")
    grade = str(result.get("grade", "")).strip().upper()[:1]
    if grade not in VALID_GRADES:
        fail(f"invalid grade: {result.get('grade')!r}")
    canonical = grade_for(score)
    if grade != canonical:
        fail(f"grade {grade} doesn't match score {score} (rubric grade is {canonical})")

    # --- tags ---
    tags = list(result.get("tags") or [])
    if any(not isinstance(t, str) for t in tags):
        fail("'tags' must be a list of strings")
    if not tags:
        tags = ["clean"]
    allowed = load_standard_tags(args.state)
    unknown = [t for t in tags if t not in allowed]
    if unknown:
        fail("tag(s) not in the standard: " + ", ".join(unknown) +
             " (define them on the Standard page / standard.json, or use a known tag)")
    nonclean = [t for t in tags if t != "clean"]
    if "clean" in tags and nonclean:
        fail("'clean' cannot coexist with problem tags: " + ", ".join(nonclean))
    if "clean" in tags and score < 75:
        fail(f"'clean' implies no material issues but score is {score} (<75) — "
             "give the real problem tags + findings instead")

    # --- findings ---
    findings = []
    for f in result.get("findings") or []:
        sev = str(f.get("sev", "")).upper()
        if sev not in {"HIGH", "MED", "LOW"}:
            fail(f"finding sev must be HIGH/MED/LOW, got {f.get('sev')!r}")
        loc, text = str(f.get("loc", "")).strip(), str(f.get("text", "")).strip()
        if not loc or not text:
            fail("every finding needs a non-empty 'loc' (file:line) and 'text'")
        findings.append({"sev": sev, "loc": loc, "text": text})
    if nonclean and not findings:
        fail("a module with problem tags must include at least one finding "
             "(cite file:line evidence) — see reference/STANDARDS.md")

    mod["score"] = score
    mod["grade"] = grade
    mod["tags"] = tags
    mod["findings"] = findings
    mod["auditedHash"] = mod.get("contentHash", "")
    mod["auditedAt"] = datetime.datetime.now().strftime("%Y-%m-%d")
    mod["auditedRev"] = args.rev

    json.dump(state, open(args.state, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"applied: {args.id}  score={score} grade={grade} "
          f"findings={len(findings)} tags={tags}")


if __name__ == "__main__":
    main()
