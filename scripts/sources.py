#!/usr/bin/env python3
"""Optional open version of a reading.

The PDF stays the source of the reading text and the page numbers. An open version (arXiv HTML first,
the arXiv TeX source as a fallback, or any HTML file you saved) only supplies clean figures, tables and
formulas, plus a report of words that the PDF's text layer dropped.

  python sources.py detect WORK/paragraphs.json             # look for an arXiv id or a DOI
  python sources.py fetch 2312.01234 --out WORK            # needs network access to arxiv.org
  python sources.py parse WORK/open.html --out WORK [--base URL] [--paras WORK/paragraphs.json]
  python sources.py parse-tex WORK/tex --out WORK [--paras WORK/paragraphs.json]
"""
import argparse
import base64
import difflib
import json
import re
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html|src)/|arXiv:\s?)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
CAP_RE = re.compile(r"^\s*(?:(?P<fig>fig(?:ure)?\.?|图)|(?P<tab>table|表))\s*(?P<n>\d+)", re.I)
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
        ".webp": "image/webp"}
MAX_IMG = 2_000_000
UA = {"User-Agent": "reading-guide/0.2 (open-version fetch)"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.geturl(), r.headers.get("Content-Type", "")


def detect(paras_path):
    doc = json.loads(Path(paras_path).read_text(encoding="utf-8"))
    text = " ".join(i["text"] for i in doc["items"][:80])
    found = {"arxiv": sorted({m.group(1) for m in ARXIV_RE.finditer(text)}),
             "doi": sorted({m.group(1).rstrip(".,;)") for m in DOI_RE.finditer(text)})}
    src = doc.get("source_path")
    if src and Path(src).exists() and src.lower().endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(src) as pdf:
                meta = " ".join(str(v) for v in (pdf.metadata or {}).values())
                first = pdf.pages[0].extract_text() or ""
            for m in ARXIV_RE.finditer(meta + " " + first + " " + "\n".join(line[::-1] for line in first.splitlines())):
                found["arxiv"] = sorted(set(found["arxiv"]) | {m.group(1)})
            for m in DOI_RE.finditer(meta + " " + first):
                found["doi"] = sorted(set(found["doi"]) | {m.group(1).rstrip(".,;)")})
        except Exception:
            pass
    print(json.dumps(found, ensure_ascii=False))
    if not found["arxiv"] and not found["doi"]:
        print("no arXiv id or DOI found; continue with the PDF alone, or pass an id to `fetch` if you know it")


def is_article_html(body):
    """Require actual converted article content, not a long error/landing page."""
    if b"<html" not in body[:2000].lower() or len(body) <= 5000:
        return False
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "html.parser")
    return soup.find("article") is not None and soup.find(class_="ltx_para") is not None


