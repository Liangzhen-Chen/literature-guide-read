#!/usr/bin/env python3
"""Page overlays and explicit, replayable segmentation corrections.

Fixes are a JSON array (or {"ops": [...]}); IDs always name original items.
After a split the original ID addresses the first piece; joined IDs address
the merged item. The log maps each original ID to all surviving pieces.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import tempfile

import segment

PREFIX = dict(para="P", heading="H", caption="C", note="N", frag="F")
COLORS = dict(para="#1671bc", heading="#be2424", caption="#148345",
              note="#9b42b1", frag="#777777", ref="#777777")
REQUIRED = dict(type=("ids", "to"), join=("ids",), split=("id", "at"),
                move=("id", "after"), region=("page", "bbox", "to", "after"))


def region(doc, op):
    source, n, box = doc.get("source_path"), op["page"], op["bbox"]
    if op["to"] not in ("para", "heading", "caption", "note"):
        raise ValueError("region target must be para, heading, caption or note")
    if (not isinstance(box, list) or len(box) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in box)
            or box[0] >= box[2] or box[1] >= box[3]):
        raise ValueError("region bbox must be a nondegenerate normalized box")
    if not source or not Path(source).is_file() or Path(source).suffix.lower() != ".pdf":
        raise ValueError("region requires source_path pointing to a readable PDF")
    import pdfplumber
    try:
        pdf = pdfplumber.open(source)
    except Exception as exc:
        raise ValueError(f"region requires a readable PDF: {exc}") from exc
    with pdf:
        if type(n) is not int or not 1 <= n <= len(pdf.pages):
            raise ValueError("region page outside the document")
        page = pdf.pages[n-1]
        words = [w for w in segment.get_words(page)
                 if box[0] <= (w["x0"]+w["x1"])/2/page.width <= box[2]
                 and box[1] <= (w["top"]+w["bottom"])/2/page.height <= box[3]]
        if not words:
            raise ValueError("region box contains no words")
        text = ""
        for line in segment.make_lines(words):
            text = segment.join_marked(text, line["text"])
    item = dict(type=op["to"], text=text, page=n, bbox=list(box))
    if item["type"] == "heading":
        item["level"] = 1
    return item


def overlay(paras, pages=None, out=None):
    doc = json.loads(paras.read_text(encoding="utf-8"))
    items = doc["items"]
    processed = doc.get("pages_processed")
    selected = segment.parse_pages(pages, doc.get("page_count", 1)) if pages else (
        list(range(processed[0], processed[-1]+1)) if processed else sorted(
            {it.get("page") for it in items if it.get("page")}))
    source = doc.get("source_path")
    if not source or not Path(source).is_file() or Path(source).suffix.lower() != ".pdf":
        print("No PDF/bboxes available for page overlays.")
        return []
    import pdfplumber
    from PIL import ImageDraw
    written = []
    with pdfplumber.open(source) as pdf:
        for n in selected:
            boxed = [it for it in items if it.get("page") == n and it.get("bbox")]
            if not boxed or not 1 <= n <= len(pdf.pages):
                print(f"p{n:03d}: no bboxes available.")
                continue
            page = pdf.pages[n - 1]
            dpi = min(100, 1100 * 72 / max(page.width, page.height))
            img = page.to_image(resolution=dpi).original.convert("RGB")
            img.thumbnail((1100, 1100))
            draw = ImageDraw.Draw(img)
            for tick in range(1, 10):
                x, y = img.width*tick/10, img.height*tick/10
                draw.line((x, 0, x, img.height), fill="#dddddd")
                draw.line((0, y, img.width, y), fill="#dddddd")
                draw.text((x+2, 1), f"0.{tick}", fill="#777777")
                draw.text((1, y+2), f"0.{tick}", fill="#777777")
            for it in boxed:
                b = it["bbox"]
                box = (b[0]*img.width, b[1]*img.height, b[2]*img.width, b[3]*img.height)
                color = COLORS.get(it["type"], "#777777")
                draw.rectangle(box, outline=color, width=2)
                x, y = box[:2]
                label = it["id"]
                if x >= len(label)*7 + 5:
                    x -= len(label)*7 + 5
                else:
                    y = max(0, y - 12)
                draw.rectangle((x, y, x + len(label)*7 + 3, y + 12), fill="white")
                draw.text((x+1, y), label, fill=color)
            target = (out or paras.parent / "pages") / f"p{n:03d}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target)
            written.append(target)
            print(target)
    return written


def corrected(original, ops):
    doc = deepcopy(original)
    items = doc["items"]
    for it in items:
        it["_orig"] = [it["id"]]
        it["_crops"] = [original.get("crops", {}).get(it["id"])]
    known = {it["id"] for it in items}
    n_regions = 0

    def find(key):
        if key not in known:
            raise ValueError(f"unknown id {key!r}")
        return next(it for it in items if key in it["_orig"])

    for index, op in enumerate(ops, 1):
        try:
            kind = op["op"]
            for key in (*REQUIRED.get(kind, ()), "why"):
                if key not in op:
                    raise KeyError(key)
            if not isinstance(op.get("why"), str) or not op["why"].strip():
                raise ValueError("why is required")
            if kind in ("type", "join"):
                ids = op["ids"]
                if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
                    raise ValueError("ids must be a nonempty list of distinct original IDs")
                targets = [find(key) for key in ids]
                if len({id(it) for it in targets}) != len(targets):
                    raise ValueError("ids already refer to the same joined item")
            if kind == "type":
                if op["to"] not in PREFIX:
                    raise ValueError("invalid target type")
                if "level" in op and (op["to"] != "heading" or type(op["level"]) is not int or op["level"] < 0):
                    raise ValueError("level must be a nonnegative heading level")
                for it in targets:
                    it["type"] = op["to"]
                    it.pop("level", None)
                    if it["type"] == "heading":
                        it["level"] = op.get("level", 1)
            elif kind == "join":
                positions = [items.index(it) for it in targets]
                if len({it["type"] for it in targets}) != 1:
                    raise ValueError("join across types")
                if len(targets) < 2 or positions != sorted(positions):
                    raise ValueError("join needs at least two items in reading order")
                between = [it for it in items[positions[0]:positions[-1]+1] if it not in targets]
                if any(it["type"] == targets[0]["type"] or it["type"] not in ("note", "frag", "caption") for it in between):
                    raise ValueError("join needs consecutive items of its type; only notes, frags or captions may intervene")
                head = targets[0]
                for other in targets[1:]:
                    head["text"] = segment.join_marked(head["text"], other["text"])
                    head["_orig"] += other["_orig"]
                    head["_crops"] += other["_crops"]
                    pages = sorted(set(head.get("pages", [head["page"]]) + other.get("pages", [other["page"]])))
                    if len(pages) > 1:
                        head["pages"] = pages
                    elif head.get("bbox") and other.get("bbox"):
                        a, b = head["bbox"], other["bbox"]
                        head["bbox"] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    items.remove(other)
            elif kind == "split":
                it = find(op["id"])
                at = op["at"]
                if not isinstance(at, str) or not at or it["text"].find(at) < 0 or it["text"].find(at, it["text"].find(at)+1) >= 0:
                    raise ValueError("split 'at' must occur exactly once")
                pos = it["text"].index(at)
                if not it["text"][:pos].strip():
                    raise ValueError("split would leave an empty first item")
                tail = deepcopy(it)
                it["text"], tail["text"] = it["text"][:pos].rstrip(), it["text"][pos:]
                tail.pop("num", None)
                items.insert(items.index(it)+1, tail)
            elif kind == "region":
                it = region(doc, op)
                after = find(op["after"]) if op["after"] is not None else None
                if after is not None and after["page"] != op["page"]:
                    raise ValueError("region after must be on the same page")
                n_regions += 1
                key = f"region{n_regions}"
                known.add(key)
                it.update(id=key, _orig=[key], _crops=[])
                pos = items.index(after)+1 if after is not None else next(
                    (i for i, old in enumerate(items) if old.get("page") == it["page"]), next(
                        (i for i, old in enumerate(items) if old.get("page", 0) > it["page"]), len(items)))
                items.insert(pos, it)
            elif kind == "move":
                it, after = find(op["id"]), find(op["after"])
                if it is after:
                    raise ValueError("cannot move an item after itself")
                items.remove(it)
                items.insert(items.index(after)+1, it)
            else:
                raise ValueError(f"unknown operation {kind!r}")
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            detail = f"missing required key {exc.args[0]!r}" if isinstance(exc, KeyError) else str(exc)
            raise ValueError(f"op {index} ({op!r}): {detail}") from exc
    counts, mapping = Counter(), {key: [] for key in known}
    for it in items:
        prefix = PREFIX.get(it["type"], "F")
        counts[prefix] += 1
        it["id"] = f"{prefix}{counts[prefix]}"
        for key in it["_orig"]:
            mapping[key].append(it["id"])
        it.pop("ref", None)
        it.pop("notes", None)
        if it["type"] == "note" and it.get("num"):
            it["text"] = f"{it['num']} " + it["text"]
        elif it["type"] != "note":
            it.pop("num", None)
    segment.link_notes(items)
    # Original geometric note marks have already been consumed by segmentation.
    # Preserve proven links when the text-only linker cannot reconstruct them.
    by_id = {it["id"]: it for it in items}
    for old in original["items"]:
        if old.get("ref") in mapping:
            for nid in mapping[old["id"]]:
                note = by_id[nid]
                hosts = [by_id[key] for key in mapping[old["ref"]] if by_id[key]["type"] == "para"]
                if note["type"] == "note" and not note.get("ref") and hosts:
                    host = hosts[0]
                    note["ref"] = host["id"]
                    if nid not in host.setdefault("notes", []):
                        host["notes"].append(nid)
    titles = [it["text"] for it in items if it["type"] == "heading" and it.get("level") == 0]
    if titles:
        doc["title_guess"] = titles[0]
    return doc, mapping


def apply(fixes, paras):
    backup = paras.with_name("paragraphs.orig.json")
    raw = (backup if backup.exists() else paras).read_bytes()
    ops = json.loads(fixes.read_text(encoding="utf-8"))
    if isinstance(ops, dict):
        ops = ops.get("ops")
    if not isinstance(ops, list):
        raise ValueError("fixes must be an array or an object with an ops array")
    doc, mapping = corrected(json.loads(raw), ops)
    # Validate all operations before writing anything, including the backup.
    from PIL import Image
    with tempfile.TemporaryDirectory(prefix="fix-", dir=paras.parent) as tmp:
        stage = Path(tmp)
        crops = {}
        for it in doc["items"]:
            paths = list(dict.fromkeys(path for path in it.pop("_crops") if path))
            it.pop("_orig")
            if len(paths) == 1:
                crops[it["id"]] = paths[0]
            elif paths:
                images = []
                for path in paths:
                    with Image.open(paras.parent / path) as image:
                        images.append(image.convert("RGB"))
                canvas = Image.new("RGB", (max(im.width for im in images), sum(im.height for im in images)), "white")
                y = 0
                for image in images:
                    canvas.paste(image, (0, y))
                    y += image.height
                rel = f"crops/fixed_{it['id']}.png"
                (stage / "crops").mkdir(exist_ok=True)
                canvas.save(stage / rel)
                crops[it["id"]] = rel
        if "crops" in doc or crops:
            doc["crops"] = crops
        # Source glyph coverage also carries item IDs.
        for it in doc["items"]:
            for source in it.get("unmapped_sources", []):
                for coverage in source.get("crop_coverage", []):
                    coverage["crop"] = mapping.get(coverage["crop"], [coverage["crop"]])[0]
        segment.write_outputs(doc, stage, 12000)
        (stage / "fixes_log.json").write_text(json.dumps(dict(id_map=mapping, ops=ops), ensure_ascii=False, indent=2), encoding="utf-8")
        if not backup.exists():
            backup.write_bytes(raw)
        for old in paras.parent.glob("paragraphs_part*.txt"):
            old.unlink()
        for path in stage.rglob("*"):
            if path.is_file():
                dest = paras.parent / path.relative_to(stage)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    print("Counts: " + ", ".join(f"{key}={n}" for key, n in sorted(Counter(it["type"] for it in doc["items"]).items())))
    return doc


def main():
    segment.use_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    ov = sub.add_parser("overlay")
    ov.add_argument("paragraphs", type=Path)
    ov.add_argument("--pages")
    ov.add_argument("--out", type=Path)
    fx = sub.add_parser("apply")
    fx.add_argument("fixes", type=Path)
    fx.add_argument("--paras", required=True, type=Path)
    args = ap.parse_args()
    try:
        if args.command == "overlay":
            overlay(args.paragraphs, args.pages, args.out)
        else:
            apply(args.fixes, args.paras)
    except (ValueError, OSError, KeyError) as exc:
        ap.exit(1, f"fix.py: {exc}\n")


if __name__ == "__main__":
    main()
