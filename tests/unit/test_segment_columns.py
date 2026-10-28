"""Three-column pages, per-page column detection, the layout self-check and paragraph joins (synthetic geometry)."""
import segment as s
import mineru_backend as mb


def word(text, x0, top, size=10, font="Serif", w=None):
    w = w or 4.5 * len(text)
    return dict(text=text, x0=x0, x1=x0 + w, top=top, bottom=top + size, size=size, bold=False, mono=False, font=font)


def column_words(col_x, col_w, tag, n_lines=40, top0=100, pitch=12):
    """n_lines lines of ragged text in one column; every word carries its column tag so the order is visible."""
    out = []
    for i in range(n_lines):
        x = col_x
        k = 0
        while x + 40 < col_x + col_w - (i % 5) * 6:
            out.append(word(f"{tag}l{i}w{k}", x, top0 + i * pitch, w=36))
            x += 40
            k += 1
    return out


COLS = [(50, 150, "A"), (230, 150, "B"), (410, 150, "C")]


def page_words(extra=()):
    return [w for x, cw, tag in COLS for w in column_words(x, cw, tag)] + list(extra)


def segs_of(words):
    return s.make_lines(words, gap_split=True)


def test_gutters_found_for_three_columns_and_not_for_one():
    gs = s.column_gutters(segs_of(page_words()), 612, 10)
    assert len(gs) == 2 and 190 < gs[0] < 230 and 370 < gs[1] < 410
    one = [word(f"w{k}", 50 + 40 * (k % 13), 100 + 12 * (k // 13), w=36) for k in range(13 * 30)]
    assert s.column_gutters(segs_of(one), 612, 10) == []


def test_gutters_ignore_a_short_table_set_in_columns():
    # a name list in four columns under one-column prose is not a column layout
    prose = [word(f"p{k}", 60 + 40 * (k % 12), 100 + 12 * (k // 12), w=36) for k in range(12 * 30)]
    names = [word(f"n{r}{c}", 60 + 130 * c, 500 + 12 * r, w=80) for r in range(3) for c in range(4)]
    assert s.column_gutters(segs_of(prose + names), 612, 10) == []


def test_three_columns_read_column_by_column_with_a_full_width_title_first():
    title = [word("Title", 50, 40, size=22, w=500)]
    words = page_words(title)
    segs = segs_of(words)
    gs = s.column_gutters(segs, 612, 10)
    lines = s.order_columns(segs, gs, 10)
    tags = [ln["text"][0] for ln in lines]
    assert tags[0] == "T"
    body = tags[1:]
    assert body == sorted(body) and body.count("A") == body.count("B") == body.count("C") == 40
    assert lines[0]["band"] != lines[1]["band"]  # the title does not share a stream with column A


def test_table_that_straddles_a_gutter_does_not_stop_the_column_split():
    cells = [word("cell", 190 + 20 * k, 140, size=9, w=16) for k in range(6)]  # crosses the first gutter
    segs = segs_of(page_words(cells))
    gs = s.column_gutters(segs, 612, 10)
    assert len(gs) == 2
    lines = s.order_columns(segs, gs, 10)
    tags = [ln["text"][0] for ln in lines]
    assert tags.count("C") == 40 and tags.index("C") > max(i for i, t in enumerate(tags) if t == "B")


def test_box_across_two_columns_is_read_as_a_unit_and_not_glued_to_the_text_around_it():
    box_words = column_words(230, 150, "X", n_lines=10, top0=100) + column_words(410, 150, "Y", n_lines=10, top0=100)
    rest = column_words(50, 150, "A") + column_words(230, 150, "B", n_lines=25, top0=240) + column_words(410, 150, "C", n_lines=25, top0=240)
    segs = segs_of(box_words + rest)
    gs = s.column_gutters(segs, 612, 10)
    lines = s.order_columns(segs, gs, 10, boxes=[[222, 90, 575, 225]], page=(612, 792))
    tags = "".join(ln["text"][0] for ln in lines)
    assert tags.index("X") < tags.index("Y") and "X" not in tags[tags.index("Y"):]
    assert tags.index("A") < tags.index("X") < tags.index("B") < tags.index("C")
    assert all(ln.get("aside") for ln in lines if ln["text"][0] in "XY")
    assert not any(ln.get("aside") for ln in lines if ln["text"][0] in "ABC")


class FakePage:
    def __init__(self, words):
        self.words, self.width, self.height = words, 612.0, 792.0


class FakePdf:
    def __init__(self, words):
        self.pages = [FakePage(words)]


def test_from_pdf_text_uses_the_three_column_path_in_auto_and_forced_modes(monkeypatch):
    monkeypatch.setattr(s, "get_words", lambda page: [dict(w) for w in page.words])
    monkeypatch.setattr(s, "figure_boxes", lambda page: [])
    pdf = FakePdf(page_words())
    for cols in ("auto", "3"):
        blocks, body, info, stats = s.from_pdf_text(pdf, [1], cols)
        assert stats["multi_col"] == 1
        assert [b["text"][0] for b in blocks] == ["A", "B", "C"]  # one block per column, in column order
    _, _, _, stats = s.from_pdf_text(pdf, [1], "1")
    assert stats["multi_col"] == 0


def test_bold_named_body_font_is_not_a_heading_signal():
    words = [word("body", 50 + 30 * k, 100, font="Frutiger-Medium") for k in range(20)]
    for w in words:
        w["bold"] = True
    odd = word("Heading", 50, 300, size=12, font="Frutiger-Bold")
    odd["bold"] = True
    allw = words + [odd]
    s.unbold_body_font(allw, 10)
    assert not any(w["bold"] for w in words) and odd["bold"]


def test_headingish_is_a_real_boolean_so_mid_paragraph_lines_do_not_split():
    lines = [s.line_from_words([word(t, 50 + 40 * k, 100 + 12 * i, w=36) for k, t in enumerate(txt.split())])
             for i, txt in enumerate(["the study found that the rates were higher in", "the treated group than in the controls.",
                                      "further analysis of these results showed that"])]
    for ln in lines:
        ln["band"], ln["col"] = 1, 0
        assert s.headingish(ln, 10) is False
    # the second line ends in a full stop, the first and third do not; none may be told apart as "heading or not"
    assert len(s.build_blocks(lines, 1, 10)) == 1


def test_comma_line_with_a_number_is_not_a_heading_and_a_question_heading_wraps():
    assert not s.is_heading_block(dict(text="1. Based on the above considerations,", size=10, bold=0, n_lines=1), 10)
    two = [dict(text="How Can We Improve", top=0, bottom=11, x0=50, x1=150, size=11, bold=0, mono=0, band=1, col=0),
           dict(text="the Situation?", top=12, bottom=23, x0=50, x1=120, size=11, bold=0, mono=0, band=1, col=0)]
    blocks = s.build_blocks(two, 1, 9)
    assert len(blocks) == 1 and s.is_heading_block(blocks[0], 9)


def test_small_references_heading_is_still_a_heading_and_ends_the_body():
    def blk(text, top, size=7.0, level=None):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=0, mono=0, top=top, bottom=top + 8,
                    x0=50, x1=200, n_lines=1)
    body = [blk("A body sentence that is long enough to count as ordinary running text in the study.", 100, 9.0),
            blk("References", 300, 8.0), blk("1. Smith J (2001) A study. Nature 1: 1-2.", 320), blk("2. Lee K (2003) Another. Cell 2: 3-4.", 330)]
    s.classify(body, 9.0, {1: {"h": 792.0}}, 1)
    assert body[1]["type"] == "heading"
    assert s.mark_sections(body) == 2 and [b["type"] for b in body[2:]] == ["ref", "ref"]


def test_pull_quote_between_the_halves_of_a_sentence_is_set_aside():
    def blk(text, size, top, typ="para"):
        return dict(type=typ, text=text, page=1, key=(1, 0), size=size, top=top, bottom=top + 12, x0=50, x1=200, n_lines=1)
    blocks = [blk("The rate of replication was low because the notion that", 9, 100),
              blk("Most claimed findings are false", 14, 130, "heading"),
              blk("are false.", 14, 150),
              blk("claims of this kind should be read with care. Next sentence.", 9, 180)]
    out, merges = s.merge_continuations(blocks, 9)
    texts = [b["text"] for b in out if b["type"] == "para"]
    assert texts == ["The rate of replication was low because the notion that claims of this kind should be read with care. Next sentence."]
    assert [b["type"] for b in out if b["type"] != "para"] == ["frag", "frag"]


def test_paragraph_split_by_a_figure_is_joined_and_keeps_both_pages():
    a = dict(type="para", text="The effect grew with sample size and", page=3, key=(2, 0), top=700, bottom=760, ph=792, x0=50, x1=200)
    fig = dict(type="frag", text="Figure 2", page=4, key=(1, 0), top=100, bottom=300, ph=792, x0=50, x1=200)
    b = dict(type="para", text="stayed stable afterwards. A new sentence.", page=4, key=(2, 0), top=320, bottom=360, ph=792, x0=50, x1=200)
    out, merges = s.merge_continuations([a, fig, b])
    assert [x["type"] for x in out] == ["para", "frag"] and out[0]["page"] == 3 and out[0]["pages"] == {3, 4}
    assert out[0]["text"].endswith("stayed stable afterwards. A new sentence.") and out[0]["breaks"] == 1


def test_uppercase_start_joins_only_across_a_real_column_break():
    top = dict(type="para", text="The result depends on the sample", page=1, key=(1, 0), top=100, bottom=300, ph=792, x0=50, x1=200)
    near = dict(type="para", text="Studies conducted in the field.", page=1, key=(2, 0), top=320, bottom=400, ph=792, x0=50, x1=200)
    assert not s.paragraph_continues(top, near)  # same page, starts below: a new paragraph in another stream
    low = dict(top, top=500, bottom=760)
    nxt = dict(near, top=60, bottom=200)
    assert s.paragraph_continues(low, nxt)  # a ends at the foot of a column and b opens the next one


def test_join_open_paragraphs_for_the_mineru_tier_skips_figures_but_not_headings():
    blocks = [dict(type="para", text="Power depends on the number of", page=2),
              dict(type="frag", text="Table 1", page=2),
              dict(type="para", text="studies, the effect size and bias.", page=2),
              dict(type="para", text="An open sentence without a stop", page=2),
              dict(type="heading", text="Methods", page=2, level=1),
              dict(type="para", text="and lowercase after a heading stays apart.", page=2)]
    out, joins = s.join_open_paragraphs(blocks)
    assert joins == 1 and out[0]["text"] == "Power depends on the number of studies, the effect size and bias."
    assert [b["type"] for b in out] == ["para", "frag", "para", "heading", "para"]


def test_mineru_convert_joins_a_paragraph_cut_at_a_column_break():
    sc = {"pages": [{"page_idx": 0, "blocks": [
        {"type": "paragraph_title", "content": "Methods", "level": 2, "bbox": [0.1, 0.1, 0.5, 0.15]},
        {"type": "text", "content": "Studies with small samples are less likely to find true effects and the", "bbox": [0.1, 0.5, 0.5, 0.95]},
        {"type": "text", "content": "same holds for small effects in the field.", "bbox": [0.55, 0.05, 0.95, 0.2]}]}]}
    d = mb.convert(sc, "x.pdf", "/x.pdf")
    paras = [i for i in d["items"] if i["type"] == "para"]
    assert len(paras) == 1 and paras[0]["text"].endswith("same holds for small effects in the field.")


def good_blocks(n=20):
    return [dict(type="para", text="A complete sentence about the study design and results.", page=1 + i % 3, jumps=0) for i in range(n)]


def test_layout_signals_pass_a_clean_split_and_flag_a_column_mix():
    score, reasons = s.layout_signals(good_blocks(), 3)
    assert reasons == [] and score < 1
    bad = good_blocks()
    for b in bad[:8]:
        b["text"], b["jumps"] = "and then the next column starts with this and", 4
    score2, reasons2 = s.layout_signals(bad, 3)
    assert score2 > score and any("lower case" in r for r in reasons2) and any("jump" in r for r in reasons2)


def test_layout_signals_flag_references_in_the_body_and_footnote_floods():
    refs = [dict(type="para", text=f"{i}. Smith JA, Lee K (2004) A study of things. Lancet 363: 17{i}-18{i}.", page=1, jumps=0)
            for i in range(1, 6)]
    score, reasons = s.layout_signals(good_blocks(10) + refs, 2)
    assert any("reference entries" in r for r in reasons)
    def note(top, ph=792):
        return dict(type="note", text="Eight words are in this note about something minor.", page=1, top=top, bottom=top + 20, ph=ph)
    high = [note(100 + 30 * i) for i in range(12)]  # "footnotes" in the upper half of the page: really body text
    score, reasons = s.layout_signals(good_blocks(10) + high, 2)
    assert any("footnotes" in r for r in reasons)
    low = [note(650 + 2 * i) for i in range(12)]  # a footnote-heavy paper whose notes sit at the foot of the page
    assert not any("footnotes" in r for r in s.layout_signals(good_blocks(10) + low, 2)[1])
    heads = [dict(type="heading", text="A heading here", level=1, page=1) for _ in range(12)]
    assert any("headings per page" in r for r in s.layout_signals(good_blocks(10) + heads, 2)[1])


def fake_result(columns, score, reasons):
    return {"columns": columns, "score": score, "reasons": reasons, "stats": {"multi_col": 0, "two_col": 0}}


def test_auto_retries_other_column_settings_and_keeps_the_best(monkeypatch):
    results = {"auto": fake_result("auto", 5.0, ["49% of the paragraphs start in lower case"]),
               "1": fake_result("1", 4.0, ["x"]), "2": fake_result("2", 0.2, []), "3": fake_result("3", 3.0, ["y"])}
    calls = []
    monkeypatch.setattr(s, "segment_text_layer", lambda pdf, pnos, c, cache=None: (calls.append(c), results[c])[1])
    best, msgs = s.choose_columns(None, [1, 2], "auto")
    assert best["columns"] == "2" and calls == ["auto", "1", "2", "3"]
    assert len(msgs) == 1 and "--columns 2" in msgs[0]


def test_auto_that_looks_fine_runs_once_and_says_so(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "segment_text_layer", lambda pdf, pnos, c, cache=None: (calls.append(c), fake_result(c, 0.1, []))[1])
    best, msgs = s.choose_columns(None, [1], "auto")
    assert calls == ["auto"] and len(msgs) == 1 and "自动识别通过" in msgs[0]


def test_when_every_setting_looks_bad_the_message_tells_the_agent_what_to_run(monkeypatch):
    monkeypatch.setattr(s, "segment_text_layer", lambda pdf, pnos, c, cache=None: fake_result(c, 5.0, ["bad"]))
    best, msgs = s.choose_columns(None, [1], "auto")
    assert best["columns"] == "auto" and len(msgs) == 2
    assert "agent" in msgs[1] and "--text" in msgs[1] and "render.py" in msgs[1] and "--engine mineru" in msgs[1]


def test_explicit_columns_are_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "segment_text_layer", lambda pdf, pnos, c, cache=None: (calls.append(c), fake_result(c, 5.0, ["bad"]))[1])
    best, msgs = s.choose_columns(None, [1], "2")
    assert calls == ["2"] and best["columns"] == "2"


def test_two_line_title_in_large_type_stays_in_one_stream():
    title = [word("Why", 50, 20, size=25, w=60), word("Most", 120, 20, size=25, w=60),
             word("Are", 50, 50, size=25, w=60), word("False", 120, 50, size=25, w=60)]  # 5pt between the lines
    segs = segs_of(page_words(title))
    lines = s.order_columns(segs, s.column_gutters(segs, 612, 10), 10)
    big = [ln for ln in lines if ln["size"] == 25]
    assert len(big) == 2 and big[0]["band"] == big[1]["band"]
    blocks = s.build_blocks(big, 1, 10)
    assert len(blocks) == 1 and blocks[0]["text"] == "Why Most Are False"


def test_title_is_the_largest_type_not_a_smaller_label_above_it():
    def blk(text, size, top):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=1.0, mono=0, top=top, bottom=top + size,
                    x0=50, x1=300, n_lines=1)
    blocks = [blk("Essay", 12, 40), blk("Why Most Published Research Findings Are False", 25, 70)]
    s.classify(blocks, 9.0, {1: {"h": 792.0}}, 1)
    assert blocks[1]["type"] == "heading" and blocks[1]["level"] == 0 and blocks[0].get("level") != 0


def test_heading_inside_a_shaded_text_box_stays_a_heading_but_figure_labels_do_not():
    def blk(text, size, top, x0=50, x1=200, n=1):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=1.0, mono=0, top=top, bottom=top + 11,
                    x0=x0, x1=x1, n_lines=n)
    text_box = [blk("Summary", 11, 150), blk("There is increasing concern that most current published findings are false.", 9, 170, n=6)]
    info = {1: {"h": 792.0, "figs": [[36, 140, 210, 400]]}}
    s.classify(text_box, 9.0, info, 1)
    assert text_box[0]["type"] == "heading"
    label = [blk("Pre-study odds", 10, 150)]
    s.classify(label, 9.0, info, 1)
    assert label[0]["type"] == "frag"


def test_wide_box_must_hold_a_gutter_well_inside_not_graze_its_edge():
    segs = segs_of(page_words())
    gs = s.column_gutters(segs, 612, 10)
    box_over_one_column = [[36, 100, gs[0] + 3, 400]]  # reaches 3pt past the gutter: a shaded box in column A
    lines = s.order_columns(segs, gs, 10, boxes=box_over_one_column, page=(612, 792))
    assert not any(ln.get("aside") for ln in lines)


def test_rules_only_table_becomes_a_region_and_its_cells_are_not_footnotes():
    rules = [dict(x0=50, x1=350, top=t, bottom=t + 0.5) for t in (100, 120, 200)]
    boxes = s.rule_tables(rules, 0, 0, 612)
    assert boxes == [[48, 98, 352, 200.5 + 2, "rules"]]
    def blk(text, top):
        return dict(type="para", text=text, page=1, key=(1, 0), size=7.0, bold=0, mono=0, top=top, bottom=top + 8,
                    x0=60, x1=300, n_lines=1)
    body = dict(text="An ordinary paragraph of running text that is long enough to matter for the page.", page=1, key=(2, 0),
                size=9.0, bold=0, mono=0, top=300, bottom=340, x0=50, x1=350, n_lines=4)
    cells = [blk("Adequately powered RCT with little bias", 130), blk("0.80 1:1 0.10", 150), blk("Underpowered phase I/II RCT", 170)]
    s.classify(cells + [body], 9.0, {1: {"h": 792.0, "figs": boxes}}, 1)
    assert all(c["type"] == "frag" and c.get("table") for c in cells) and body["type"] == "para"


def test_run_of_small_note_rows_that_are_mostly_numbers_is_a_table_not_footnotes():
    def note(text, top):
        return dict(text=text, page=1, key=(1, 0), size=7.0, bold=0, mono=0, top=top, bottom=top + 8, x0=50, x1=200, n_lines=1)
    rows = [note(t, 600 + 10 * i) for i, t in enumerate(["0.80 1:1 0.10", "Adequately powered RCT", "0.95 2:1 0.30", "0.20 1:5 0.20", "Meta-analysis of studies"])]
    s.classify(rows, 9.0, {1: {"h": 792.0}}, 1)
    assert all(r["type"] == "frag" for r in rows)
    real = [note(f"{i}. See the earlier study by Smith for the argument.", 600 + 10 * i) for i in range(1, 6)]
    s.classify(real, 9.0, {1: {"h": 792.0}}, 1)
    assert all(r["type"] == "note" for r in real)


# ---- single-column papers: off-page panels, glyph metrics, touching words, mastheads, tables ----

class MetricPage:
    """A pdfplumber-like page whose words and chars are given as dicts."""
    def __init__(self, words, chars=(), width=486.0, height=702.0):
        self.words_in, self.chars, self.width, self.height = words, list(chars), width, height
        self.bbox = (0.0, 0.0, width, height)

    def extract_words(self, **kw):
        return [dict(w, upright=True, fontname=w.get("fontname", "Serif")) for w in self.words_in]


def raw(text, x0, top, size=11.0, x1=None):
    return dict(text=text, x0=x0, x1=x1 if x1 is not None else x0 + 5 * len(text), top=top, bottom=top + size, size=size)


def test_words_placed_outside_the_page_are_never_read():
    page = MetricPage([raw("Contents", -325.0, 80.0), raw("hidden", -200.0, 90.0), raw("Visible", 60.0, 100.0),
                       raw("below", 60.0, 900.0)])
    assert [w["text"] for w in s.get_words(page)] == ["Visible"]


def test_a_glyph_with_wrong_font_metrics_is_put_back_on_its_baseline():
    base = 628.6  # PDF y of the baseline on a 702pt page
    good = dict(text="O", top=62.6, bottom=76.6, size=14.0, matrix=(14, 0, 0, 14, 157.6, base), upright=True, y0=0, y1=0)
    odd = dict(text="(", top=71.5, bottom=85.5, size=14.0, matrix=(14, 0, 0, 14, 152.5, base), upright=True, y0=0, y1=0)
    page = MetricPage([], [good, odd])
    s.level_glyph_boxes(page)
    assert good["top"] == 62.6  # an ordinary glyph is left alone
    assert abs(odd["top"] - (702 - base - 0.8 * 14)) < 1e-6 and odd["bottom"] - odd["top"] == 14.0


def test_bracket_in_another_font_joins_its_word_and_does_not_become_a_line():
    ws = [dict(raw("(", 152.5, 60.0, 14.0, x1=157.0), font="Math"), dict(raw("Re", 157.1, 60.0, 14.0), font="Sans"),
          dict(raw(")", 178.0, 60.0, 14.0, x1=182.0), font="Math"), dict(raw("thinking", 182.1, 60.0, 14.0), font="Sans"),
          dict(raw("Small", 230.0, 60.0, 14.0), font="Sans")]
    lines = s.make_lines(ws)
    assert len(lines) == 1 and lines[0]["text"] == "(Re)thinking Small"


def test_small_capitals_split_by_size_are_rejoined_but_subscripts_are_not():
    caps = [dict(raw("R", 100.0, 100.0, 10.0, x1=107.0), font="A"), dict(raw("EFERENCES", 107.2, 103.0, 7.0), font="A")]
    caps[1]["bottom"] = caps[0]["bottom"] - 0.5  # same baseline, smaller capitals
    assert s.line_from_words(caps)["text"] == "REFERENCES"
    sub = [dict(raw("L", 100.0, 100.0, 10.0, x1=107.0), font="A"), dict(raw("DPO", 107.2, 106.0, 7.0), font="A")]
    assert s.line_from_words(sub)["text"] == "L DPO"  # the subscript sits lower: not one word


def test_punctuation_and_accent_tokens_attach_to_their_neighbours():
    assert s.join_words("Smith’s (", "1992") == "Smith’s (1992"
    assert s.join_words("1992", ")") == "1992)"
    assert s.join_words("review", ".") == "review."
    assert s.join_words("Ho", "̋") == "Hő"
    assert s.compose_accents("Mu¨ller") == "Müller"
    assert s.compose_accents("w˜m") == "w˜m"  # no precomposed letter exists: left as it was


def test_masthead_is_not_the_title_and_a_small_capitals_title_is_found_under_it():
    def blk(text, size, top, n=1):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=0.0, mono=0, top=top, bottom=top + size,
                    x0=75, x1=375, n_lines=n)
    blocks = [blk("JOURNAL OF EXAMPLE STUDIES", 24, 87, 2), blk("Vol. XII March 2001 Issue 4", 14, 151),
              blk("A MODEL OF SOMETHING IMPORTANT*", 10, 189), blk("JANE ROE AND JOHN DOE", 7, 208),
              blk("We develop a simple model of choice under risk and test it in a long abstract sentence.", 8, 236, 12)]
    s.classify(blocks, 10.0, {1: {"h": 666.0}}, 1)
    assert blocks[0]["type"] == blocks[1]["type"] == "frag"
    assert blocks[2]["type"] == "heading" and blocks[2]["level"] == 0 and blocks[2]["text"] == "A MODEL OF SOMETHING IMPORTANT"


def test_journal_line_above_the_title_and_the_mark_after_it_are_dropped():
    def blk(text, size, top):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=0.0, mono=0, top=top, bottom=top + size, x0=30, x1=300, n_lines=1)
    blocks = [blk("Example Journal of Applied Studies 2 (October 2010): 177-199 and a long address", 8, 29),
              blk("(Re)thinking Small Gambles †", 14, 60)]
    s.classify(blocks, 11.0, {1: {"h": 702.0}}, 1)
    assert blocks[0]["type"] == "frag" and blocks[1]["text"] == "(Re)thinking Small Gambles"


