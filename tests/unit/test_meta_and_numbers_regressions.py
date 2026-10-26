"""Regressions: bilingual meta fields, decimal section numbers, figure hosts."""
import json
from types import SimpleNamespace
import pytest
import render as r
from common import numbers_in, source_numbers
from check import run_checks


@pytest.mark.parametrize("lang", [None, "zh", "en"])
def test_bilingual_meta_fields_render(clean, tmp_path, lang):
    doc, guide = clean
    guide["meta"]["notes_lang"] = ["zh", "en"]
    guide["meta"].update(title={"en": "Reward choices", "zh": "奖励选择"},
                         author={"en": "A. Smith", "zh": "史密斯"},
                         source={"en": "Journal 1", "zh": "期刊 1"})
    out = tmp_path / "p.html"
    args = SimpleNamespace(density=None, force=True, sources=None, no_page_images=True, pdf=None, lang=lang)
    r.render(doc, guide, out, args)
    text = out.read_text(encoding="utf-8")
    d = json.loads(r.DATA_RE.search(text).group(1).replace("<\\/", "</"))
    for f in ("title", "author", "source"):
        assert isinstance(d["meta"][f], str) and d["meta"][f]
    assert "<title>" in text and "{" not in text.split("<title>")[1].split("</title>")[0]
    if lang == "en":
        assert d["meta"]["title"] == "Reward choices"
    if lang == "zh":
        assert d["meta"]["title"] == "奖励选择"


@pytest.mark.parametrize("src,note", [
    ("Section 6.2 reports a gain of 40 points.", "第 6.2 节报告了 40 分的提升。"),
    ("第 6.2 节报告了 40 分的提升。", "Section 6.2 reports a gain of 40 points."),
    ("Section 6.2.1 reports a gain of 40 points.", "第 6.2.1 节报告了 40 分的提升。"),
])
def test_section_numbers_are_references_in_both_languages(src, note):
    assert numbers_in(src) == {40.0}
    assert numbers_in(note) == {40.0}


def test_chinese_section_number_passes_check(clean):
    doc, guide = clean
    doc["items"][0]["text"] = "Section 6.2 shows three buyers chose the smaller reward."
    guide["paras"]["P1"]["note"] = "第 6.2 节说明三个买家选了较小的奖励。"
    errors, _, _ = run_checks(doc, guide)
    assert not any("6.2" in e for e in errors)


def test_real_decimals_still_checked():
    assert numbers_in("The share was 6.2% in Section 3.") == {6.2}
    assert numbers_in("表 24.03") == {24.03}
    assert 0.2 not in source_numbers("Section 6.2 holds")
