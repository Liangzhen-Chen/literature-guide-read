#!/usr/bin/env python3
"""Page overlays and explicit, replayable segmentation corrections.

Fixes are a JSON array (or {"ops": [...]}); IDs always name original items.
After a split the original ID addresses the first piece; joined IDs address
the merged item. New tails get the next unused #2, #3 suffix for that base ID.
The log maps original IDs to surviving pieces and tail names to their items.
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
    crop = dict(table="table", figure="figure", display="equation").get(op["to"])
    if op["to"] not in ("para", "heading", "caption", "note") and not crop:
        raise ValueError("region target must be para, heading, caption, note, table, figure or display")
    if "level" in op and (op["to"] != "heading" or type(op["level"]) is not int or op["level"] < 0):
        raise ValueError("level must be a nonnegative heading level")
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
        if not words and not crop:
            raise ValueError("region box contains no words")
        text = ""
        for line in segment.make_lines(words):
            text = segment.join_marked(text, line["text"])
    item = dict(type="frag" if crop else op["to"], text=text, page=n, bbox=list(box))
    if crop:
        item.update(region_crop=True, **{crop: True})
    if item["type"] == "heading":
        item["level"] = op.get("level", 1)
    return item


def overlay(paras, pages=None, out=None, orig=False):
    backup = paras.with_name("paragraphs.orig.json")
    drawn = backup if orig and backup.exists() else paras
    numbering = "original" if drawn == backup else "current"
    doc = json.loads(drawn.read_text(encoding="utf-8"))
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
                label = it["id"] + (f" L{it['level']}" if it["type"] == "heading" and "level" in it else "")
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
            print(f"{target} ({numbering} numbering)")
    return written


def corrected(original, ops, messages=None, current=None):
    messages = messages if messages is not None else []
    current, texts = current or {}, {it["id"]: it["text"] for it in original["items"]}
    doc = deepcopy(original)
    items = doc["items"]
    for it in items:
        it["_orig"] = [it["id"]]
        it["_keys"] = [it["id"]]
        it["_crops"] = [original.get("crops", {}).get(it["id"])]
    known = {it["id"] for it in items}
    n_regions, region_ends, noted = 0, {}, set()

    def find(key):
        if key not in known:
            raise ValueError(f"unknown id {key!r}")
        return next(it for it in items if key in it["_keys"])

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
                    if op["to"] == "frag":
                        it["_crops"] = []  # explicit hiding also hides a replaced partial crop
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
                    head["_orig"] = list(dict.fromkeys(head["_orig"] + other["_orig"]))
                    head["_keys"] += other["_keys"]
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
                root, suffix = op["id"].split("#", 1)[0], 2
                while f"{root}#{suffix}" in known:
                    suffix += 1
                key = f"{root}#{suffix}"
                known.add(key)
                tail["_orig"] = [name for name in it["_orig"] if "#" not in name] + [key]
                tail["_keys"] = [key]
                it["text"], tail["text"] = it["text"][:pos].rstrip(), it["text"][pos:]
                texts[key] = tail["text"]
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
                it.update(id=key, _orig=[key], _keys=[key], _crops=[])
                if it.get("region_crop"):
                    it["_crops"] = [{k: deepcopy(v) for k, v in it.items() if not k.startswith("_")}]
                texts[key] = it["text"]
                anchor = (op["page"], op["after"])
                previous_region = next((old for old in items if region_ends.get(anchor) in old["_keys"]), None)
                pos = items.index(previous_region)+1 if previous_region is not None else items.index(after)+1 if after is not None else next(
                    (i for i, old in enumerate(items) if old.get("page") == it["page"]), next(
                        (i for i, old in enumerate(items) if old.get("page", 0) > it["page"]), len(items)))
                items.insert(pos, it)
                region_ends[anchor] = key
            elif kind == "move":
                it, after = find(op["id"]), find(op["after"])
                if it is after:
                    raise ValueError("cannot move an item after itself")
                items.remove(it)
                items.insert(items.index(after)+1, it)
            else:
                raise ValueError(f"unknown operation {kind!r}")
            refs = list(op["ids"]) if kind in ("type", "join") else [op["id"]] if kind == "split" else [op.get("id"), op.get("after")]
            if kind == "region": refs.append(key)
            refs = list(dict.fromkeys(ref for ref in refs if ref))
            short = lambda text: json.dumps(" ".join(text.split()[:8]), ensure_ascii=False)
            label = kind + (f"→{op['to']}" if kind in ("type", "region") else "")
            messages.append(f"op {index} {label}: " + "; ".join(f"{ref} {short(texts[ref])}" for ref in refs))
            for ref in refs:
                if ref in current and current[ref] != texts[ref] and ref not in noted:
                    messages.append(f"note: op {index} names original {ref} {short(texts[ref])}; the current files show that id on {short(current[ref])}")
                    noted.add(ref)
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            detail = f"missing required key {exc.args[0]!r}" if isinstance(exc, KeyError) else str(exc)
            raise ValueError(f"op {index} ({op!r}): {detail}") from exc
    counts, mapping = Counter(), {key: [] for key in sorted(known)}
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
    current = {it["id"]: it["text"] for it in json.loads(paras.read_text(encoding="utf-8"))["items"]} if backup.exists() else {}
    original, messages = json.loads(raw), []
    doc, mapping = corrected(original, ops, messages, current)
    # Validate all operations before writing anything, including the backup.
    from fix_crops import stage_crops, remove_stale
    log = paras.with_name("fixes_log.json")
    previous = json.loads(log.read_text(encoding="utf-8")).get("created_crops", []) if log.exists() else []
    with tempfile.TemporaryDirectory(prefix="fix-", dir=paras.parent) as tmp:
        stage = Path(tmp)
        created = stage_crops(doc, original, paras.parent, stage)
        # Source glyph coverage also carries item IDs.
        for it in doc["items"]:
            for source in it.get("unmapped_sources", []):
                for coverage in source.get("crop_coverage", []):
                    coverage["crop"] = mapping.get(coverage["crop"], [coverage["crop"]])[0]
        segment.write_outputs(doc, stage, 12000)
        (stage / "fixes_log.json").write_text(json.dumps(dict(id_map=mapping, ops=ops, created_crops=created), ensure_ascii=False, indent=2), encoding="utf-8")
        if not backup.exists():
            backup.write_bytes(raw)
        for old in paras.parent.glob("paragraphs_part*.txt"):
            old.unlink()
        for path in stage.rglob("*"):
            if path.is_file():
                dest = paras.parent / path.relative_to(stage)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
        remove_stale(paras.parent, previous, created, original)
    for message in messages: print(message)
    print("Counts: " + ", ".join(f"{key}={n}" for key, n in sorted(Counter(it["type"] for it in doc["items"]).items())))
    return doc


def ids(paras, pages=None):
    doc, log = json.loads(paras.read_text(encoding="utf-8")), paras.with_name("fixes_log.json")
    mapping = json.loads(log.read_text(encoding="utf-8")).get("id_map", {}) if log.exists() else {}
    originals = {}
    for old, new_ids in mapping.items():
        for key in new_ids: originals.setdefault(key, []).append(old)
    selected = segment.parse_pages(pages, doc.get("page_count") or max((it.get("page",1) for it in doc["items"]), default=1)) if pages else None
    print("new id | original id(s) | type | page | first 8 words")
    for it in doc["items"]:
        if selected is None or set(it.get("pages", [it.get("page")])) & set(selected):
            print(f"{it['id']} | {', '.join(originals.get(it['id'], [it['id']]))} | {it['type']} | {it.get('page', '')} | {' '.join(it['text'].split()[:8])}")


def main():
    segment.use_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    ov = sub.add_parser("overlay")
    ov.add_argument("paragraphs", type=Path)
    ov.add_argument("--pages")
    ov.add_argument("--out", type=Path)
    ov.add_argument("--orig", action="store_true", help="draw first-segmentation IDs from paragraphs.orig.json when available")
    fx = sub.add_parser("apply"); fx.add_argument("fixes", type=Path)
    fx.add_argument("--paras", required=True, type=Path)
    ls = sub.add_parser("ids"); ls.add_argument("paragraphs", type=Path); ls.add_argument("--pages")
    args = ap.parse_args()
    try:
        if args.command == "overlay":
            overlay(args.paragraphs, args.pages, args.out, args.orig)
        elif args.command == "ids": ids(args.paragraphs, args.pages)
        else:
            apply(args.fixes, args.paras)
    except (ValueError, OSError, KeyError) as exc:
        ap.exit(1, f"fix.py: {exc}\n")


if __name__ == "__main__":
    main()
