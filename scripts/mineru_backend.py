#!/usr/bin/env python3
"""Optional MinerU backend: layout analysis for segment.py.

  python mineru_backend.py run reading.pdf --out WORK [--pages 3-28]   # what segment.py --engine mineru calls

MinerU (pip install "mineru>=4,<5"; mineru-kit models download --tier basic) supplies running-head removal,
headings, tables as structure and the position of display formulas. If its 577 MB formula model (MFR) is
installed it also supplies LaTeX; otherwise formulas are cropped images that the reading model transcribes.
The skill's own rules (sidebar, front matter, numbered-heading depth, footnote linking) are applied here."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment import NUM_HEAD_RE, join_text, link_notes  # noqa: E402

MASTHEAD_LINE_RE = re.compile(r"\b(vol\.|volume|issue|no\.)\s*[\dIVXLCM]+", re.I)

FOOTNOTE_START_RE = re.compile(r"^\d{1,2}\.\s+[A-Z\u4e00-\u9fff]")

MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
HTML_TAG = re.compile(r"</?(?:sup|sub|strong|em|b|i|span|br)\b[^>]*>")
MFR_DIR = Path(os.environ.get("MINERU_HOME", str(Path.home() / ".mineru"))) / "models" / "MinerU-4_models_onnx" / "MFR"


def clean(s):
    s = MD_LINK.sub(r"\1", s or "")
    s = HTML_TAG.sub("", s).replace("**", "").replace("\\*", "*").replace("\\_", "_")
    return re.sub(r"\s+", " ", s).strip()


def _can_import(python):
    try:
        return subprocess.run([python, "-c", "import mineru"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def available(python=None):
    """The interpreter that has MinerU, or None."""
    cands = [python, os.environ.get("MINERU_PYTHON"), sys.executable]
    kit = shutil.which("mineru-kit")
    if kit:
        try:
            first = Path(kit).read_text(errors="ignore").splitlines()[0]
            if first.startswith("#!"):
                cands.append(first[2:].strip())
        except Exception:
            pass
    for c in cands:
        if c and Path(c).exists() and _can_import(c):
            return c
    return None


# Runs mineru-kit in the MinerU interpreter. Without --with-mfr the formula-recognition model is never
# loaded: display formulas keep their boxes (cropped later), inline formula boxes are dropped so their
# characters stay in the text. The PDF render worker re-imports this file, hence the __main__ guard.
LIGHT_RUNNER = r'''
import sys
if __name__ == "__main__":
    with_mfr = sys.argv[1] == "--with-mfr"
    del sys.argv[1]
    if not with_mfr:
        import mineru.backend.analysis.pdf.ocr as ocr
        import mineru.backend.analysis.pdf.formulas as formulas
        from mineru.backend.analysis.pdf.constants import PIPELINE_DET_TYPE
        ocr._build_ocr_det_type_and_mfr_enable = lambda parse_mode, effort: (PIPELINE_DET_TYPE, False)
        _orig = formulas._build_formula_inputs
        formulas._build_formula_inputs = lambda res: [[f for f in page if f.get("label") == "display_formula"] for page in _orig(res)]
    from mineru.kit.main import main
    sys.exit(main())
'''


def run(pdf_path, out_dir, pages=None, python=None):
    """Run MinerU (light unless the MFR model is installed) and return the structured_content.json path."""
    python = python or available()
    if not python:
        sys.exit("MinerU is not installed in any known interpreter; use --engine pdfplumber or set MINERU_PYTHON")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = out_dir / "_mineru_runner.py"
    runner.write_text(LIGHT_RUNNER, encoding="utf-8")
    mode = "--with-mfr" if MFR_DIR.exists() else "--light"
    cmd = [python, str(runner), mode, "parse", str(pdf_path), "-o", str(out_dir), "-f", "zip", "--tier", "basic"]
    if pages:
        cmd += ["-p", pages]
    print(f"MinerU: {'with formula model' if mode == '--with-mfr' else 'light, display formulas as crops'} …", file=sys.stderr, flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("MinerU failed:\n" + res.stderr[-2000:])
    zips = sorted(out_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        sys.exit("MinerU produced no zip output")
    with zipfile.ZipFile(zips[-1]) as z:
        z.extractall(out_dir / "mineru")
    return out_dir / "mineru" / "structured_content.json"


def convert(sc, source_name, source_path):
    """MinerU structured_content.json -> the skill's paragraphs.json dict."""
    blocks, labels, n_refs, headers = [], [], 0, Counter()
    for pg in sc["pages"]:
        page = pg["page_idx"] + 1
        pblocks = pg["blocks"]
        for k, b in enumerate(pblocks):
            t, c = b["type"], b.get("content")
            text = clean(c) if isinstance(c, str) else ""
            base = {"page": page, "bbox": b.get("bbox")}
            if t == "page_number":
                m = re.match(r"^\s*(\d{1,4})", text)
                if m:
                    labels.append((page, m.group(1)))
            elif t == "header":
                if text:
                    headers[re.sub(r"\d+", "", text).strip()] += 1
            elif t == "footer":
                continue
            elif t == "doc_title" and _is_masthead(pblocks, k):
                blocks.append(dict(base, type="frag", text=text, masthead=True))
            elif t == "text" and re.match(r"^\(\d{1,3}[a-z]?\)$", text):  # an equation label on its own line
                blocks.append(dict(base, type="frag", text=text))
            elif t == "text" and _is_footnote_block(pblocks, k, text):
                blocks.append(dict(base, type="note", text=text))
            elif t == "text" and text and _continues_without_flag(blocks, text, page):
                a = next(x for x in reversed(blocks) if x["type"] == "para")
                a["text"] = join_text(a["text"], text)
                a.setdefault("pages", {a["page"]}).add(page)
            elif t == "ref_text":
                n_refs += 1
            elif t in ("doc_title", "paragraph_title"):
                lvl = 0 if t == "doc_title" else max(1, int(b.get("level") or 2) - 1)
                m = NUM_HEAD_RE.match(text)
                if m and re.match(r"^\d", text):
                    lvl = min(4, m.group(1).count(".") + 1)
                blocks.append(dict(base, type="heading", text=text, level=lvl))
            elif t in ("text", "list", "index", "code", "algorithm_body"):
                if not text:
                    continue
                if b.get("continues_prev") and blocks:
                    j = len(blocks) - 1
                    while j >= 0 and blocks[j]["type"] != "para":
                        j -= 1
                    if j >= 0:
                        a = blocks[j]
                        a["text"] = join_text(a["text"], text)
                        a.setdefault("pages", {a["page"]}).add(page)
                        continue
                blocks.append(dict(base, type="para", text=text))
            elif t == "aside_text":
                blocks.append(dict(base, type="frag", text=text))
            elif t == "page_footnote":
                # Scans yield footnote blocks that are empty or hold a stray symbol ("μ(·)"); a note has words.
                if text and (re.search(r"[A-Za-z]{3,}", text) or re.search(r"[\u4e00-\u9fff]", text)):
                    blocks.append(dict(base, type="note", text=text))
            elif t == "equation":
                blocks.append(dict(base, type="frag", text=text or "[equation]", tex=text or None, equation=True))
            elif t in ("image", "table", "chart"):
                caps = " ".join(clean(x.get("content")) for x in b.get("captions") or [])
                fns = " ".join(clean(x.get("content")) for x in b.get("footnotes") or [])
                if caps:
                    blocks.append(dict(base, type="caption", text=caps, kind=t))
                if t == "table":
                    blocks.append(dict(base, type="frag", text=(text or "")[:200], table=True, html=text))
                if fns:
                    blocks.append(dict(base, type="note", text=fns, figure_note=True))
            else:
                blocks.append(dict(base, type="frag", text=text))
    _sidebar_rule(blocks)
    _front_matter_rule(blocks)
    items = _number(blocks)
    pnos = [pg["page_idx"] + 1 for pg in sc["pages"]]
    page_labels = _labels(labels, pnos)
    title = next((i["text"] for i in items if i["type"] == "heading" and i.get("level") == 0), "")
    if not title:  # alternating running heads: the one that is not the journal name is the article title
        banner = next((b["text"] for b in blocks if b["type"] == "frag" and b.get("masthead")), "")
        for h, _ in headers.most_common():
            if len(h.split()) >= 2 and not (banner and (h.casefold() in banner.casefold() or banner.casefold() in h.casefold())):
                title = h
                break
    layout = sc.get("extensions", {}).get("docvortex_layout", {}).get("pages")
    return {"version": 2, "source": source_name, "source_path": source_path,
            "mode": "MinerU " + sc.get("extensions", {}).get("mineru", {}).get("tier", ""),
            "page_count": len(layout) if layout else len(pnos),
            "pages_processed": [pnos[0], pnos[-1]] if pnos else None, "page_labels": page_labels,
            "title_guess": title, "items": items, "refs_excluded": n_refs}


