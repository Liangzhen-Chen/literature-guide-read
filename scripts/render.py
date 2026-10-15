#!/usr/bin/env python3
"""Build the reading page, or pull the data back out of one.

  python render.py WORK/paragraphs.json WORK/guide.json [WORK/paras_*.json] --out OUT.html
         [--sources WORK/sources.json] [--pdf reading.pdf] [--no-page-images] [--lang zh|en]
  python render.py --dump OUT.html --out WORK
"""
import argparse
import base64
import datetime
import html
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import report, run_checks  # noqa: E402
from common import SKILL_DIR, as_lang, load_elements, load_guide, load_json, skill_version  # noqa: E402

DATA_RE = re.compile(r'<script id="guide-data" type="application/json">(.*?)</script>', re.S)
CAP_KEY_RE = re.compile(r"^\s*(?:(?P<fig>fig(?:ure)?s?\.?|exhibit|chart|plate|map|图)|(?P<tab>tables?|tab\.|表))\s*(?P<n>\d+)", re.I)
MENTION_RE = re.compile(r"(?:\b(?P<w>fig(?:ure)?s?\.?|tables?|tab\.)\s*(?P<n>\d+))|(?:(?P<c>[图表])\s*(?P<m>\d+))", re.I)


def cap_key(text):
    m = CAP_KEY_RE.match(text or "")
    if not m:
        return None
    return ["table" if m.group("tab") else "fig", int(m.group("n"))]


def mentions(text):
    out = []
    for m in MENTION_RE.finditer(text):
        if m.group("w"):
            out.append(["table" if m.group("w").lower().startswith("tab") else "fig", int(m.group("n"))])
        else:
            out.append(["table" if m.group("c") == "表" else "fig", int(m.group("m"))])
    return out


def page_images(pdf_path, pages, res=110):
    """Whole-page images for pages that carry figures or tables. No cropping."""
    imgs = {}
    if not pages or not pdf_path or not Path(pdf_path).exists():
        return imgs
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for p in sorted(pages):
                im = pdf.pages[p - 1].to_image(resolution=res).original.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=72, optimize=True)
                imgs[str(p)] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return imgs
    except Exception as e:  # fall back to poppler
        print(f"pdfplumber could not render pages ({e}); trying pdftoppm")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for p in sorted(pages):
                stem = Path(tmp) / f"p{p}"
                subprocess.run(["pdftoppm", "-jpeg", "-r", str(res), "-f", str(p), "-l", str(p), "-singlefile",
                                str(pdf_path), str(stem)], check=True, capture_output=True)
                imgs[str(p)] = "data:image/jpeg;base64," + base64.b64encode(stem.with_suffix(".jpg").read_bytes()).decode()
    except Exception as e:
        print(f"page images skipped: {e}")
    return imgs