def extract_source_archive(tf, dest):
    """Extract regular files only, including on Python versions without tar filters."""
    root = dest.resolve()
    members = tf.getmembers()
    for member in members:
        path = Path(member.name)
        target = (root / path).resolve()
        if path.is_absolute() or ".." in path.parts or (target != root and root not in target.parents):
            raise ValueError(f"unsafe archive path: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise ValueError(f"unsupported archive entry: {member.name}")
    for member in members:
        target = root / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def fetch(arxiv_id, out, tex=False):
    out.mkdir(parents=True, exist_ok=True)
    if not tex:
        for url in (f"https://arxiv.org/html/{arxiv_id}", f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"):
            try:
                body, final, ctype = get(url)
                if is_article_html(body):
                    (out / "open.html").write_bytes(body)
                    (out / "open.json").write_text(json.dumps({"kind": "html", "url": final}), encoding="utf-8")
                    print(f"saved {out / 'open.html'} from {final}")
                    print(f"next: python sources.py parse {out / 'open.html'} --out {out} --base {final} --paras {out / 'paragraphs.json'}")
                    return
            except Exception as e:
                print(f"{url}: {e}")
    url = f"https://arxiv.org/src/{arxiv_id}"
    try:
        body, final, ctype = get(url, timeout=60)
        tgz = out / f"{arxiv_id.replace('/', '_')}.tar.gz"
        tgz.write_bytes(body)
        dest = out / "tex"
        dest.mkdir(exist_ok=True)
        try:
            with tarfile.open(tgz) as tf:
                extract_source_archive(tf, dest)
        except tarfile.ReadError:  # a single gzipped .tex file
            import gzip
            (dest / "main.tex").write_bytes(gzip.decompress(body))
        print(f"unpacked TeX source into {dest}")
        print(f"next: python sources.py parse-tex {dest} --out {out} --paras {out / 'paragraphs.json'}")
    except Exception as e:
        print(f"{url}: {e}")
        print("Could not reach arXiv. On claude.ai the code sandbox only allows listed domains; an organization "
              "owner can add arxiv.org, or run this step in a local agent. Continuing without the open version is fine.")
        sys.exit(2)


def data_uri(raw, suffix):
    mime = MIME.get(suffix.lower())
    if not mime or len(raw) > MAX_IMG:
        return None
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def load_image(src, base, folder):
    if not src:
        return None
    if src.startswith("data:"):
        return src
    local = (folder / urllib.parse.unquote(src)).resolve()
    if local.exists():
        return data_uri(local.read_bytes(), local.suffix)
    if base:
        url = urllib.parse.urljoin(base, src)
        try:
            body, _, _ = get(url)
            return data_uri(body, Path(urllib.parse.urlparse(url).path).suffix)
        except Exception:
            return None
    return None


def cap_key(text):
    m = CAP_RE.match(text or "")
    if not m:
        return None, None
    return ("table" if m.group("tab") else "fig"), int(m.group("n"))


def words(text):
    return re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?|[\u4e00-\u9fff]", text.lower())


def compare_text(paras_path, open_paras):
    """Report words present in the open version but missing from the PDF text, paragraph by paragraph."""
    doc = json.loads(Path(paras_path).read_text(encoding="utf-8"))
    pool = [(t, words(t)) for t in open_paras if len(t) > 60]
    report = []
    for it in doc["items"]:
        if it["type"] != "para":
            continue
        w = words(it["text"])
        if len(w) < 12:
            continue
        sw = set(w)
        best, score = None, 0.0
        for t, ow in pool:
            if len(sw & set(ow)) < 0.5 * len(sw):
                continue
            r = difflib.SequenceMatcher(None, w, ow, autojunk=False).ratio()
            if r > score:
                best, score = ow, r
        if best is None or score < 0.8 or score > 0.999:
            continue
        sm = difflib.SequenceMatcher(None, w, best, autojunk=False)
        gaps = [" ".join(best[j1:j2]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("insert", "replace") and j2 - j1 >= 2
                and "".join(w[i1:i2]) != "".join(best[j1:j2])]
        if gaps:
            report.append({"id": it["id"], "ratio": round(score, 3), "missing": gaps[:5]})
    return report


def finish(result, out, paras, open_paras):
    if paras:
        result["text_check"] = compare_text(paras, open_paras)
    (out / "sources.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    figs = result["figures"]
    print(f"wrote {out / 'sources.json'}: {sum(1 for f in figs if f['kind'] == 'fig')} figures "
          f"({sum(1 for f in figs if f.get('img'))} with images), {sum(1 for f in figs if f['kind'] == 'table')} tables, "
          f"{len(result['equations'])} display equations")
    for r in result.get("text_check", []):
        print(f"  {r['id']}: the open version has words the PDF text lacks: {' | '.join(r['missing'])}")


def html_paragraphs(soup):
    """Extract prose without inline footnotes or duplicate MathML alternatives."""
    for extra in soup.select(".ltx_note, math annotation, math annotation-xml"):
        extra.decompose()
    return [p.get_text(" ", strip=True) for p in soup.find_all("p")]


def parse_html(path, out, base, paras):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("parsing HTML needs beautifulsoup4: pip install beautifulsoup4")
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "open.json"
    if not base and meta.exists():
        base = json.loads(meta.read_text(encoding="utf-8")).get("url")
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="replace"), "html.parser")
    figs = []
    for f in soup.find_all("figure"):
        if f.find_parent("figure") is not None:
            continue  # sub-figures belong to their parent
        cap_el = next((c for c in f.find_all("figcaption") if c.find_parent("figure") is f), None)
        cap = cap_el.get_text(" ", strip=True) if cap_el else ""
        kind, num = cap_key(cap)
        table = f.find("table")
        classes = " ".join(f.get("class") or [])
        if kind is None:
            kind = "table" if ("ltx_table" in classes or (table and not f.find("img"))) else "fig"
        entry = {"kind": kind, "num": num, "caption": cap}
        if kind == "table" and table is not None:
            entry["rows"] = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        img = f.find("img") or f.find("object", attrs={"type": "image/svg+xml"})
        if img is not None:
            entry["img"] = load_image(img.get("src") or img.get("data"), base, Path(path).parent)
        figs.append(entry)
    eqs = [{"tex": m.get("alttext")} for m in soup.find_all("math") if m.get("display") == "block" and m.get("alttext")]
    open_paras = html_paragraphs(soup)
    finish({"source": base or str(path), "kind": "html", "figures": figs, "equations": eqs}, out, paras, open_paras)


def strip_tex(s):
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\\(?:textbf|textit|emph|text|mathrm|cite[tp]?|ref|eqref|label)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", s)
    return re.sub(r"[{}~]", " ", re.sub(r"\s+", " ", s)).strip()


def parse_tex(folder, out, paras):
    folder = Path(folder)
    texs = sorted(folder.rglob("*.tex"))
    if not texs:
        sys.exit(f"no .tex files under {folder}")
    main = next((t for t in texs if "\\documentclass" in t.read_text(errors="ignore")), texs[0])

    def expand(path, depth=0):
        src = path.read_text(errors="ignore")
        if depth > 8:
            return src

        def sub(m):
            name = m.group(1)
            cand = (path.parent / name)
            cand = cand if cand.suffix else cand.with_suffix(".tex")
            return expand(cand, depth + 1) if cand.exists() else ""
        return re.sub(r"\\(?:input|include)\{([^}]+)\}", sub, src)

    src = re.sub(r"(?<!\\)%.*", "", expand(main))
    figs = []
    for env in re.finditer(r"\\begin\{(figure|table|wrapfigure|wraptable)\*?\}(.*?)\\end\{\1\*?\}", src, re.S):
        body = env.group(2)
        cap = re.search(r"\\caption(?:of\{(?:figure|table)\})?(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}", body, re.S)
        caption_kind = re.search(r"\\captionof\{(figure|table)\}", body)
        kind = "table" if (caption_kind.group(1) if caption_kind else env.group(1)).endswith("table") else "fig"
        entry = {"kind": kind, "num": None, "caption": strip_tex(cap.group(1)) if cap else ""}
        if kind == "fig":
            g = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body)
            if g:
                name = g.group(1)
                for cand in [folder / name] + [folder / (name + ext) for ext in (".png", ".jpg", ".jpeg")]:
                    if cand.exists() and cand.suffix.lower() in MIME:
                        entry["img"] = data_uri(cand.read_bytes(), cand.suffix)
                        break
        else:
            tab = re.search(r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}", body, re.S)
            if tab:
                rows = [r for r in re.split(r"\\\\", tab.group(1)) if strip_tex(r.replace("&", " "))]
                entry["rows"] = [[strip_tex(c) for c in r.split("&")] for r in rows]
        figs.append(entry)
    counters = {"fig": 0, "table": 0}
    for f in figs:  # LaTeX numbers floats in order of appearance
        counters[f["kind"]] += 1
        f["num"] = counters[f["kind"]]
    eqs = [{"tex": (m.group(2) if m.group(1) else m.group(3)).strip()}
           for m in re.finditer(r"\\begin\{(equation|align|gather)\*?\}(.*?)\\end\{\1\*?\}|\\\[(.*?)\\\]", src, re.S)]
    body = re.sub(r"\\begin\{(figure|table|equation|align|gather)\*?\}.*?\\end\{\1\*?\}", " ", src, flags=re.S)
    open_paras = [strip_tex(p) for p in re.split(r"\n\s*\n", body)]
    finish({"source": str(main), "kind": "tex", "figures": figs, "equations": eqs}, out, paras, open_paras)


def main():
    ap = argparse.ArgumentParser(description="Optional open version of a reading")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("detect")
    a.add_argument("paragraphs")
    b = sub.add_parser("fetch")
    b.add_argument("arxiv_id")
    b.add_argument("--out", required=True)
    b.add_argument("--tex", action="store_true", help="skip HTML and download the TeX source")
    c = sub.add_parser("parse")
    c.add_argument("html")
    c.add_argument("--out", required=True)
    c.add_argument("--base", help="URL the HTML came from, to resolve images")
    c.add_argument("--paras")
    d = sub.add_parser("parse-tex")
    d.add_argument("folder")
    d.add_argument("--out", required=True)
    d.add_argument("--paras")
    args = ap.parse_args()
    if args.cmd == "detect":
        detect(args.paragraphs)
    elif args.cmd == "fetch":
        fetch(args.arxiv_id, Path(args.out), args.tex)
    elif args.cmd == "parse":
        parse_html(args.html, Path(args.out), args.base, args.paras)
    else:
        parse_tex(args.folder, Path(args.out), args.paras)


if __name__ == "__main__":
    main()