def test_text_between_a_tables_rules_is_table_content_even_at_body_size():
    rules = [dict(x0=60, x1=426, top=t, bottom=t + 0.5) for t in (100.0, 300.0)]
    split = [dict(x0=60 + 61 * k, x1=121 + 61 * k, top=140.0, bottom=140.5) for k in range(6)]  # a rule drawn in pieces
    boxes = s.rule_tables(rules + split, 0, 0, 486)
    assert len(boxes) == 1 and boxes[0][4] == "rules"
    line_in = dict(text="Panel A. Full sample 17.05 47.57", top=200.0, bottom=211.0, x0=70, x1=300, size=11.0, bold=0.0, mono=0,
                   band=0, col=0, tab=True)
    line_out = dict(line_in, text="Summary statistics for the full sample are given in the table below.", top=320.0, bottom=331.0, tab=False)
    blocks = s.build_blocks([line_in, line_out], 1, 11.0)
    assert len(blocks) == 2 and blocks[0]["tab"] and not blocks[1]["tab"]
    s.classify(blocks[:1], 11.0, {1: {"h": 702.0}}, 1)
    assert blocks[0]["type"] == "frag" and blocks[0]["table"]


def test_notes_under_a_table_and_significance_stars_are_not_prose_or_footnotes():
    def blk(text, top):
        return dict(text=text, page=1, key=(1, 0), size=8.0, bold=0.0, mono=0, top=top, bottom=top + 9, x0=60, x1=420, n_lines=2)
    tn = [blk("notes: Means with standard deviations are in parentheses. The average is over all customers.", 500),
          blk("*** Significant at the 1 percent level.", 520)]
    s.classify(tn, 11.0, {1: {"h": 702.0}}, 1)
    assert [b["type"] for b in tn] == ["frag", "frag"]
    assert s.CAPTION_RE.match("Table 3—Bounds on a Coefficient")


