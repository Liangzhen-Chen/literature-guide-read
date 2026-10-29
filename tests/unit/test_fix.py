import json
import os

import pytest
from PIL import Image

import check
import fix


@pytest.fixture
def work(tmp_path, sample_pdf):
    doc = dict(source="synthetic", source_path=str(sample_pdf), page_count=3,
               items=[dict(id=f"P{i}", type="para", page=1, text=text,
                           bbox=[.1, .1*i, .8, .1*i+.08])
                      for i, text in enumerate(["An intro.", "inter-", "national Second sentence.", "Body.1"], 1)])
    doc["items"].append(dict(id="N1", type="note", page=1, text="A note.", num=1, ref="P4"))
    doc["items"][-2]["notes"] = ["N1"]
    path = tmp_path / "paragraphs.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def run(work, ops):
    path = work.with_name("fixes.json")
    path.write_text(json.dumps(ops), encoding="utf-8")
    return fix.apply(path, work)


def test_type_and_replay(work):
    raw = work.read_bytes()
    ops = [dict(op="type", ids=["P1"], to="heading", level=0, why="title")]
    doc = run(work, ops)
    assert doc["items"][0]["id"] == "H1"
    assert doc["title_guess"] == "An intro."
    assert work.with_name("paragraphs.orig.json").read_bytes() == raw
    first = work.read_bytes()
    run(work, ops)
    assert work.read_bytes() == first
    doc = run(work, [dict(op="type", ids=["P1"], to="frag", why="metadata")])
    assert doc["items"][0]["id"] == "F1"
    assert doc["items"][1]["text"] == "inter-"
    assert (work.parent / "paragraphs_part01.txt").exists()


def test_join_split_move_original_ids(work):
    doc = run(work, [dict(op="join", ids=["P2", "P3"], why="false split"),
                     dict(op="split", id="P3", at="Second sentence.", why="false join"),
                     dict(op="move", id="N1", after="P1", why="reading order")])
    assert [it["text"] for it in doc["items"]][:4] == ["An intro.", "A note.", "international", "Second sentence."]
    mapping = json.loads(work.with_name("fixes_log.json").read_text())["id_map"]
    assert mapping["P2"] == mapping["P3"] == ["P2", "P3"]


@pytest.mark.parametrize("op", [
    dict(op="type", ids=["P99"], to="para"),
    dict(op="type", ids=["P1"], to="guess"),
    dict(op="join", ids=["P1", "P3"]),
    dict(op="join", ids=["P4", "N1"]),
    dict(op="split", id="P1", at="absent"),
    dict(op="split", id="P1", at="n"),
    dict(op="split", id="P1", at="An"),
    dict(op="move", id="P1", after="P1"),
])
def test_invalid_no_writes(work, op):
    before = {p.name: p.read_bytes() for p in work.parent.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="op 2"):
        run(work, [dict(op="type", ids=["P1"], to="heading", why="valid first"), dict(op, why="bad")])
    after = {p.name: p.read_bytes() for p in work.parent.iterdir() if p.is_file() and p.name != "fixes.json"}
    assert after == before


def test_missing_reason(work):
    with pytest.raises(ValueError, match="why"):
        run(work, [dict(op="type", ids=["P1"], to="frag")])


def test_crops_and_footnotes_survive(work):
    doc = json.loads(work.read_text())
    (work.parent / "crops").mkdir()
    for key, color in [("P2", "red"), ("P3", "blue")]:
        Image.new("RGB", (10, 10), color).save(work.parent / "crops" / f"{key}.png")
    doc["crops"] = {key: f"crops/{key}.png" for key in ["P2", "P3"]}
    work.write_text(json.dumps(doc))
    doc = run(work, [dict(op="type", ids=["P1"], to="heading", level=0, why="title"),
                     dict(op="join", ids=["P2", "P3"], why="join crops")])
    crop = Image.open(work.parent / doc["crops"]["P1"])
    assert crop.size == (10, 20)
    assert crop.getpixel((1, 1)) == (255, 0, 0)
    assert crop.getpixel((1, 11)) == (0, 0, 255)
    assert doc["items"][-1]["ref"] == "P2"
    assert doc["items"][-2]["notes"] == ["N1"]
    first = work.read_bytes()
    run(work, [dict(op="type", ids=["P1"], to="heading", level=0, why="title"),
               dict(op="join", ids=["P2", "P3"], why="join crops")])
    assert work.read_bytes() == first
    doc = run(work, [dict(op="type", ids=["P1"], to="caption", why="caption")])
    assert doc["crops"]["P1"] == "crops/P2.png"


def test_overlay(work, capsys):
    paths = fix.overlay(work, "1,2-3")
    assert [p.name for p in paths] == ["p001.png"]
    assert max(Image.open(paths[0]).size) <= 1100
    with Image.open(paths[0]) as image:
        assert image.getpixel((int(image.width*.9), image.height-10)) == (221, 221, 221)
    assert "p002: no bboxes" in capsys.readouterr().out
    doc = json.loads(work.read_text())
    for it in doc["items"]:
        it.pop("bbox", None)
    work.write_text(json.dumps(doc))
    assert fix.overlay(work) == []
    doc.pop("source_path")
    work.write_text(json.dumps(doc))
    assert fix.overlay(work) == []


