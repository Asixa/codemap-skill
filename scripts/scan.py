#!/usr/bin/env python3
"""scan.py — compute per-module LoC + content hash and report staleness.

The architecture state file (modules.json) is the source of truth. Each module
declares `paths` (a list of globs, relative to the project root). This script:

  * resolves each module's files, counts lines (LoC) and computes a content hash
    (sha256 over sorted "relpath:sha256(bytes)" pairs) that is stable across
    checkouts (depends on content, not mtime);
  * compares the fresh content hash to `auditedHash` (the hash captured the last
    time the module was audited) to classify each module as:
        fresh      — code unchanged since last audit
        stale      — code changed since last audit (needs re-audit)
        unaudited  — never audited (no auditedHash / no score)
        empty      — paths match no files (likely deleted / moved)
  * with --write, writes the fresh `loc` and `contentHash` back into the state.

It also reports, when in a git repo, what changed since the last codemap run
(`meta.rev`): the commits and which modules they touch — so `update` can show recent
history at a glance and re-audit exactly the affected modules. `--stamp-rev` caches the
current HEAD into `meta.rev` (run at the end of a successful update/generate).

Output (stdout): a JSON report the orchestrator uses to decide what to re-audit.
Stdlib only.
"""
import argparse, glob, hashlib, json, os, subprocess, sys


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root, *args],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_changes_since(root, since):
    """commits + changed files between `since` and HEAD, or None if unavailable."""
    head = git(root, "rev-parse", "HEAD")
    if not head:
        return None  # not a git repo
    info = {"head": head, "since": since}
    if not since or git(root, "rev-parse", "--verify", "--quiet", since + "^{commit}") is None:
        info["commits"], info["files"] = None, None   # no/unknown baseline → diff everything
        return info
    diff = git(root, "diff", "--name-only", since + "..HEAD") or ""
    log = git(root, "log", "--pretty=format:%h %s", since + "..HEAD") or ""
    info["files"] = [f for f in diff.splitlines() if f.strip()]
    info["commits"] = [c for c in log.splitlines() if c.strip()]
    return info

DEFAULT_EXCLUDES = [
    # vcs / editor
    "/.git/", "/.svn/", "/.hg/", "/.idea/", "/.vs/",
    # build / output dirs (py, js/ts, rust, c#/.net, c/c++/cmake, jvm, swift, next/nuxt)
    "__pycache__", "/node_modules/", "/dist/", "/build/", "/out/", "/target/",
    "/bin/", "/obj/", "/cmake-build", "/.gradle/", "/pods/", "/.next/", "/.nuxt/",
    # deps / vendored / generated
    "/vendor/", "/third_party/", "/external/", "/.venv/", "/venv/", "/coverage/",
    ".min.js", ".min.css", ".map", ".pytest", ".d.ts",
    ".designer.cs", ".g.cs", ".generated.", ".pb.go", "_pb2.py",
    # tests are the regression net, not part of a module's audit scope:
    "/tests/", "/test/", "/__tests__/", "/spec/", ".test.", ".spec.",
    "_test.py", "_test.go", "_test.rs", "conftest.py", ".stories.",
    ".tests/", "tests.cs",
]


def iter_files(root, patterns, excludes):
    seen = set()
    for pat in patterns:
        for p in glob.glob(os.path.join(root, pat), recursive=True):
            if not os.path.isfile(p):
                continue
            rp = os.path.relpath(p, root).replace("\\", "/")
            low = "/" + rp.lower()
            if any(e in low for e in excludes):
                continue
            if rp in seen:
                continue
            seen.add(rp)
            yield p, rp


def module_stats(root, module, excludes):
    pats = module.get("paths") or []
    if isinstance(pats, str):
        pats = [pats]
    excl = list(excludes) + list(module.get("exclude", []))
    loc = 0
    parts = []
    nfiles = 0
    for p, rp in sorted(iter_files(root, pats, excl), key=lambda x: x[1]):
        try:
            data = open(p, "rb").read()
        except OSError:
            continue
        loc += data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        parts.append(rp + ":" + hashlib.sha256(data).hexdigest())
        nfiles += 1
    chash = hashlib.sha256("\n".join(parts).encode()).hexdigest() if parts else ""
    return loc, chash, nfiles


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # commit messages may be non-ASCII
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--state", required=True, help="path to modules.json")
    ap.add_argument("--write", action="store_true",
                    help="write fresh loc + contentHash back into the state")
    ap.add_argument("--stamp-rev", action="store_true",
                    help="cache current git HEAD into meta.rev (run at end of a successful update)")
    args = ap.parse_args()

    state = json.load(open(args.state, encoding="utf-8"))
    excludes = state.get("excludes", DEFAULT_EXCLUDES)
    root = os.path.abspath(args.root)

    buckets = {"fresh": [], "stale": [], "unaudited": [], "empty": []}
    union_files = {}
    file_index = {}  # repo-relative path -> [module ids] (for git-change → module mapping)
    for m in state.get("modules", []):
        loc, chash, nfiles = module_stats(root, m, excludes)
        m["loc"] = loc
        m["contentHash"] = chash
        # union for an accurate, non-double-counted repo total
        for p, rp in iter_files(root, (m.get("paths") or []),
                                list(excludes) + list(m.get("exclude", []))):
            union_files[rp] = p
            file_index.setdefault(rp, []).append(m["id"])
        if nfiles == 0:
            buckets["empty"].append(m["id"])
        elif not m.get("auditedHash") or m.get("score") is None:
            buckets["unaudited"].append(m["id"])
        elif m.get("auditedHash") != chash:
            buckets["stale"].append(m["id"])
        else:
            buckets["fresh"].append(m["id"])

    tracked_loc = 0
    for rp, p in union_files.items():
        try:
            data = open(p, "rb").read()
            tracked_loc += data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        except OSError:
            pass

    # git: what changed since the last codemap run (meta.rev)?
    since = state.get("meta", {}).get("rev")
    gc = git_changes_since(root, since)
    git_report = None
    changed_modules = []
    if gc is not None:
        if gc.get("files") is None:
            git_report = {"head": gc["head"], "since": since,
                          "note": "no/unknown baseline rev — treat all unaudited/stale as the change set"}
        else:
            for f in gc["files"]:
                for mid in file_index.get(f, []):
                    if mid not in changed_modules:
                        changed_modules.append(mid)
            git_report = {"head": gc["head"], "since": since,
                          "commits": gc["commits"], "commit_count": len(gc["commits"]),
                          "changed_files": len(gc["files"]),
                          "changed_modules": sorted(changed_modules)}

    if args.stamp_rev and gc and gc.get("head"):
        state.setdefault("meta", {})["rev"] = gc["head"]
    if args.write or args.stamp_rev:
        meta = state.setdefault("meta", {})
        meta["tracked_loc"] = tracked_loc
        meta["tracked_files"] = len(union_files)
        json.dump(state, open(args.state, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    needs = buckets["stale"] + buckets["unaudited"]
    report = {
        "modules": len(state.get("modules", [])),
        "tracked_loc": tracked_loc,
        "tracked_files": len(union_files),
        "needs_audit": needs,
        "needs_audit_count": len(needs),
        "up_to_date": len(needs) == 0 and not buckets["empty"],
        "git": git_report,
        **buckets,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