def test_small_caps_subheading_and_stray_formula_footnotes():
    def blk(text, size=11.0, n=1, top=300):
        return dict(text=text, page=1, key=(1, 0), size=size, bold=0.0, mono=0, top=top, bottom=top + 11, x0=60, x1=250, n_lines=n)
    body = blk("A body paragraph with enough ordinary words to count as running text in this paper.", 11.0, 4, 100)
    head = blk("A. generating Bounds on risk Aversion", 11.0, 1, 200)
    junk = [blk("k 1", 8.0, 1, 600), blk("DEPARTMENT OF ECONOMICS, UNIVERSITY OF CALIFORNIA, BERKELEY", 8.0, 1, 640)]
    real = blk("See Smith and Jones (2004) for a review of the evidence on this question.", 8.0, 1, 620)
    blocks = [body, head, real] + junk
    s.classify(blocks, 11.0, {1: {"h": 702.0}}, 1)
    assert head["type"] == "heading" and real["type"] == "note" and [b["type"] for b in junk] == ["frag", "frag"]


def test_small_type_set_into_the_text_is_an_annotation_not_a_paragraph():
    body = dict(text="A body paragraph with enough ordinary words to count as running text in this paper.", page=1, key=(1, 0),
                size=10.0, bold=0.0, mono=0, top=100, bottom=140, x0=60, x1=420, n_lines=4)
    ann = dict(text="= π(y | x), using Thm. 1 reparam.", page=1, key=(1, 0), size=7.0, bold=0.0, mono=0, top=300, bottom=308,
               x0=250, x1=350, n_lines=1)
    later = dict(body, top=500, bottom=540)
    s.classify([body, ann, later], 10.0, {1: {"h": 792.0}}, 1)
    assert body["type"] == "para" and ann["type"] == "frag"


def test_footnote_heavy_paper_is_not_flagged_but_notes_high_on_the_page_are():
    def blk(top):
        return dict(type="note", text="See the earlier discussion of this point in the first section of the paper.",
                    page=1, top=top, bottom=top + 20, ph=666)
    paras = good_blocks(30)
    assert s.layout_signals(paras + [blk(560 + i) for i in range(25)], 3)[1] == []
    assert any("footnotes" in r for r in s.layout_signals(paras + [blk(80 + 20 * i) for i in range(10)], 3)[1])