def _is_masthead(pblocks, k):
    """A doc_title at the top of a page followed by a volume/issue line is the journal masthead, not the title."""
    b = pblocks[k]
    nxt = next((x for x in pblocks[k + 1:] if x["type"] not in ("page_number", "header")), None)
    return (b.get("bbox") or [0, 1])[1] < 0.1 and nxt is not None and bool(MASTHEAD_LINE_RE.search(clean(nxt.get("content") or "")))


def _is_footnote_block(pblocks, k, text):
    """'2. Despite ...' as the last text block at the foot of a page is a footnote MinerU labelled text."""
    if not FOOTNOTE_START_RE.match(text) or (pblocks[k].get("bbox") or [0, 0])[1] < 0.7:
        return False
    return not any(x["type"] in ("text", "paragraph_title", "equation", "table", "image") for x in pblocks[k + 1:])


def _continues_without_flag(blocks, text, page):
    """First text block of a page that starts in lower case continues the previous page's open paragraph."""
    if not text[:1].islower():
        return False
    if any(b["page"] == page and b["type"] in ("para", "heading") for b in blocks):
        return False
    prev = next((b for b in reversed(blocks) if b["type"] in ("para", "heading", "caption")), None)
    return prev is not None and prev["type"] == "para" and not re.search(r"[.!?。！？:]['\"’”)]*$", prev["text"])