def build_data(doc, guide, comp, sources, imgs, lang, crops=None):
    primary = comp["primary"]
    langs = comp["stats"]["langs"]
    items = {}
    for it in doc["items"]:
        if it["type"] in ("para", "heading", "caption", "note", "frag"):  # frags are kept for --dump and checks
            items[it["id"]] = {k: it[k] for k in ("type", "text", "page", "pages", "level", "notes", "num", "ref", "table",
                                                   "equation", "has_math", "tex", "bbox")
                               if it.get(k) is not None}
    order = [it["id"] for it in doc["items"] if it["type"] in ("heading", "caption", "para")]
    first = {}
    for it in doc["items"]:
        if it["type"] == "para":
            for key in mentions(it["text"]):
                first.setdefault(tuple(key), it["id"])
    figs = {}
    for it in doc["items"]:
        if it["type"] == "caption":
            key = cap_key(it["text"])
            figs[it["id"]] = {"key": key, "host": first.get(tuple(key)) if key else None, "page": it["page"]}
    table_pages, last = {}, None
    for it in doc["items"]:
        if it["type"] == "para":
            last = it["id"]
        elif it["type"] == "frag" and it.get("table") and last:
            table_pages.setdefault(last, it["page"])
    open_assets = {}
    if sources:
        for f in sources.get("figures", []):
            if f.get("num") is None:
                continue
            key = (f.get("kind", "fig"), int(f["num"]))
            cid = next((c for c, v in figs.items() if v["key"] and tuple(v["key"]) == key), None)
            if cid:
                open_assets[cid] = {k: f[k] for k in ("caption", "img", "rows") if f.get(k)}
    entries = {}
    for eid, g in guide["paras"].items():
        if eid not in items:
            continue
        e = {"tier": g["tier"], "role": as_lang(g.get("role"), primary)}
        for f in ("note", "read", "why"):
            if g.get(f) is not None:
                e[f] = as_lang(g[f], primary)
        if g.get("ref"):
            e["ref"] = g["ref"]
        els, used = [], []
        spans = {i: (s, t) for s, t, i in comp["hl"].get(eid, [])}
        for i, x in enumerate(g.get("els") or []):
            y = {"t": x["t"]}
            for f in ("s", "x", "term"):
                if x.get(f) is not None:
                    y[f] = as_lang(x[f], primary)
            if x.get("a"):
                y["a"] = x["a"]
            if x.get("tex"):
                y["tex"] = str(x["tex"])
            if x.get("why") is not None:
                y["why"] = as_lang(x["why"], primary)
            if isinstance(x.get("syms"), list):
                y["syms"] = [{"s": str(z.get("s", "")), "m": as_lang(z.get("m"), primary)} for z in x["syms"] if isinstance(z, dict)]
            if i in spans and not any(spans[i][0] < b and a < spans[i][1] for a, b in used):
                # String.slice in the page uses UTF-16 code units, not Python code points.
                text = items[eid]["text"]
                y["hl"] = [len(text[:offset].encode("utf-16-le")) // 2 for offset in spans[i]]
                used.append(spans[i])
            els.append(y)
        e["els"] = els
        entries[eid] = e
    parts = []
    for p in guide.get("parts", []):
        q = {k: p[k] for k in ("id", "range", "claim_p", "skip") if p.get(k) is not None}
        if isinstance(p.get("recall"), list):
            q["recall"] = [{"q": as_lang(x.get("q"), primary), "a": as_lang(x.get("a"), primary)} for x in p["recall"] if isinstance(x, dict)]
        for f in ("title", "role", "claim"):
            if p.get(f) is not None:
                q[f] = as_lang(p[f], primary)
        parts.append(q)
    logic = {"rels": {}, "flows": {}}
    for p in guide.get("parts", []):
        if p.get("rel"):
            logic["rels"][p["id"]] = [dict(r, label=as_lang(r["label"], primary)) if r.get("label") is not None else dict(r)
                                      for r in p["rel"]]
        if p.get("flow"):
            logic["flows"][p["id"]] = [dict(st, x=as_lang(st.get("x"), primary)) for st in p["flow"]]
    crops = crops or {}
    # crops of equation/table fragments: a table that follows a caption goes to the paragraph that first cites
    # the caption (method.md section 8); anything else goes to the paragraph it follows
    frag_crops, last, last_cap = {}, None, None
    for it in doc["items"]:
        if it["type"] == "para":
            last, last_cap = it["id"], None
        elif it["type"] == "caption":
            last_cap = it["id"]
        elif it["type"] == "frag" and it["id"] in crops:
            host = None
            if it.get("table") and last_cap and figs.get(last_cap, {}).get("host"):
                host = figs[last_cap]["host"]
            host = host or last
            if host:
                frag_crops.setdefault(host, []).append(it["id"])
    glossary = []  # terms and symbols the page can explain on hover wherever they recur
    for eid, g in guide["paras"].items():
        for x in g.get("els") or []:
            if x.get("t") == "def" and x.get("term") and x.get("x"):
                glossary.append({"term": str(x["term"]), "x": as_lang(x["x"], primary), "src": eid})
            for z in x.get("syms") or [] if isinstance(x.get("syms"), list) else []:
                if isinstance(z, dict) and z.get("s") and z.get("m") and "\\" not in str(z["s"]):
                    glossary.append({"term": str(z["s"]), "x": as_lang(z["m"], primary), "src": eid})
    has_tex = (any(e.get("tex") for g in entries.values() for e in g["els"])
               or any(q.get("tex") for q in (sources or {}).get("equations", [])))
    meta = dict(guide.get("meta") or {})
    for f in ("genre", "purpose", "familiarity"):
        if f in meta:
            meta[f] = as_lang(meta[f], primary)
    questions = [{"q": as_lang(q.get("q"), primary), "a": as_lang(q.get("a"), primary), "p": [i for i in (q.get("p") or []) if i in items]}
                 for q in (guide.get("questions") or []) if isinstance(q, dict)]
    return {
        "v": 2, "skill_version": skill_version(), "generated": datetime.date.today().isoformat(),
        "langs": langs, "default_lang": lang if lang in langs else langs[0],
        "doc": {k: doc.get(k) for k in ("source", "source_path", "mode", "page_count", "title_guess")},
        "meta": meta, "thesis": as_lang(guide.get("thesis"), primary), "overview": as_lang(guide.get("overview"), primary),
        "parts": parts, "order": order, "items": items, "page_labels": doc.get("page_labels") or {},
        "guide": entries, "figs": figs, "table_pages": table_pages, "page_images": imgs,
        "open": {"assets": open_assets, "equations": (sources or {}).get("equations", []),
                 "text_check": {r["id"]: r["missing"] for r in (sources or {}).get("text_check", [])},
                 "source": (sources or {}).get("source")},
        "types": load_elements(), "logic": logic,
        "crops": crops, "frag_crops": frag_crops, "has_tex": has_tex, "glossary": glossary, "questions": questions,
    }


def crop_images(doc, work_dir):
    """Data URIs for the crops segment.py wrote next to paragraphs.json."""
    out = {}
    if not work_dir:
        return out
    for pid, rel in (doc.get("crops") or {}).items():
        path = Path(work_dir) / rel
        if path.exists():
            out[pid] = "data:image/png;base64," + base64.b64encode(_small_png(path.read_bytes())).decode()
    return out


def _small_png(raw):
    """Crops are black-on-white: an optimised grayscale PNG is 20-30% smaller with no visible change."""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw))
        buf = io.BytesIO()
        im.convert("L").save(buf, "PNG", optimize=True)
        return buf.getvalue() if len(buf.getvalue()) < len(raw) else raw
    except Exception:
        return raw


