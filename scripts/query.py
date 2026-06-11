#!/usr/bin/env python3
"""query.py — token-cheap module selector over modules.json.

An agent uses this to find exactly the modules it must act on WITHOUT reading the
whole state file. Filter by grade/score level, by smell tag, by finding severity,
by band/coupling, or by staleness; emit just ids, paths, a compact table, the
findings, or filtered JSON.

Examples:
  # all C-and-below modules → just their ids (pipe into a fix loop)
  python query.py --state s.json --max-grade C --format ids
  # modules with a dual-format problem, worst first, as a table
  python query.py --state s.json --tag dual-format
  # the file globs to read for every module that has a HIGH finding
  python query.py --state s.json --sev HIGH --format paths
  # the actual findings to fix for one tag, as text
  python query.py --state s.json --tag glue --format findings
  # what needs re-auditing (stale or never scored)
  python query.py --state s.json --needs-audit --format ids

Filters combine with AND. --tag may be repeated (ANY by default, --match-all for AND).
Stdlib only.
"""
import argparse, json, sys

# include a module if its score is strictly below this bound (grade and worse).
GRADE_BOUND = {"A": 101, "B": 90, "C": 75, "D": 60, "F": 40}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # findings/descriptions may be non-ASCII
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="filter modules.json for agents")
    ap.add_argument("--state", required=True)
    ap.add_argument("--max-grade", choices=list(GRADE_BOUND),
                    help="include this grade AND worse (e.g. C → C,D,F)")
    ap.add_argument("--min-score", type=int)
    ap.add_argument("--max-score", type=int)
    ap.add_argument("--tag", action="append", default=[],
                    help="smell tag; repeatable (ANY unless --match-all)")
    ap.add_argument("--match-all", action="store_true", help="require ALL --tag")
    ap.add_argument("--sev", choices=["HIGH", "MED", "LOW"],
                    help="has at least one finding of this severity")
    ap.add_argument("--band")
    ap.add_argument("--coupling", choices=["low", "med", "high", "core"])
    ap.add_argument("--needs-audit", action="store_true",
                    help="stale (contentHash != auditedHash) or never scored")
    ap.add_argument("--sort", choices=["score", "loc", "label", "band"], default="score")
    ap.add_argument("--desc", action="store_true", help="sort descending")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--format", choices=["table", "ids", "paths", "findings", "json", "count"],
                    default="table")
    args = ap.parse_args()

    state = json.load(open(args.state, encoding="utf-8"))
    mods = state.get("modules", [])

    bound = GRADE_BOUND[args.max_grade] if args.max_grade else None
    tags = set(args.tag)

    def keep(m):
        s = m.get("score")
        if bound is not None and not (s is not None and s < bound):
            return False
        if args.min_score is not None and not (s is not None and s >= args.min_score):
            return False
        if args.max_score is not None and not (s is not None and s <= args.max_score):
            return False
        if tags:
            mt = set(m.get("tags") or [])
            if args.match_all and not tags <= mt:
                return False
            if not args.match_all and not (tags & mt):
                return False
        if args.sev and not any(f.get("sev") == args.sev for f in (m.get("findings") or [])):
            return False
        if args.band and m.get("band") != args.band:
            return False
        if args.coupling and m.get("coupling") != args.coupling:
            return False
        if args.needs_audit:
            stale = (m.get("score") is None or not m.get("auditedHash")
                     or m.get("auditedHash") != m.get("contentHash"))
            if not stale:
                return False
        return True

    sel = [m for m in mods if keep(m)]
    key = {"score": lambda m: (m.get("score") if m.get("score") is not None else 999),
           "loc": lambda m: m.get("loc") or 0,
           "label": lambda m: m.get("label", ""),
           "band": lambda m: m.get("band", "")}[args.sort]
    sel.sort(key=key, reverse=args.desc)
    if args.limit:
        sel = sel[:args.limit]

    if args.format == "count":
        print(len(sel))
    elif args.format == "ids":
        print(" ".join(m["id"] for m in sel))
    elif args.format == "paths":
        seen, out = set(), []
        for m in sel:
            for p in (m.get("paths") or []):
                if p not in seen:
                    seen.add(p); out.append(p)
        print("\n".join(out))
    elif args.format == "findings":
        for m in sel:
            for f in (m.get("findings") or []):
                print(f"{m['id']}\t{f.get('sev')}\t{f.get('loc','')}\t{f.get('text','')}")
    elif args.format == "json":
        print(json.dumps(sel, ensure_ascii=False, indent=1))
    else:  # table
        print(f"# {len(sel)} of {len(mods)} modules match", file=sys.stderr)
        for m in sel:
            s = m.get("score")
            sg = f"{s if s is not None else '--'}/{m.get('grade','-')}"
            tg = ",".join(t for t in (m.get("tags") or []) if t != "clean") or "-"
            print(f"{m['id']:<22} {sg:>7} {str(m.get('loc') or 0):>6}  {m.get('band',''):<12} {tg}")


if __name__ == "__main__":
    main()
