"""A drop cap (one enlarged capital beside the first lines) is left out by text extraction and by MinerU."""
import pdfplumber
import pytest
from reportlab.pdfgen import canvas

import mineru_backend as mb
import segment as s
from common import drop_cap_for

LINES = ["ublished research findings are sometimes", "refuted by subsequent evidence, with",
         "ensuing confusion and disappointment."]
CONT = ["and so the argument continues for a while", "longer than a single line of body text."]
W, H = 595, 842


def _pdf(path, cap=True):
    c = canvas.Canvas(str(path), pagesize=(W, H))
    top = 100  # distance of the first line's top from the page top
    if cap:
        c.setFont("Helvetica-Bold", 40)
        c.drawString(60, H - top - 30, "P")
    c.setFont("Helvetica", 10)
    for i, ln in enumerate(LINES):
        c.drawString(90, H - top - 8 - 12 * i, ln)
    for i, ln in enumerate(CONT):  # an ordinary paragraph that continues the previous page: lowercase start, no cap
        c.drawString(60, H - 300 - 12 * i, ln)
    c.save()


def _layer(path):
    pg = pdfplumber.open(path).pages[0]
    words = s.get_words(pg)
    return words, float(pg.width), float(pg.height), s.body_size(words)


def _sc(bbox_cap, bbox_cont):
    mk = lambda text, bbox: {"type": "text", "content": text, "bbox": bbox}
    head = {"type": "paragraph_title", "content": "Introduction", "bbox": [0.1, 0.05, 0.3, 0.07], "level": 2}
    return {"pages": [{"page_idx": 0, "blocks": [head,
        mk(" ".join(LINES), bbox_cap), mk(" ".join(CONT), bbox_cont)]}]}


def _boxes(words):
    first = [w for w in words if w["text"] == "ublished"][0]
    return [60 / W, (first["top"] - 3) / H, 400 / W, (first["top"] + 36) / H], [60 / W, 300 / H, 400 / W, 325 / H]


def test_mineru_restores_drop_cap(tmp_path):
    p = tmp_path / "a.pdf"
    _pdf(p)
    b1, b2 = _boxes(_layer(p)[0])
    paras = [i["text"] for i in mb.convert(_sc(b1, b2), "a.pdf", str(p))["items"] if i["type"] == "para"]
    assert paras[0].startswith("Published research findings")
    assert paras[1].startswith("and so the argument")  # a normal lowercase continuation is left alone


def test_mineru_without_drop_cap_is_unchanged(tmp_path):
    p = tmp_path / "b.pdf"
    _pdf(p, cap=False)
    b1, b2 = _boxes(_layer(p)[0])
    paras = [i["text"] for i in mb.convert(_sc(b1, b2), "b.pdf", str(p))["items"] if i["type"] == "para"]
    assert paras[0].startswith("ublished research")


def test_mineru_convert_survives_missing_pdf():
    d = mb.convert(_sc([0.1, 0.1, 0.5, 0.2], [0.1, 0.4, 0.5, 0.5]), "x.pdf", "/no/such/x.pdf")
    assert [i["text"][:3] for i in d["items"] if i["type"] == "para"] == ["ubl", "and"]


def test_pdfplumber_path_merges_drop_cap(tmp_path):
    p = tmp_path / "c.pdf"
    _pdf(p)
    words, w, h, body = _layer(p)
    pg = pdfplumber.open(p).pages[0]
    words, caps = s.split_drop_caps(words, body)
    lines = s.make_lines(words)
    for ln in lines:
        ln["band"], ln["col"] = 0, 0
    blocks = s.restore_drop_caps(s.build_blocks(lines, 1, body), caps, body)
    assert any(b["text"].startswith("Published research findings") for b in blocks)
    assert not any(b["text"].strip() == "P" for b in blocks)
    assert any(b["text"].startswith("and so the argument") for b in blocks)


@pytest.mark.parametrize("text", ["e.g. a lowercase start", "Capital start", ""])
def test_drop_cap_for_needs_lowercase_text(text):
    big = {"text": "P", "x0": 60, "x1": 85, "top": 100, "bottom": 140, "size": 40}
    assert (text[:1].islower()) == bool(drop_cap_for(text, (60, 100, 400, 140), [big], 10)) if text else \
        drop_cap_for(text, (60, 100, 400, 140), [big], 10) is None