def katex_bundle():
    """Vendored KaTeX, fonts inlined, for pages that contain formulas."""
    base = SKILL_DIR / "assets" / "katex"
    css = (base / "katex.min.css").read_text(encoding="utf-8")

    def font(m):
        p = base / m.group(1)
        if not p.exists():
            return m.group(0)
        return "url(data:font/woff2;base64," + base64.b64encode(p.read_bytes()).decode() + ")"
    css = re.sub(r"url\((fonts/[^)]+\.woff2)\)", font, css)
    css = re.sub(r",url\(fonts/[^)]+\.(?:woff|ttf)\) format\(\"(?:woff|truetype)\"\)", "", css)
    js = (base / "katex.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    return f"<style>{css}</style>\n<script>{js}</script>"


def render(doc, guide, out_path, args, work_dir=None):
    errors, warns, comp = run_checks(doc, guide, args.density)
    report(errors, warns, comp)
    if errors and not args.force:
        sys.exit("There are errors; no page was written. Fix them and run again.")
    sources = load_json(args.sources) if args.sources else None
    pages = set()
    if not args.no_page_images:
        pages = {it["page"] for it in doc["items"] if it["type"] == "caption" or (it["type"] == "frag" and it.get("table"))}
    pdf = args.pdf or doc.get("source_path")
    imgs = page_images(pdf, {p for p in pages if p}) if pages else {}
    data = build_data(doc, guide, comp, sources, imgs, args.lang, crops=crop_images(doc, work_dir))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = (guide.get("meta") or {}).get("title") or doc.get("title_guess") or doc.get("source") or "Reading guide"
    tpl = (SKILL_DIR / "assets" / "template.html").read_text(encoding="utf-8")
    # fill the KaTeX slot first: once the JSON payload is in, its text must never be scanned for placeholders
    page = tpl.replace("__KATEX__", katex_bundle() if data["has_tex"] else "").replace("__TITLE__", html.escape(title))
    head, _, tail = page.partition("__DATA__")
    page = head + payload + tail
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"written: {out_path} ({out_path.stat().st_size // 1024} KB; {len(imgs)} page images; "
          f"{len(data['crops'])} crops; KaTeX {'inlined' if data['has_tex'] else 'not needed'})")


