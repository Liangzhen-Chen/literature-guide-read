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


@pytest.mark.parametrize("kind,required", [(None, ("op",)), *fix.REQUIRED.items()])
def test_missing_required_keys(work, kind, required):
    complete = dict(op=kind, ids=["P1", "P2"], to="para", id="P1", at="intro.",
                    after="P1", page=1, bbox=[.1, .1, .8, .2], why="synthetic correction")
    for key in (*required, "why"):
        op = {k: v for k, v in complete.items() if k != key}
        with pytest.raises(ValueError, match=f"op 2 .*missing required key '{key}'"):
            run(work, [dict(op="type", ids=["P1"], to="heading", why="valid first"), op])
        assert not work.with_name("paragraphs.orig.json").exists()
        assert not work.with_name("fixes_log.json").exists()


def test_join_across_notes_fragments_captions(work):
    doc = json.loads(work.read_text())
    inserts = [dict(id=key, type=kind, page=1, text=text) for key, kind, text in
               [("N2", "note", "First inset"), ("F1", "frag", "A fragment"),
                ("C1", "caption", "A caption"), ("N3", "note", "Second inset")]]
    doc["items"][2:2] = inserts
    work.write_text(json.dumps(doc))
    ops = [dict(op="join", ids=["P2", "P3"], why="paragraph interrupted by notes")]
    result = run(work, ops)
    assert result["items"][1]["text"] == "international Second sentence."
    assert [it["text"] for it in result["items"][2:6]] == [it["text"] for it in inserts]
    assert result["items"][6]["text"] == "Body.1"
    log = json.loads(work.with_name("fixes_log.json").read_text())
    assert log["id_map"]["P2"] == log["id_map"]["P3"] == ["P2"]
    first = work.read_bytes()
    run(work, ops)
    assert work.read_bytes() == first


@pytest.mark.parametrize("target_type,between_type", [
    ("para", "heading"), ("para", "para"), ("note", "para"), ("note", "note"),
    ("caption", "caption"), ("frag", "frag"),
])
def test_join_rejects_intervening_type(work, target_type, between_type):
    doc = json.loads(work.read_text())
    for it in doc["items"][:3]:
        it["type"] = target_type
    doc["items"][1]["type"] = between_type
    work.write_text(json.dumps(doc))
    before = work.read_bytes()
    with pytest.raises(ValueError, match="op 1.*consecutive items of its type"):
        run(work, [dict(op="join", ids=["P1", "P3"], why="invalid gap")])
    assert work.read_bytes() == before


def test_split_tail_names_accept_all_id_fields(work):
    doc = json.loads(work.read_text())
    doc["items"][2]["text"] = "First. Second. Third."
    work.write_text(json.dumps(doc))
    ops = [dict(op="split", id="P3", at="Second.", why="first split"),
           dict(op="split", id="P3#2", at="Third.", why="split the tail"),
           dict(op="type", ids=["P3#2"], to="caption", why="caption piece"),
           dict(op="move", id="P3#3", after="P1", why="move tail"),
           dict(op="type", ids=["P3"], to="heading", why="original head remains addressable"),
           dict(op="move", id="P2", after="P3#2", why="tail as anchor"),
           region_op(after="P3#3")]
    result = run(work, ops)
    items = {it["text"]: it for it in result["items"]}
    mapping = json.loads(work.with_name("fixes_log.json").read_text())["id_map"]
    assert mapping["P3#2"] == [items["Second."]["id"]]
    assert mapping["P3#3"] == [items["Third."]["id"]]
    assert set(mapping["P3"]) == {items[text]["id"] for text in ["First.", "Second.", "Third."]}
    assert items["Second."]["type"] == "caption"
    assert items["First."]["type"] == "heading"
    assert result["items"][1]["text"] == "Third."
    assert result["items"][2]["id"] == mapping["region1"][0]
    before = work.read_bytes()
    run(work, ops)
    assert work.read_bytes() == before


def test_join_tail_names_and_deduplicate_original_mapping(work):
    ops = [dict(op="split", id="P3", at="Second sentence.", why="split"),
           dict(op="join", ids=["P3", "P3#2"], why="join named pieces")]
    doc = run(work, ops)
    assert doc["items"][2]["text"] == "national Second sentence."
    mapping = json.loads(work.with_name("fixes_log.json").read_text())["id_map"]
    assert mapping["P3"] == mapping["P3#2"] == ["P3"]