def test_stale_fixes(work):
    assert check.stale_fixes(work) is None
    run(work, [])
    fixes = work.with_name("fixes.json")
    os.utime(fixes, ns=(work.stat().st_mtime_ns+1000000000,)*2)
    assert "edited but not applied" in check.stale_fixes(work)


def test_overlapping_split_rejected(work):
    doc = json.loads(work.read_text())
    doc["items"][0]["text"] = "x aaa end"
    work.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="exactly once"):
        run(work, [dict(op="split", id="P1", at="aa", why="ambiguous")])


def test_split_crop_and_geometric_note(work):
    doc = json.loads(work.read_text())
    doc["items"][-2]["text"] = "No baseline marker. Another sentence."
    doc["crops"] = {"P4": "crops/original.png"}
    (work.parent / "crops").mkdir()
    Image.new("RGB", (10, 10), "white").save(work.parent / "crops/original.png")
    work.write_text(json.dumps(doc))
    doc = run(work, [dict(op="split", id="P4", at="Another sentence.", why="false join")])
    assert doc["crops"] == {"P4": "crops/original.png", "P5": "crops/original.png"}
    assert doc["items"][-1]["ref"] == "P4"
    assert doc["items"][-3]["notes"] == ["N1"]


def region_op(**changes):
    return dict(dict(op="region", page=1, bbox=[.09, .1, .95, .17],
                     to="para", after="P1", why="extract a single PDF column"), **changes)


@pytest.mark.parametrize("mode", ["PDF text layer", "MinerU basic"])
def test_region_extract_replay_and_mapping(work, mode):
    original = json.loads(work.read_text())
    original["mode"] = mode
    work.write_text(json.dumps(original))
    ops = [region_op(), region_op(page=2, bbox=[.09, .1, .95, .12], after=None, to="caption")]
    doc = run(work, ops)
    it = doc["items"][1]
    assert it["text"] == ("The normal distribution has two parameters, the mean and the standard deviation. "
                          "If X is a quantity with a normal distribution we write X ~ N(mu, sigma). "
                          "The z-score counts standard deviations from the mean of the distribution.")
    assert it["bbox"] == ops[0]["bbox"] and it["page"] == 1
    assert doc["items"][-1]["page"] == 2
    assert doc["items"][-1]["type"] == "caption"
    log = json.loads(work.with_name("fixes_log.json").read_text())
    assert log["id_map"]["region1"] == ["P2"]
    assert log["id_map"]["region2"] == ["C1"]
    assert doc["items"][2]["text"] == original["items"][1]["text"]
    saved = {p.name: p.read_bytes() for p in work.parent.glob("*.json")}
    run(work, ops)
    assert {p.name: p.read_bytes() for p in work.parent.glob("*.json")} == saved


@pytest.mark.parametrize("changes, error", [
    ({"bbox": [.1, .1, .1, .2]}, "nondegenerate"),
    ({"bbox": [.2, .2, .1, .3]}, "nondegenerate"),
    ({"bbox": [-.1, 0, .2, .2]}, "normalized"),
    ({"bbox": [0, 0, .01, .01]}, "no words"),
    ({"page": 0}, "outside"),
    ({"page": 4}, "outside"),
    ({"page": 1.5}, "outside"),
    ({"after": "P99"}, "unknown id"),
    ({"page": 2}, "same page"),
    ({"to": "frag"}, "target"),
])
def test_invalid_region_no_writes(work, changes, error):
    before = work.read_bytes()
    with pytest.raises(ValueError, match=f"op 1.*{error}"):
        run(work, [region_op(**changes)])
    assert work.read_bytes() == before
    assert not work.with_name("paragraphs.orig.json").exists()
    assert not work.with_name("fixes_log.json").exists()


@pytest.mark.parametrize("source", [None, "missing.pdf", "bad.pdf"])
def test_region_requires_pdf(work, source):
    doc = json.loads(work.read_text())
    doc["source_path"] = str(work.parent/source) if source else None
    if source == "bad.pdf":
        (work.parent/source).write_text("not a PDF")
    work.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="op 1.*readable PDF"):
        run(work, [region_op()])


def test_region_page_start(work):
    doc = run(work, [region_op(after=None, to="heading")])
    assert doc["items"][0]["id"] == "H1"
    assert doc["items"][0]["level"] == 1
    assert doc["items"][1]["text"] == "An intro."


def test_region_page_start_after_reorder(work):
    doc = json.loads(work.read_text())
    doc["items"][0]["page"] = 2
    work.write_text(json.dumps(doc))
    doc = run(work, [region_op(after=None)])
    assert doc["items"][0]["page"] == 2
    assert doc["items"][1]["bbox"] == [.09, .1, .95, .17]
    assert doc["items"][2]["text"] == "inter-"
