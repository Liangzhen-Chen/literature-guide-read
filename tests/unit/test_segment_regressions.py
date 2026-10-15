"""Source-reviewed regressions: PLOS pagination, ACM section lines, mixed scans."""
import segment as s


def line(text, top=100, x0=50, x1=400, size=10):
    return dict(text=text, top=top, bottom=top+10, x0=x0, x1=x1,
                size=size, bold=0, mono=0, band=0, col=0)


def test_page_fraction_uses_current_page_not_total():
    pages=[dict(pno=p,h=800,lines=[line('PLOS ONE | https://doi.org/10.1371/journal.pone.0225883 December 18, 2019 '+str(p)+' / 13',top=770)]) for p in [1,2,3]]
    labels=[]
    s.strip_margins(pages,lambda p:p['lines'],lambda p,v:p.update(lines=v),labels)
    assert s.page_labels_from(labels,[1,2,3]) == {'1':'1','2':'2','3':'3'}


def test_numbered_heading_is_separate_from_body_with_same_size():
    blocks=s.build_blocks([line('1 INTRODUCTION'),line('Sparse tensors are essential in scientific applications.',top=112)],1,10)
    assert [b['text'] for b in blocks] == ['1 INTRODUCTION','Sparse tensors are essential in scientific applications.']


def test_numbered_subheading_is_separate_from_other_heading():
    blocks=s.build_blocks([line('2 BACKGROUND'),line('2.1 Automatic Differentiation',top=112),line('Automatic differentiation computes function gradients.',top=124)],1,10)
    assert len(blocks)==3


def test_auto_ocr_decides_each_page_from_usable_words():
    class Page:
        def __init__(self,words): self.words=words
    class Pdf: pages=[Page([]),Page([{'text':'Body text '*10}]),Page([])]
    original=s.get_words
    try:
        s.get_words=lambda page:page.words
        assert s.ocr_page_numbers(Pdf(),[1,2,3],'auto') == [1,3]
        assert s.ocr_page_numbers(Pdf(),[1,2,3],'off') == []
        assert s.ocr_page_numbers(Pdf(),[1,2,3],'on') == [1,2,3]
    finally: s.get_words=original


def test_narrow_small_font_sidebar_detected_without_equal_columns():
    segs=[line('Publisher metadata has several lines',top=100+i*12,x0=36,x1=184,size=8) for i in range(12)]
    segs += [line('The main article continues independently of metadata.',top=100+i*12,x0=200,x1=575,size=10) for i in range(16)]
    assert 184 < s.detect_sidebar(segs,612) < 200
    for ln in segs[:12]: ln['size']=10
    assert s.detect_sidebar(segs,612) is None


def test_chinese_abstract_heading_and_dense_prose_are_not_table_rows():
    texts=['摘要','本研究通过问卷调查的方式，以475名大学生为对象，探索开放性人格对创造力的影响，以及归因风格',
           '的作用。研究结果表明，开放性与创造力存在显著的正相关，开放性可以显著正向预测个体的创造力。',
           '本研究揭示了归因风格对大学生创造力的部分影响机制，为创造力培养提供依据。']
    blocks=[dict(line(t,top=200+i*12),n_lines=1,page=1) for i,t in enumerate(texts)]
    s.classify(blocks,10,{1:{'h':800}},1)
    assert blocks[0]['type']=='heading'
    assert all(b['type']=='para' for b in blocks[1:])


def test_sidebar_metadata_never_classified_as_main_prose():
    b=dict(line('Citation: Jones and Smith (2023) A long publisher citation and publication metadata.'),n_lines=1,page=1,sidebar=True)
    s.classify([b],10,{1:{'h':800}},1)
    assert b['type']=='frag'


def test_bold_abstract_sentence_is_not_a_heading():
    b=dict(text='In this study, a questionnaire survey was conducted among 475 college students to explore the in-',size=10,bold=1,n_lines=1)
    assert not s.is_heading_block(b,10)


def _page(pno, h, lines):
    return {'pno': pno, 'h': h, 'lines': [{'text': t, 'top': top, 'bottom': top + 8} for t, top in lines]}


def test_strip_margins_removes_running_head_at_twelve_percent():
    # List (2003), QJE: running heads sit at 12.1% of a 652pt page, outside the old 8.5% band
    pages = [_page(p, 652, [('42 QUARTERLY JOURNAL OF ECONOMICS' if p % 2 else 'DOES MARKET EXPERIENCE ELIMINATE ANOMALIES? 43', 79),
                             ('theory to doubt the validity of certain neoclassical models', 106)]) for p in (2, 3, 4, 5)]
    labels = []
    removed = s.strip_margins(pages, lambda p: p['lines'], lambda p, v: p.update(lines=v), labels)
    assert removed == 4
    assert all(len(p['lines']) == 1 and p['lines'][0]['text'].startswith('theory') for p in pages)
    assert (2, '43') in labels and (3, '42') in labels


