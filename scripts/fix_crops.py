"""Stage crops under current IDs, preserving original bytes for fixes replay."""
from pathlib import Path, PureWindowsPath
import shutil
import tempfile


def posix(rel):
    return PureWindowsPath(rel).as_posix()


def stage_crops(doc, original, work, stage):
    # Region sources are temporary; only current-ID copies enter the output.
    with tempfile.TemporaryDirectory(prefix="regions-", dir=stage) as tmp:
        return _stage_crops(doc, original, work, stage, Path(tmp))


def _stage_crops(doc, original, work, stage, tmp):
    from PIL import Image
    from crops import crop_regions
    # The segmenter writes OS-native separators (crops\F3.png on Windows); compare names in one form.
    originals = {posix(rel) for rel in original.get("crops", {}).values()}
    saved, boxes = {}, {}
    for rel in originals:
        archive = Path("crops.orig") / rel
        source = work / archive if (work / archive).exists() else work / rel
        saved[rel] = source
        if not (work / archive).exists():
            (stage / archive).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, stage / archive)
    crops = {}
    for it in doc["items"]:
        paths = []
        for source in it.pop("_crops"):
            if isinstance(source, dict):
                key = source["id"]
                if key not in saved:
                    made = crop_regions(doc.get("source_path"), [source], tmp)
                    if key not in made:
                        raise ValueError(f"could not crop {key} from the source PDF")
                    saved[key] = Path(made[key])
                    boxes[key] = source["crop_bbox"]
                if it.get("region_crop"):
                    it["crop_bbox"] = boxes[key]
                paths.append(key)
            elif source:
                paths.append(posix(source))
        paths = list(dict.fromkeys(paths))
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
    if "crops" in doc or crops:
        doc["crops"] = crops
    return sorted(crops.values())


def remove_stale(work, previous, current, original):
    """After install, crops/ holds only current-ID crops: earlier apply outputs and
    segmenter crops under unused names go (the latter stay archived in crops.orig/)."""
    originals = {posix(r) for r in original.get("crops", {}).values()}
    for rel in ({posix(r) for r in previous} | originals) - {posix(r) for r in current}:
        path = (work / rel).resolve()
        if rel in originals and not (work / "crops.orig" / rel).exists():
            continue  # never delete a segmenter crop that has no archived copy
        if path.parent == (work / "crops").resolve() and path.suffix == ".png":
            path.unlink(missing_ok=True)
