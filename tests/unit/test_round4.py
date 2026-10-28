"""Small-caps subheadings without capitals, line-end hyphens decided by the document, numbers in real papers."""
import copy

import segment as s
import common as c
from check import run_checks


def head(text, x0, x1, pw=486.0, n=1):
    return dict(text=text, size=11.0, bold=0.0, n_lines=n, x0=x0, x1=x1, pw=pw)


def test_small_caps_subheading_without_capitals_is_a_heading_only_when_centred():
    assert s.is_heading_block(head("C. industry comparisons", 187.5, 298.5), 11.0)  # centred on a 486pt page
    assert s.is_heading_block(head("B. sample selection rules", 175.6, 310.4), 11.0)
    # the same words as the start of a list item at the left margin are not a heading
    assert not s.is_heading_block(head("C. industry comparisons", 60.0, 170.0), 11.0)
    assert not s.is_heading_block(head("c. industry comparisons", 187.5, 298.5), 11.0)


def hy(*parts):
    return s.HY.join(parts)


def resolve(texts):
    out, decisions = s.resolve_hyphens(texts)
    return out, {(a, b): k for a, b, k in decisions}


def test_hyphen_kept_when_the_word_before_the_break_is_already_a_compound():
    out, _ = resolve(["the cost-of" + s.HY + "living index", "a state-of" + s.HY + "the-art method"])
    assert out == ["the cost-of-living index", "a state-of-the-art method"]


def test_hyphen_kept_between_number_words_and_when_the_document_hyphenates_elsewhere():
    out, _ = resolve(["the twenty" + s.HY + "fifth percentile", "a low" + s.HY + "cost plan", "every low-cost firm"])
    assert out == ["the twenty-fifth percentile", "a low-cost plan", "every low-cost firm"]


def test_hyphen_dropped_when_the_document_writes_the_closed_form_elsewhere():
    out, dec = resolve(["a dataset of poli" + s.HY + "cies", "the policies differ", "a data" + s.HY + "set of homes", "the dataset is new"])
    assert out[0] == "a dataset of policies" and out[2] == "a dataset of homes"
    out, _ = resolve(["the refer" + s.HY + "ence-dependent model", "a reference point"])
    assert out[0] == "the reference-dependent model"


def test_hyphen_kept_when_both_pieces_are_words_and_the_closed_form_never_occurs_and_dropped_without_evidence():
    out, _ = resolve(["a modest" + s.HY + "scale plan", "modest effects", "a scale of things"])
    assert out[0] == "a modest-scale plan"
    out, _ = resolve(["an unusual" + s.HY + "qxz word"])  # no evidence either way: the old behaviour
    assert out == ["an unusualqxz word"]


def test_hyphen_decisions_are_resolved_for_every_text_and_markers_never_survive():
    doc = {"items": [{"id": "P1", "type": "para", "text": "a modest" + s.HY + "scale plan with modest effects", "page": 1},
                      {"id": "P2", "type": "para", "text": "a scale of things", "page": 1}]}
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        s.write_outputs(doc, Path(d), 5000)
        assert "" not in (Path(d) / "paragraphs.json").read_text(encoding="utf-8")
    assert doc["items"][0]["text"] == "a modest-scale plan with modest effects"


def test_join_text_marks_a_dropped_hyphen_only_when_asked():
    assert s.join_text("hy-", "phen") == "hyphen"
    assert s.join_marked("hy-", "phen") == "hy" + s.HY + "phen"
    assert s.join_marked("one", "two") == "one two"


def nums(text):
    return c.source_numbers(text)


def test_source_numbers_accepts_digits_a_text_layer_set_apart_but_never_merges_numbers():
    assert 10 in nums("risk of 3 × 1 0 − 5 per year") and 5 in nums("3 × 1 0 − 5")
    assert 2575 not in nums("shares of 25 75 percent") and 25 in nums("shares of 25 75 percent")
    assert 17 not in nums("1 7") or 17 in nums("1 7")  # a run of single digits may be one number: allowed, only as an extra
    assert 99 not in nums("3 × 1 0 − 5")


def test_source_numbers_accepts_spelled_out_numbers_in_digits():
    assert 48 in nums("Forty-eight percent of the firms answered") and 25 in nums("the twenty-fifth percentile")
    assert 5 in nums("the fifth wave") and 90 in nums("the ninetieth percentile") and 73 in nums("seventy three")
    assert 1 not in nums("the first wave") and 2 not in nums("the second wave")  # too common to count as numbers
    assert 49 not in nums("Forty-eight percent")


def _with_source(clean, source, note):
    doc, g = copy.deepcopy(clean[0]), copy.deepcopy(clean[1])
    doc["items"][0]["text"] = source
    g["paras"]["P1"]["note"] = note
    return doc, g


def test_check_accepts_notes_that_use_digits_for_source_words_and_split_digits(clean):
    doc, g = _with_source(clean, "Three buyers chose it. Forty-eight percent paid 3 × 1 0 − 5 per year.", "48 percent paid 3 × 10−5.")
    errors, _, _ = run_checks(doc, g)
    assert not any("P1" in e and "numbers not in the source" in e for e in errors)
    doc, g = _with_source(clean, "Three buyers chose it. Forty-eight percent paid.", "49 percent paid.")
    errors, _, _ = run_checks(doc, g)
    assert any("numbers not in the source" in e and "49" in e for e in errors)


def test_money_next_to_inline_maths_is_not_reported_as_a_json_backslash_problem(clean):
    doc, g = clean
    g = copy.deepcopy(g)
    g["paras"]["P1"]["why"] = "Pays $500 against $750, and $x$ stays small; then $y$ too."
    _, warns, _ = run_checks(doc, g)
    assert not any("double backslash" in w for w in warns)
    g["paras"]["P1"]["why"] = "Pays $500 against $750 and $\theta$ is fixed."  # a real eaten backslash (a tab) still warns
    _, warns, _ = run_checks(doc, g)
    assert any("paras.P1.why" in w and "double backslash" in w for w in warns)