def _sidebar_rule(blocks):
    """A narrow left column of short text blocks beside a wide main column is publisher metadata, not prose."""
    by_page = defaultdict(list)
    for b in blocks:
        if b["type"] == "para" and b.get("bbox"):
            by_page[b["page"]].append(b)
    for bs in by_page.values():
        main = [b for b in bs if b["bbox"][2] - b["bbox"][0] > 0.45]
        if len(main) < 2:
            continue
        main_x0 = sorted(b["bbox"][0] for b in main)[len(main) // 2]
        side = [b for b in bs if b["bbox"][2] < main_x0 + 0.01 and b["bbox"][2] - b["bbox"][0] < 0.35]
        if len(side) >= 2:
            for b in side:
                b["type"] = "frag"


def _front_matter_rule(blocks):
    """On the title page, short text blocks above the first section heading (byline, affiliations) are not prose."""
    first = min((b["page"] for b in blocks), default=None)
    if first is None:
        return
    title_i = next((k for k, b in enumerate(blocks) if b["type"] == "heading" and b.get("level") == 0), None)
    head_i = next((k for k, b in enumerate(blocks) if b["type"] == "heading" and b.get("level", 1) >= 1
                   and b["page"] == first and (title_i is None or k > title_i)), None)
    for b in blocks[:head_i if head_i is not None else len(blocks)]:
        if b["type"] == "para" and b["page"] == first and len(b["text"]) < 300:
            b["type"] = "frag"


def _number(blocks):
    counters, items = Counter(), []
    prefix = {"para": "P", "heading": "H", "caption": "C", "note": "N", "frag": "F"}
    for b in blocks:
        k = prefix[b["type"]]
        counters[k] += 1
        it = {"id": f"{k}{counters[k]}", "type": b["type"], "text": b["text"], "page": b["page"]}
        for f in ("level", "table", "tex", "html", "kind", "equation", "bbox"):
            if b.get(f) is not None:
                it[f] = b[f]
        pages = sorted(b.get("pages", {b["page"]}))
        if len(pages) > 1:
            it["pages"] = pages
        items.append(it)
    return link_notes(items)


def _labels(pairs, pnos):
    digits = [(p, int(l)) for p, l in pairs]
    if len(digits) >= 2:
        off, cnt = Counter(l - p for p, l in digits).most_common(1)[0]
        if cnt >= max(2, 0.6 * len(digits)):
            return {str(p): str(p + off) for p in pnos if p + off > 0}
    return {str(p): l for p, l in pairs}


def main():
    ap = argparse.ArgumentParser(description="Run MinerU for segment.py")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    r = sub.add_parser("run")
    r.add_argument("pdf")
    r.add_argument("--out", required=True)
    r.add_argument("--pages")
    r.add_argument("--python")
    a = ap.parse_args()
    print(run(a.pdf, a.out, a.pages, a.python))


if __name__ == "__main__":
    main()
