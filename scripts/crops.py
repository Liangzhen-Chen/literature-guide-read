#!/usr/bin/env python3
"""Crop formula and table regions out of the PDF so the page can show the typeset original next to the notes."""
from pathlib import Path


def merge_table_runs(items):
    """Consecutive table rows on one page become one region on the first row; followers get table_part."""
    prev = None
    for it in items:
        if it.get("table") and it.get("bbox"):
            if prev is not None and prev["page"] == it["page"]:
                b, c = prev["bbox"], it["bbox"]
                prev["bbox"] = [min(b[0], c[0]), min(b[1], c[1]), max(b[2], c[2]), max(b[3], c[3])]
                it["table_part"] = True
            else:
                prev = it
        elif it["type"] != "frag":
            prev = None
    return items


def _short_math_part(it):
    """A fragment with at most three tokens next to an equation: a numerator, a denominator, a limit, a label."""
    return it["type"] == "frag" and it.get("bbox") and not it.get("table") and not it.get("equation") and len(it["text"].split()) <= 3


def merge_equation_runs(items):
    """A display equation set over several lines (fraction parts, the equation, its number) is one region:
    consecutive equation fragments on one page, plus the short fragments touching them."""
    n = len(items)
    i = 0
    while i < n:
        it = items[i]
        if not (it.get("equation") and it.get("bbox") and not it.get("table")):
            i += 1
            continue
        start = i
        while start > 0 and _short_math_part(items[start - 1]) and items[start - 1]["page"] == it["page"] and not items[start - 1].get("eq_part"):
            start -= 1
        end = i
        while end + 1 < n and items[end + 1]["page"] == it["page"] and (
                (items[end + 1].get("equation") and items[end + 1].get("bbox") and not items[end + 1].get("table"))
                or _short_math_part(items[end + 1])):
            end += 1
        head = items[start]
        box = list(head["bbox"])
        for k in range(start + 1, end + 1):
            c = items[k]["bbox"]
            box = [min(box[0], c[0]), min(box[1], c[1]), max(box[2], c[2]), max(box[3], c[3])]
            items[k]["eq_part"] = True
        head["bbox"] = box
        head["equation"] = True
        i = end + 1
    return items


def wants_crop(it):
    if not it.get("bbox") or it.get("table_part") or it.get("eq_part"):
        return False
    return bool(it.get("equation") or it.get("table") or it.get("has_math"))


def crop_regions(pdf_path, items, out_dir, resolution=150, pad=0.006):
    """Write out_dir/<id>.png for every equation, table and math paragraph with a bbox. Returns {id: path}."""
    out_dir = Path(out_dir)
    merge_table_runs(items)
    merge_equation_runs(items)
    for it in items:  # a display equation sits alone on its line; its text box often misses glyphs, so take the column
        if it.get("equation") and it.get("bbox"):
            b = it["bbox"]
            it["bbox"] = [min(b[0], 0.08), b[1], max(b[2], 0.92), b[3]]
    todo = [it for it in items if wants_crop(it)]
    if not todo or not pdf_path or not Path(pdf_path).exists():
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        for it in todo:
            if not 1 <= it["page"] <= len(pdf.pages):
                continue
            page = pdf.pages[it["page"] - 1]
            w, h = float(page.width), float(page.height)
            x0, top, x1, bottom = it["bbox"]
            box = (max(0, (x0 - pad) * w), max(0, (top - pad) * h), min(w, (x1 + pad) * w), min(h, (bottom + pad) * h))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            try:
                # relative: offsets from the page's own top-left, so a MediaBox that does not start at
                # the origin (JSTOR scans) still crops the right region
                img = page.crop(box, relative=True).to_image(resolution=resolution).original.convert("RGB")
            except Exception as e:  # a damaged page must not stop the run
                print(f"crop skipped for {it['id']}: {e}")
                continue
            path = out_dir / f"{it['id']}.png"
            img.save(path, "PNG", optimize=True)
            written[it["id"]] = str(path)
    return written