def dump(html_path, out_dir):
    m = DATA_RE.search(Path(html_path).read_text(encoding="utf-8"))
    if not m:
        sys.exit("no guide data in this file")
    d = json.loads(m.group(1).replace("<\\/", "</"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order = {k: i for i, k in enumerate(d["items"])}  # JSON keeps the original item order
    items = [dict(v, id=k) for k, v in sorted(d["items"].items(), key=lambda kv: order[kv[0]])]
    doc = {"version": 2, **d["doc"], "page_labels": d["page_labels"], "items": items}
    if d.get("crops"):  # restore the PNGs the page embeds, so a re-render keeps the crops
        (out / "crops").mkdir(exist_ok=True)
        doc["crops"] = {}
        for pid, uri in d["crops"].items():
            if uri.startswith("data:image/png;base64,"):
                (out / "crops" / f"{pid}.png").write_bytes(base64.b64decode(uri.split(",", 1)[1]))
                doc["crops"][pid] = f"crops/{pid}.png"
    paras = {}
    for eid, g in d["guide"].items():
        g = dict(g)
        g["els"] = [{k: v for k, v in e.items() if k != "hl"} for e in g.get("els", [])]
        paras[eid] = g
    logic = d.get("logic") or {}
    parts = []
    for p in d["parts"]:
        p = dict(p)
        if p["id"] in logic.get("rels", {}):
            p["rel"] = logic["rels"][p["id"]]
        if p["id"] in logic.get("flows", {}):
            p["flow"] = logic["flows"][p["id"]]
        parts.append(p)
    guide = {"meta": d["meta"], "thesis": d["thesis"], "overview": d["overview"], "parts": parts, "paras": paras}
    if d.get("questions"):
        guide["questions"] = d["questions"]
    (out / "paragraphs.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "guide.json").write_text(json.dumps(guide, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"recovered {out / 'paragraphs.json'} and {out / 'guide.json'} (all paragraph entries are in guide.json; "
          f"crops are in {out / 'crops'}; page images and open-version assets are rebuilt on the next render)")


def main():
    ap = argparse.ArgumentParser(description="Build the reading page")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump", metavar="HTML")
    ap.add_argument("--sources", help="sources.json from sources.py")
    ap.add_argument("--pdf", help="PDF for page images, if it moved since segmentation")
    ap.add_argument("--no-page-images", action="store_true")
    ap.add_argument("--lang", choices=["zh", "en"])
    ap.add_argument("--density", choices=["low", "medium", "high"])
    ap.add_argument("--force", action="store_true", help="write the page despite errors (debugging only)")
    args = ap.parse_args()
    if args.dump:
        dump(args.dump, args.out)
        return
    if len(args.files) < 2:
        sys.exit("need paragraphs.json and at least one guide file")
    render(load_json(args.files[0]), load_guide(args.files[1:]), args.out, args, work_dir=Path(args.files[0]).parent)


if __name__ == "__main__":
    main()
