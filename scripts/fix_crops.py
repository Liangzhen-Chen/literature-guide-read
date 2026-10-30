"""Stage crops under current IDs, preserving original bytes for fixes replay."""
from pathlib import Path
import shutil


def stage_crops(doc, original, work, stage):
    from PIL import Image
    originals = set(original.get("crops", {}).values())
    saved = {}
    for rel in originals:
        archive = Path("crops.orig") / rel
        source = work / archive if (work / archive).exists() else work / rel
        saved[rel] = source
        if not (work / archive).exists():
            (stage / archive).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, stage / archive)
    crops = {}
    for it in doc["items"]:
        paths = list(dict.fromkeys(p for p in it.pop("_crops") if p))
        it.pop("_orig"); it.pop("_keys")
        if not paths:
            continue
        rel = f"crops/{it['id']}.png"
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if len(paths) == 1:
            shutil.copyfile(saved[paths[0]], target)
        else:
            images = []
            for p in paths:
                with Image.open(saved[p]) as image:
                    images.append(image.convert("RGB"))
            canvas = Image.new("RGB", (max(im.width for im in images), sum(im.height for im in images)), "white")
            y = 0
            for image in images:
                canvas.paste(image, (0, y)); y += image.height
            canvas.save(target)
        crops[it["id"]] = rel
    # Restore original root names when they are no longer used by current items.
    # Colliding names are safe: their original bytes are archived before install.
    for rel in originals - set(crops.values()):
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(saved[rel], stage / rel)
    if "crops" in doc or crops:
        doc["crops"] = crops
    return sorted(crops.values())


def remove_stale(work, previous, current, original):
    for rel in set(previous) - set(current) - set(original.get("crops", {}).values()):
        path = (work / rel).resolve()
        # Only files explicitly recorded as apply outputs inside crops/ qualify.
        if path.parent == (work / "crops").resolve() and path.suffix == ".png":
            path.unlink(missing_ok=True)