def test_strip_margins_keeps_unique_body_lines():
    # tight margins: a different first body line on every page inside the 15% band must survive
    pages = [_page(p, 652, [(f'Body sentence number {p} that differs on every page.', 70)]) for p in (1, 2, 3, 4)]
    labels = []
    assert s.strip_margins(pages, lambda p: p['lines'], lambda p, v: p.update(lines=v), labels) == 0
    assert all(len(p['lines']) == 1 for p in pages)


def _hb(text, size=10.0, bold=0.0, n_lines=1):
    return {'text': text, 'size': size, 'bold': bold, 'n_lines': n_lines}


def test_page_first_continuation_line_is_not_a_heading():
    # JSTOR OCR layers give the first line of a page a slightly larger size; it is still body text
    assert not s.is_heading_block(_hb('tober 1994. The sheet has market value since it is a unique', size=11.2), 10.0)
    assert not s.is_heading_block(_hb('To provide insights into how the findings herein could', size=11.2), 10.0)
    assert s.is_heading_block(_hb('VI. Evidence from Nonmemorabilia Collectors', size=11.2), 10.0)
    assert s.is_heading_block(_hb('Evidence from Nonmemorabilia Collectors', size=11.2), 10.0)


def _blk(text, typ='para', page=1):
    return {'type': typ, 'text': text, 'page': page}


def test_roman_rewrite_suppressed_when_document_uses_roman_numerals():
    blocks = [_blk('Table II reports the pooled sample.'), _blk('Results of Experiment I are in Table I.')]
    items, counters = s.finalize(blocks)
    assert items[1]['text'] == 'Results of Experiment I are in Table I.'
    assert counters['roman_rewrites'] == 0


def test_roman_rewrite_reports_count():
    blocks = [_blk('See Figure l for the design.'), _blk('Question l asked about the mug.')]
    items, counters = s.finalize(blocks)
    assert items[0]['text'] == 'See Figure 1 for the design.'
    assert counters['roman_rewrites'] == 2


def test_finalize_keeps_normalised_bbox_and_marks_equations():
    blocks = [{'type': 'para', 'text': 'The model is estimated as', 'page': 1, 'x0': 60, 'top': 100, 'x1': 540, 'bottom': 140, 'pw': 600, 'ph': 800},
              {'type': 'frag', 'text': '(1) trade = g(a + b X),', 'page': 1, 'x0': 60, 'top': 150, 'x1': 300, 'bottom': 165, 'pw': 600, 'ph': 800},
              {'type': 'frag', 'text': 'Dealers Nondealers', 'page': 1, 'x0': 60, 'top': 200, 'x1': 300, 'bottom': 212, 'pw': 600, 'ph': 800, 'table': True}]
    items, _ = s.finalize(blocks)
    assert items[0]['bbox'] == [0.1, 0.125, 0.9, 0.175]
    assert items[1]['equation'] is True and items[1]['bbox'][1] == 0.1875
    assert 'equation' not in items[2] and items[2]['table'] is True


def _offset_text_pdf(path):
    """One page, MediaBox starting at y=40, with the text EQUATION=X near the top (true distance 216-240pt of 300)."""
    content = b"BT /F1 24 Tf 20 100 Td (EQUATION=X) Tj ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 40 200 340] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def test_text_layer_coordinates_are_page_relative(tmp_path):
    import pdfplumber
    pdf = tmp_path / 'offset.pdf'; _offset_text_pdf(pdf)
    with pdfplumber.open(str(pdf)) as doc:
        page = doc.pages[0]
        w = s.get_words(page)[0]
        assert 210 < w['top'] < 225 and 236 < w['bottom'] < 245, (w['top'], w['bottom'])  # distance from the top of the page
        assert page.crop((w['x0'], w['top'], w['x1'], w['bottom']), relative=True).extract_text() == 'EQUATION=X'


def test_caption_lines_in_outer_band_survive():
    # "Table 1" and "Table 2" share a digit-stripped key but are captions, not running heads
    pages = [_page(p, 800, [(f'Table {p // 2}', 90), ('Body text that follows the table on this page.', 300)]) for p in (2, 4, 6)]
    labels = []
    assert s.strip_margins(pages, lambda p: p['lines'], lambda p, v: p.update(lines=v), labels) == 0
    assert labels == []