def test_split_tail_suffixes_follow_creation_order(work):
    doc = json.loads(work.read_text())
    doc["items"][2]["text"] = "First. Middle. Last."
    work.write_text(json.dumps(doc))
    result = run(work, [dict(op="split", id="P3", at="Last.", why="tail"),
                        dict(op="split", id="P3", at="Middle.", why="another tail"),
                        dict(op="type", ids=["P3#2"], to="caption", why="last piece"),
                        dict(op="type", ids=["P3#3"], to="heading", why="middle piece")])
    assert [(it["text"], it["type"]) for it in result["items"][2:5]] == [
        ("First.", "para"), ("Middle.", "heading"), ("Last.", "caption")]


def test_apply_echoes_original_targets_for_every_op(work, capsys):
    run(work, [dict(op="type", ids=["P1"], to="heading", why="title"),
               dict(op="join", ids=["P2", "P3"], why="join"),
               dict(op="split", id="P3", at="Second sentence.", why="split"),
               dict(op="type", ids=["P3#2"], to="caption", why="tail caption"),
               dict(op="move", id="N1", after="P1", why="move"), region_op(after="P2")])
    lines = capsys.readouterr().out.splitlines()
    echoes = [line for line in lines if line.startswith("op ")]
    assert len(echoes) == 6
    assert 'op 1 type\u2192heading: P1 "An intro."' in echoes
    assert 'P2 "inter-"; P3 "national Second sentence."' in echoes[1]
    assert 'P3 "national Second sentence."' in echoes[2]
    assert 'P3#2 "Second sentence."' in echoes[3]
    assert 'N1 "A note."; P1 "An intro."' in echoes[4]
    assert 'region1 "The normal distribution has two parameters, the mean"' in echoes[5]
    assert not any(line.startswith("Warning") for line in lines)


def test_reapply_warns_but_uses_original_ids(work, capsys):
    run(work, [dict(op="type", ids=["P1"], to="heading", why="title")])
    capsys.readouterr()
    result = run(work, [dict(op="type", ids=["P1", "P2"], to="frag", why="hide originals"),
                        dict(op="move", id="N1", after="P1", why="original anchor")])
    output = capsys.readouterr().out
    assert 'Warning op 1: P1 means original "An intro."; current files show "inter-" under P1.' in output
    assert 'Warning op 1: P2 means original "inter-"; current files show "national Second sentence." under P2.' in output
    assert 'Warning op 2: P1 means original "An intro."' in output
    assert result['items'][0]['text'] == 'An intro.'
    assert result['items'][0]['type'] == 'frag'
    assert result['items'][1]['text'] == 'A note.'


def test_reapply_unchanged_text_has_no_warning(work, capsys):
    run(work, [])
    capsys.readouterr()
    run(work, [dict(op="type", ids=["P2"], to="heading", why="same original item")])
    assert 'Warning' not in capsys.readouterr().out


def test_overlay_original_numbering(work, capsys, monkeypatch):
    from PIL import ImageDraw
    run(work, [dict(op="type", ids=["P1"], to="heading", why="title")])
    capsys.readouterr()
    labels = []
    draw_text = ImageDraw.ImageDraw.text
    def record(self, xy, text, *args, **kwargs):
        labels.append(text)
        return draw_text(self, xy, text, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', record)
    fix.overlay(work, '1')
    assert 'H1 L1' in labels  # headings show their level
    assert '(current numbering)' in capsys.readouterr().out
    labels.clear()
    fix.overlay(work, '1', orig=True)
    assert not any(label.startswith('H1') for label in labels) and 'P1' in labels
    assert '(original numbering)' in capsys.readouterr().out


def test_overlay_orig_without_backup_and_cli_flag(work, capsys, monkeypatch):
    assert fix.overlay(work, '1', orig=True)
    assert '(current numbering)' in capsys.readouterr().out
    called = []
    monkeypatch.setattr(fix, 'overlay', lambda *args: called.append(args))
    monkeypatch.setattr('sys.argv', ['fix.py', 'overlay', str(work), '--orig'])
    fix.main()
    assert called[0] == (work, None, None, True)
