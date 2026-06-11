#!/usr/bin/env python3
"""apply_audit.py — merge one subagent's audit result into modules.json.

A module audit is produced by an INDEPENDENT subagent (see reference/STANDARDS.md)
and returned as a small JSON object:

    {"score": 72, "grade": "C",
     "tags": ["duplication","legacy"],
     "findings": [{"sev":"HIGH","loc":"path/file.py:120","text":"..."}, ...]}

This script writes that result onto the module and stamps `auditedHash` =
current `contentHash` (so scan.py will treat the module as fresh until its code
changes again), plus `auditedAt` / `auditedRev`. Run scan.py --write FIRST so the
current contentHash is present.

Accepts the result inline (--json '...') or from a file (--json-file path).
Stdlib only.
"""
import argparse, datetime, json, sys

VALID_GRADES = {"A", "B", "C", "D", "F"}


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
        sys.exit(f"module id not found: {args.id}")

    score = int(result["score"])
    grade = str(result["grade"]).strip().upper()[:1]
    if grade not in VALID_GRADES:
        sys.exit(f"invalid grade: {result['grade']}")
    if not (0 <= score <= 100):
        sys.exit(f"score out of range: {score}")

    findings = []
    for f in result.get("findings", []):
        sev = str(f.get("sev", "LOW")).upper()
        if sev not in {"HIGH", "MED", "LOW"}:
            sev = "LOW"
        findings.append({"sev": sev, "loc": str(f.get("loc", "")),
                         "text": str(f.get("text", ""))})

    mod["score"] = score
    mod["grade"] = grade
    mod["tags"] = list(result.get("tags", [])) or ["clean"]
    mod["findings"] = findings
    mod["auditedHash"] = mod.get("contentHash", "")
    mod["auditedAt"] = datetime.datetime.now().strftime("%Y-%m-%d")
    mod["auditedRev"] = args.rev

    json.dump(state, open(args.state, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"applied: {args.id}  score={score} grade={grade} "
          f"findings={len(findings)} tags={mod['tags']}")


if __name__ == "__main__":
    main()