def test_roman_suppressed_is_reported():
    items, counters = s.finalize([_blk('Table II reports it.'), _blk('See Figure l.')])
    assert counters['roman_suppressed'] is True and items[1]['text'] == 'See Figure l.'
    _, counters = s.finalize([_blk('See Figure l.')])
    assert counters['roman_suppressed'] is False


def test_auto_engine_falls_back_when_mineru_fails(tmp_path, monkeypatch, capsys, sample_pdf):
    import sys as _sys
    import mineru_backend as mb
    monkeypatch.setattr(mb, 'available', lambda python=None: _sys.executable)
    def boom(*a, **k): raise SystemExit('MinerU failed:\nno models')
    monkeypatch.setattr(mb, 'run', boom)
    monkeypatch.setattr(_sys, 'argv', ['segment.py', str(sample_pdf), '--out', str(tmp_path / 'out'), '--pages', '1-1'])
    s.main()
    out = capsys.readouterr().out
    assert '模式：PDF 文字层' in out and 'pdfplumber' in out
    assert (tmp_path / 'out' / 'paragraphs.json').exists()


def _cb(text, top, page=1, size=10.0):
    return {'type': 'para', 'text': text, 'page': page, 'size': size, 'bold': 0.0, 'mono': 0.0, 'n_lines': 1,
            'top': top, 'bottom': top + 12, 'x0': 100, 'x1': 400, 'key': (0, 0)}


def test_display_equation_lines_are_not_table_rows():
    # Attention (1): a fraction's numerator, the equation line and the denominator form three short lines
    blocks = [_cb('We compute the dot products of the', 100), _cb('QK T', 120), _cb('Attention( Q, K, V ) = softmax( √ ) V (1)', 132),
              _cb('d k', 144), _cb('While for small values of d k the two mechanisms perform similarly.', 170)]
    s.classify(blocks, 10.0, {1: {'h': 800, 'w': 600, 'figs': []}}, 1)
    assert not any(b.get('table') for b in blocks)
    assert blocks[2]['type'] == 'frag' and s.is_display_equation(blocks[2])


def test_numeric_rows_still_become_a_table():
    blocks = [_cb('1 512 512 5.29 24.9', 100), _cb('2 256 1024 4.80 23.1', 112), _cb('3 128 2048 4.50 22.0', 124)]
    s.classify(blocks, 10.0, {1: {'h': 800, 'w': 600, 'figs': []}}, 1)
    assert all(b.get('table') for b in blocks)


def test_math_dense_paragraph_is_marked():
    items, _ = s.finalize([_blk('MultiHead( Q, K, V ) = Concat(head 1 , ..., head h ) W O where head i = Attention( QW i Q , KW i K , V W i V )'),
                           _blk('The share of buyers who traded was 32.8 percent, which is below one half.')])
    assert items[0].get('has_math') is True and 'has_math' not in items[1]


def test_strip_margins_three_pages_alternating_heads():
    # three pages: the odd-page head repeats, the even-page head appears once but sits at the same height
    pages = [_page(p, 652, [('42 QUARTERLY JOURNAL OF ECONOMICS' if p % 2 else 'DOES MARKET EXPERIENCE ELIMINATE ANOMALIES? 43', 40),
                             ('theory to doubt the validity of certain neoclassical models', 106)]) for p in (1, 2, 3)]
    labels = []
    removed = s.strip_margins(pages, lambda p: p['lines'], lambda p, v: p.update(lines=v), labels)
    assert removed == 3
    assert all(len(p['lines']) == 1 and p['lines'][0]['text'].startswith('theory') for p in pages)
    assert (2, '43') in labels


def test_strip_margins_first_page_title_at_head_row_survives():
    # the article title sits where the running head sits on later pages; it is not a running head
    pages = [_page(1, 652, [('DOES MARKET EXPERIENCE ELIMINATE MARKET ANOMALIES?', 40), ('JOHN A. LIST', 60)])]
    pages += [_page(p, 652, [('42 QUARTERLY JOURNAL OF ECONOMICS', 40), ('theory to doubt the validity', 106)]) for p in (2, 3)]
    labels = []
    s.strip_margins(pages, lambda p: p['lines'], lambda p, v: p.update(lines=v), labels)
    assert [l['text'] for l in pages[0]['lines']] == ['DOES MARKET EXPERIENCE ELIMINATE MARKET ANOMALIES?', 'JOHN A. LIST']
