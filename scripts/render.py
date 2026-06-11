#!/usr/bin/env python3
"""render.py — regenerate architecture-map.html + architecture-audit.md from modules.json.

modules.json is the single source of truth. The HTML and MD are pure projections
of it and must never be hand-edited. Run scan.py --write before rendering so LoC /
content hashes are current.

Usage:
  python render.py --state modules.json \
      --template assets/template.html \
      --out-html architecture-map.html --out-md architecture-audit.md

Stdlib only.
"""
import argparse, json, os


def health_color(s):
    if s is None: return "#6b7280"
    if s < 50:  return "#e0524b"
    if s < 65:  return "#e0804a"
    if s < 75:  return "#d9a441"
    if s < 85:  return "#8f969d"
    return "#5d6b63"


def band_order(state):
    return [b["id"] for b in state.get("bands", []) if not b.get("wire")]


def load_standard(state_path, explicit=None):
    """Effective audit standard: explicit path → project override next to the state
    file (`<state dir>/standard.json`) → the skill's default `reference/standard.json`."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(state_path)), "standard.json"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference", "standard.json"))
    for c in candidates:
        if c and os.path.isfile(c):
            try:
                return json.load(open(c, encoding="utf-8"))
            except (ValueError, OSError):
                pass
    return None


def render_html(state, template, standard=None):
    data = {
        "meta": state.get("meta", {}),
        "bands": state.get("bands", []),
        "spine": state.get("spine", []),
        "reportThemes": state.get("reportThemes", []),
        "standard": standard,
        "modules": [
            {k: m.get(k) for k in (
                "id", "label", "band", "path", "desc", "coupling", "deps",
                "loc", "score", "grade", "tags", "findings")}
            for m in state.get("modules", [])
        ],
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__ARCH_DATA__", blob)


def render_md(state):
    meta = state.get("meta", {})
    mods = [m for m in state.get("modules", []) if m.get("score") is not None]
    bands = {b["id"]: b for b in state.get("bands", [])}
    out = []
    proj = meta.get("project", "Project")
    out.append("<!--")
    out.append(f"  This file:        {meta.get('mdPath', 'architecture-audit.md')}   (written report)")
    out.append(f"  Interactive map:  {meta.get('htmlPath', 'architecture-map.html')}")
    out.append("-->\n")
    out.append(f"# {proj} — Functional Module Quality Audit\n")
    out.append(f"> **Interactive view:** [`{meta.get('htmlPath','architecture-map.html')}`]"
               f"({os.path.basename(meta.get('htmlPath','architecture-map.html'))}) — "
               "per-module scores, findings, LoC, and the dependency graph. This file is the written report.\n")
    gen = meta.get("generatedAt", "")
    loc_line = meta.get("locLine") or (
        f"{meta.get('tracked_loc','?')} tracked LoC across {meta.get('tracked_files','?')} files")
    out.append(f"**Generated:** {gen} · **Modules:** {len(mods)} · **Size:** {loc_line}\n")

    # per-layer averages
    out.append("## Health by layer\n")
    out.append("| Layer | Modules | Avg score |")
    out.append("|---|--:|--:|")
    for b in state.get("bands", []):
        if b.get("wire"):
            continue
        grp = [m for m in mods if m["band"] == b["id"]]
        if not grp:
            continue
        avg = round(sum(m["score"] for m in grp) / len(grp))
        out.append(f"| {b.get('t', b['id'])} | {len(grp)} | {avg} |")
    out.append("")

    # per-module LoC + score, grouped by band, sorted by loc desc
    out.append("## Per-module lines of code & score\n")
    out.append("_LoC is the representative file/folder per module; folder-level modules overlap "
               "and are not additive._\n")
    for b in state.get("bands", []):
        if b.get("wire"):
            continue
        grp = sorted([m for m in mods if m["band"] == b["id"]],
                     key=lambda m: -(m.get("loc") or 0))
        if not grp:
            continue
        out.append(f"### {b.get('t', b['id'])}\n")
        out.append("| Module | LoC | Score | Tags |")
        out.append("|---|--:|:--|:--|")
        for m in grp:
            tags = ", ".join(t for t in (m.get("tags") or []) if t != "clean") or "—"
            loc = f"{m.get('loc',0):,}"
            out.append(f"| {m['label']} | {loc} | {m['score']} {m['grade']} | {tags} |")
        out.append("")

    # worst offenders
    out.append("## Worst offenders\n")
    worst = sorted(mods, key=lambda m: m["score"])[:10]
    for m in worst:
        fnd = m.get("findings") or []
        top = next((f for f in fnd if f["sev"] == "HIGH"), fnd[0] if fnd else None)
        ev = f" — {top['loc']}: {top['text']}" if top else ""
        out.append(f"- **{m['label']} ({m['score']}/{m['grade']})**{ev}")
    out.append("")

    # all findings, by severity
    out.append("## All findings\n")
    for sev in ("HIGH", "MED", "LOW"):
        rows = [(m, f) for m in mods for f in (m.get("findings") or []) if f["sev"] == sev]
        if not rows:
            continue
        out.append(f"### {sev} ({len(rows)})\n")
        for m, f in rows:
            out.append(f"- **{m['label']}** · `{f['loc']}` — {f['text']}")
        out.append("")

    # cross-cutting themes
    themes = state.get("reportThemes", [])
    if themes:
        out.append("## Cross-cutting themes\n")
        for h, body in themes:
            out.append(f"- **{h}.** {body}")
        out.append("")

    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out-html", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--standard", help="path to a custom standard.json (else project override → skill default)")
    args = ap.parse_args()

    state = json.load(open(args.state, encoding="utf-8"))
    template = open(args.template, encoding="utf-8").read()
    standard = load_standard(args.state, args.standard)

    open(args.out_html, "w", encoding="utf-8").write(render_html(state, template, standard))
    open(args.out_md, "w", encoding="utf-8").write(render_md(state))
    n = len(state.get("modules", []))
    scored = sum(1 for m in state.get("modules", []) if m.get("score") is not None)
    print(f"rendered {n} modules ({scored} scored) -> {args.out_html} + {args.out_md}")


if __name__ == "__main__":
    main()
