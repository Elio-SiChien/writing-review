"""Push LaTeX manuscript sections into the running Writing Review service as a new review.

Written for assistant use: after drafting a section in LaTeX, the assistant pushes it so the user
can open the tool (desktop icon), comment on text and figures (keyboard or Win+H voice) and press
"请AI出修改方案". Nothing is converted from PDF; the LaTeX source is read directly.

What it does
- Reads the given section files in order, drops comments, expands number macros (\\nvdef files),
  resolves \\ref and citations from main.aux (compile the manuscript first), and turns LaTeX into
  plain readable text.
- One review paragraph per text paragraph, labelled with the section number (e.g. "3.1.2 ¶1");
  the first paragraph after a heading carries the heading.
- Each figure becomes a figure card (image + caption); each table becomes one paragraph.
- Figure images (PNG) are copied to <data dir>/assets/<review id>/ so the page can show them.
- Saves through the authenticated local API (/api/save). Re-pushing identical text is a no-op;
  changed text gets a new review ID (the tool never overwrites an existing review).

Usage
  python -X utf8 tools/push_latex.py --latex-dir <dir with main.tex> --sections results.tex discussion.tex
         --title "论文2_结果_第1轮" --figures-dir <folder with FigN_*.png> [--id-prefix p2-results]
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

GREEK = {r"\rho": "ρ", r"\alpha": "α", r"\beta": "β", r"\delta": "δ", r"\Delta": "Δ", r"\mu": "μ",
         r"\sigma": "σ", r"\le": "≤", r"\ge": "≥", r"\leq": "≤", r"\geq": "≥", r"\times": "×",
         r"\to": "→", r"\pm": "±", r"\approx": "≈", r"\sim": "~", r"\circ": "°", r"\cdot": "·"}
SUPER = {"2": "²", "3": "³", "-1": "⁻¹", "-2": "⁻²"}


def strip_comments(text):
    out = []
    for line in text.splitlines():
        line = re.sub(r"(?<!\\)%.*$", "", line)
        out.append(line)
    return "\n".join(out)


def read_numbers(latex_dir):
    main = (latex_dir / "main.tex").read_text(encoding="utf-8-sig")
    values = {}
    for name in re.findall(r"\\input\{(numbers[^}]*)\}", main):
        f = latex_dir / (name if name.endswith(".tex") else name + ".tex")
        if f.exists():
            for k, v in re.findall(r"\\nvdef\{([^}]*)\}\{((?:[^{}]|\{[^{}]*\})*)\}", f.read_text(encoding="utf-8")):
                values[k] = v
    return values


def read_aux(latex_dir):
    aux = (latex_dir / "main.aux").read_text(encoding="utf-8", errors="replace") if (latex_dir / "main.aux").exists() else ""
    labels = dict(re.findall(r"\\newlabel\{([^}]*)\}\{\{([^}]*)\}", aux))
    cites = {}
    # \bibcite{key}{{num}{year}{{short author}}{{long author}}}; the year may contain "{}" (e.g. "2026{}")
    for key, num, author in re.findall(r"\\bibcite\{([^}]*)\}\{\{([^}]*)\}\{(?:[^{}]|\{\})*\}\{\{([^}]*)\}\}", aux):
        cites[key] = (num, author.replace("~", " ").replace("{", "").replace("}", ""))
    return labels, cites


class Converter:
    def __init__(self, numbers, labels, cites):
        self.numbers, self.labels, self.cites = numbers, labels, cites

    def nv(self, key):
        v = self.numbers.get(key)
        if v is None:
            return "[" + key + "?]"
        return self.inline(v)

    def cite(self, kind, keys):
        keys = [k.strip() for k in keys.split(",")]
        nums = [self.cites.get(k, ("?", k))[0] for k in keys]
        ref = "[" + ", ".join(nums) + "]"
        if kind == "citet":
            authors = [self.cites.get(k, ("?", k))[1] for k in keys]
            return " and ".join(a + " " for a in authors).strip() + " " + ref
        return ref

    def math(self, m):
        s = m
        for k, v in sorted(GREEK.items(), key=lambda kv: -len(kv[0])):
            s = s.replace(k, v)
        s = re.sub(r"\^\{?(-?\d)\}?", lambda x: SUPER.get(x.group(1), "^" + x.group(1)), s)
        s = re.sub(r"_\\mathrm\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", s)
        s = s.replace("{", "").replace("}", "").replace("\\", "")
        return s

    def inline(self, t):
        t = re.sub(r"\\pv\{([^}]*)\}", lambda m: "p = " + self.nv(m.group(1) + ".p"), t)
        t = re.sub(r"\\nv\{([^}]*)\}", lambda m: self.nv(m.group(1)), t)
        t = re.sub(r"\\(citet|citep|cite)\{([^}]*)\}", lambda m: self.cite(m.group(1), m.group(2)), t)
        t = re.sub(r"\\(?:eq)?ref\{([^}]*)\}", lambda m: self.labels.get(m.group(1), "?"), t)
        t = t.replace(r"\ensuremath{-}", "−").replace(r"\ensuremath{+}", "+").replace(r"\ensuremath", "")
        t = re.sub(r"\$([^$]*)\$", lambda m: self.math(m.group(1)), t)
        t = t.replace("``", "“").replace("''", "”").replace("---", "—").replace("--", "–")
        t = t.replace(r"\%", "%").replace(r"\&", "&").replace(r"\,", " ").replace(r"\ ", " ").replace("~", " ")
        t = re.sub(r"\\(begin|end)\{[^}]*\}", " ", t)          # environment markers (abstract, keyword, ...)
        t = t.replace(r"\sep", ";")
        t = re.sub(r"\\(?:textit|textbf|emph|textrm|text|mathrm|texttt)\{([^}]*)\}", r"\1", t)
        t = re.sub(r"\\[a-zA-Z]+\*?", "", t)
        t = t.replace("{", "").replace("}", "")
        return re.sub(r"\s+", " ", t).strip()


def braced(s, i):
    """Content of the {...} group starting at s[i] == '{' (nested braces allowed)."""
    assert s[i] == "{"
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{" and s[j - 1] != "\\":
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return s[i + 1:j]
        j += 1
    return s[i + 1:]


def tabulars(fl):
    """Bodies of all tabular environments in a float, skipping the column specification."""
    out, pos = [], 0
    while True:
        k = fl.find("\\begin{tabular}", pos)
        if k < 0:
            return out
        j = k + len("\\begin{tabular}")
        while j < len(fl) and fl[j] in " \n[":
            if fl[j] == "[":
                j = fl.index("]", j) + 1
            else:
                j += 1
        spec = braced(fl, j)
        start = j + len(spec) + 2
        end = fl.find("\\end{tabular}", start)
        out.append(fl[start:end])
        pos = end + 1


def parse(sections, conv):
    """Yield dicts: kind text|figure|table, text, label, heading, image."""
    items, heading = [], None
    for f in sections:
        tex = strip_comments(f.read_text(encoding="utf-8-sig"))
        if "\\begin{document}" in tex:   # a stand-alone file (e.g. supplement.tex): skip the preamble
            tex = tex.split("\\begin{document}", 1)[1].replace("\\maketitle", "").replace("\\end{document}", "")
            tex = re.sub(r"\\(clearpage|newpage)", "", tex)
        # floats first, replaced by placeholders so that they keep their position
        floats = []

        def grab(m):
            floats.append(m.group(0))
            return "\n\n@@FLOAT" + str(len(floats) - 1) + "@@\n\n"
        tex = re.sub(r"\\begin\{(figure|table)\*?\}.*?\\end\{\1\*?\}", grab, tex, flags=re.S)
        blocks = re.split(r"\n\s*\n", tex)
        current_num, count = "", 0
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            for m in re.finditer(r"\\(section|subsection|subsubsection)\*?\{([^}]*)\}(\\label\{([^}]*)\})?", b):
                num = conv.labels.get(m.group(4) or "", "")
                current_num, count = num, 0
                heading = (num + " " if num else "") + conv.inline(m.group(2))
            b = re.sub(r"\\(section|subsection|subsubsection)\*?\{[^}]*\}(\\label\{[^}]*\})?", "", b).strip()
            if not b or b.startswith("\\pending"):
                continue
            fm = re.fullmatch(r"@@FLOAT(\d+)@@", b)
            if fm:
                fl = floats[int(fm.group(1))]
                cap = re.search(r"\\caption\{(.*)\}\s*\\label", fl, flags=re.S)
                lab = re.search(r"\\label\{([^}]*)\}", fl)
                num = conv.labels.get(lab.group(1), "?") if lab else "?"
                caption = conv.inline(cap.group(1)) if cap else ""
                k = fl.find("\\caption*{")
                if k >= 0:
                    # unnumbered caption with its own label, e.g. supplementary "\textbf{Table S1a.} ..."
                    body = braced(fl, k + len("\\caption*"))
                    m = re.match(r"\s*\\textbf\{([^}]*)\}\s*(.*)", body, flags=re.S)
                    if m:
                        num = conv.inline(m.group(1)).rstrip(".").replace("Table ", "").replace("Fig. ", "")
                        caption = conv.inline(m.group(2))
                    else:
                        caption = conv.inline(body)
                if fl.lstrip().startswith("\\begin{figure"):
                    img = re.search(r"\\figfile(?:\[[^\]]*\])?\{([^}]*)\}", fl)
                    items.append(dict(kind="figure", label="Fig. " + num, text="Fig. " + num + ". " + caption,
                                      image=img.group(1) if img else None, heading=heading))
                else:
                    rows = []
                    for body in tabulars(fl):
                        body = re.sub(r"\\chg\{([^}]*)\}", lambda m: " & ".join(
                            ["\\nv{%s.before}" % m.group(1), "\\nv{%s.after}" % m.group(1), "\\nv{%s.change}" % m.group(1),
                             "\\nv{%s.ninc}/\\nv{%s.ntot}" % (m.group(1), m.group(1)), "\\nv{%s.p}" % m.group(1)]), body)
                        for row in re.split(r"\\\\", body):
                            row = re.sub(r"\\(toprule|midrule|bottomrule|addlinespace|hline)", "", row).strip()
                            row = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}", "", row)
                            if row:
                                rows.append(" | ".join(conv.inline(c) for c in row.split("&")))
                    items.append(dict(kind="table", label="Table " + num,
                                      text="Table " + num + ". " + caption + ("\n" + "\n".join(rows) if rows else ""),
                                      heading=heading))
                heading = None
                continue
            if "\\item" in b:
                # numbered lists (e.g. conclusions): the lead-in and each item become separate paragraphs
                parts = re.split(r"\\item\b", b)
                lead = re.sub(r"\\(begin|end)\{(enumerate|itemize)\}(\[[^\]]*\])?", "", parts[0]).strip()
                if lead:
                    count += 1
                    items.append(dict(kind="text", label=(current_num + " ¶" + str(count)).strip(),
                                      text=conv.inline(lead), heading=heading))
                    heading = None
                for k, part in enumerate(parts[1:], 1):
                    part = re.sub(r"\\(begin|end)\{(enumerate|itemize)\}(\[[^\]]*\])?", "", part).strip()
                    items.append(dict(kind="text", label=(current_num + " (" + str(k) + ")").strip(),
                                      text=conv.inline(part), heading=heading))
                    heading = None
                continue
            count += 1
            items.append(dict(kind="text", label=(current_num + " ¶" + str(count)).strip(), text=conv.inline(b),
                              heading=heading))
            heading = None
    return items


def token_and_storage(base):
    page = urllib.request.urlopen(base + "/", timeout=3).read().decode("utf-8")
    token = re.search(r'name="review-token" content="([^"]+)"', page).group(1)
    req = urllib.request.Request(base + "/api/storage", headers={"X-Review-Token": token})
    return token, json.load(urllib.request.urlopen(req, timeout=3))


def call(base, token, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-Review-Token": token, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=10))
    except urllib.error.HTTPError as exc:
        raise SystemExit(path + ": " + exc.read().decode("utf-8", errors="replace"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--latex-dir", type=Path, required=True)
    ap.add_argument("--sections", nargs="+", required=True, help="file names inside <latex-dir>/sections")
    ap.add_argument("--title", required=True)
    ap.add_argument("--figures-dir", type=Path, help="folder with <figfile name>.png")
    ap.add_argument("--id-prefix", default="tex")
    ap.add_argument("--scope", default="academic", choices=["academic", "grant", "general"])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dry-run", action="store_true", help="print the paragraphs, do not save")
    ap.add_argument("--parent", help="create the next round of this review (only after the user approved the plan)")
    ap.add_argument("--approval-note", help="required with --parent: how the user approved, in the chat")
    ap.add_argument("--responses", type=Path,
                    help="required with --parent: JSON list of {commentId, status: addressed|carried, action}")
    args = ap.parse_args()

    latex = args.latex_dir.resolve()
    labels, cites = read_aux(latex)
    conv = Converter(read_numbers(latex), labels, cites)
    items = parse([latex / "sections" / s for s in args.sections], conv)
    if not items:
        raise SystemExit("No paragraphs found")
    paragraphs = []
    for i, it in enumerate(items, 1):
        p = dict(id="P" + str(i), original=it["text"], current=it["text"], label=it["label"], kind=it["kind"])
        if it.get("heading"):
            p["heading"] = it["heading"]
        if it["kind"] == "figure" and it.get("image"):
            p["image"] = it["image"] + ".png"
        paragraphs.append(p)
    digest = hashlib.sha256(json.dumps([[p["id"], p["original"]] for p in paragraphs], ensure_ascii=False).encode()).hexdigest()
    rid = re.sub(r"[^A-Za-z0-9_-]", "-", args.id_prefix)[:60] + "-" + digest[:10]
    if args.dry_run:
        for p in paragraphs:
            print(("\n### " + p["heading"]) if p.get("heading") else "", "\n[" + p["label"] + "]", p["original"][:300])
        print("\nparagraphs:", len(paragraphs), "id:", rid)
        return

    base = "http://127.0.0.1:" + str(args.port)
    try:
        token, storage = token_and_storage(base)
    except Exception:
        raise SystemExit("Writing Review is not running. Double-click the desktop icon 写作复利 first.")
    assets = Path(storage["dataDirectory"]) / "assets" / rid
    missing = []
    for p in paragraphs:
        if p.get("image"):
            src = (args.figures_dir / p["image"]) if args.figures_dir else None
            if src and src.is_file():
                assets.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, assets / p["image"])
                p["imagePath"] = str(assets / p["image"])
            else:
                missing.append(p["image"])
                p.pop("image")
    review = dict(id=rid, title=args.title, scope=args.scope, paragraphs=paragraphs, comments=[], assetSet=rid,
                  sourceFiles=[str(latex / "sections" / s) for s in args.sections])
    if args.parent:
        # Next round through the existing round API: every parent comment needs one response; the server
        # checks the parent's saved version so that a stale approval cannot overwrite newer comments.
        if not args.approval_note or not args.responses:
            raise SystemExit("--parent needs --approval-note and --responses")
        parent = call(base, token, "/api/reviews/" + args.parent)
        responses = json.loads(args.responses.read_text(encoding="utf-8"))
        missing_ids = {c["id"] for c in parent["comments"]} - {r["commentId"] for r in responses}
        if missing_ids:
            raise SystemExit("No response for comments: " + ", ".join(sorted(missing_ids)))
        child = call(base, token, "/api/rounds", {"parentReviewId": args.parent, "expectedVersion": parent["version"],
                                                    "approvalNote": args.approval_note, "review": review,
                                                    "responses": responses})
        print("New round:", child["title"], "| id", child["id"], "| round", child["lineage"]["roundNumber"],
              "| parent version", parent["version"])
        print("Handoff folder:", child["storage"].get("directory"))
        return
    try:
        old = call(base, token, "/api/reviews/" + rid)
        print("Unchanged text, already in the tool:", old["title"], "| id", rid)
        return
    except SystemExit as exc:
        if "not found" not in str(exc).lower():
            raise
    saved = call(base, token, "/api/save", {"review": review, "expectedVersion": 0})
    print("Pushed:", saved["title"], "| id", rid, "| paragraphs", len(paragraphs),
          "| figures", sum(1 for p in paragraphs if p.get("image")))
    print("Handoff folder:", saved["storage"].get("directory"))
    if missing:
        print("Figure images not found (card shows caption only):", ", ".join(missing))


if __name__ == "__main__":
    main()
