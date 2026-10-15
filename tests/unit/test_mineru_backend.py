import json
from pathlib import Path
import mineru_backend as mb

FIX = Path(__file__).resolve().parent.parent / 'fixtures' / 'mineru_structured_small.json'


def _doc():
    return mb.convert(json.loads(FIX.read_text(encoding='utf-8')), 'ioannidis2005.pdf', '/x/ioannidis2005.pdf')


def test_convert_drops_running_heads_and_keeps_labels():
    d = _doc()
    texts = [i['text'] for i in d['items']]
    assert not any('Open access, freely available online' in t for t in texts)
    assert not any('plosmedicine.org' in t for t in texts)
    assert d['page_labels']['1'] == '696' and d['page_labels']['2'] == '697'


def test_convert_equation_table_heading_note():
    d = _doc()
    eq = next(i for i in d['items'] if i.get('equation'))
    assert 'PPV' in eq['tex'].replace(' ', '')
    assert eq['bbox'] == [0.104, 0.857, 0.622, 0.878]
    tab = next(i for i in d['items'] if i.get('table'))
    assert tab['html'].startswith('<table>') and any(i['type'] == 'caption' and i['text'].startswith('Table 1') for i in d['items'])
    head = next(i for i in d['items'] if i['type'] == 'heading')
    assert head['level'] == 1 and head['text'].startswith('Modeling the Framework')
    note = next(i for i in d['items'] if i['type'] == 'note' and i.get('num'))
    assert note['num'] == 13 and note.get('ref', '').startswith('P')


def test_convert_merges_continuation():
    d = _doc()
    cont = [i for i in d['items'] if i['type'] == 'para' and i.get('pages')]
    assert cont and cont[0]['pages'] == [1, 2]


def test_convert_without_page_numbers():
    sc = json.loads(FIX.read_text(encoding='utf-8'))
    for pg in sc['pages']:
        pg['blocks'] = [b for b in pg['blocks'] if b['type'] != 'page_number']
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert d['page_labels'] == {} and d['items']


def test_available_returns_none_when_no_mineru(monkeypatch):
    monkeypatch.setenv('MINERU_PYTHON', '/nonexistent/python')
    monkeypatch.setattr(mb.shutil, 'which', lambda name: None)
    monkeypatch.setattr(mb, '_can_import', lambda py: False)
    assert mb.available() is None


def test_convert_heading_with_null_level():
    sc = json.loads(FIX.read_text(encoding='utf-8'))
    sc['pages'][0]['blocks'].insert(0, {'type': 'paragraph_title', 'level': None, 'content': 'Appendix', 'bbox': [0.1, 0.1, 0.5, 0.12]})
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert any(i['type'] == 'heading' and i['text'] == 'Appendix' and i['level'] == 1 for i in d['items'])


def test_convert_drops_empty_and_stray_math_footnotes():
    # scans: MinerU emitted footnote blocks holding "" or stray symbols such as "μ(·)"
    sc = json.loads(FIX.read_text(encoding='utf-8'))
    sc['pages'][0]['blocks'] += [{'type': 'page_footnote', 'content': '', 'bbox': [0.1, 0.9, 0.5, 0.92]},
                                 {'type': 'page_footnote', 'content': 'μ(·)', 'bbox': [0.1, 0.92, 0.5, 0.94]},
                                 {'type': 'page_footnote', 'content': '8. A real note.', 'bbox': [0.1, 0.94, 0.5, 0.96]}]
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    notes = [i['text'] for i in d['items'] if i['type'] == 'note']
    assert '' not in notes and 'μ(·)' not in notes and any('A real note' in t for t in notes)


def _pages(*pages):
    return {'pages': [{'page_idx': i, 'blocks': bs} for i, bs in enumerate(pages)]}


def _b(t, content, y0, y1=None, **kw):
    return dict({'type': t, 'content': content, 'bbox': [0.11, y0, 0.89, y1 or y0 + 0.03]}, **kw)


LONG = 'Research findings are defined here as any relationship reaching formal statistical significance, e.g., effective interventions, informative predictors, risk factors, or associations. ' * 3


def test_convert_journal_masthead_is_not_the_title():
    # a scan whose journal masthead MinerU labelled doc_title; the article title is the alternate running head
    sc = _pages(
        [_b('doc_title', 'PLoS Medicine', 0.04, 0.14), _b('text', 'August 2005 | Volume 2 | Issue 8 | e124', 0.16),
         _b('text', 'Why Most Published Research Findings Are False John P. A. Ioannidis', 0.21, 0.26), _b('text', LONG, 0.28, 0.47),
         _b('paragraph_title', 'Modeling the Framework for False Positive Findings', 0.5, level=2), _b('text', LONG, 0.52, 0.58)],
        [_b('header', 'PLoS Medicine', 0.06), _b('text', LONG, 0.1, 0.3)],
        [_b('header', 'Why Most Published Research Findings Are False', 0.06), _b('text', LONG, 0.1, 0.3)],
        [_b('header', 'PLoS Medicine', 0.06), _b('text', LONG, 0.1, 0.3)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert d['title_guess'] == 'Why Most Published Research Findings Are False'
    assert not any(i['type'] == 'heading' and 'PLoS Medicine' in i['text'] for i in d['items'])


def test_convert_numbered_text_at_page_bottom_is_a_footnote():
    # the same scan: a footnote came back as a text block at the foot of the page
    sc = _pages([_b('paragraph_title', 'Modeling the Framework for False Positive Findings', 0.28, level=2),
                 _b('text', 'The PPV is also the complementary probability of what Wacholder et al. have called the false positive report probability.10', 0.31, 0.4),
                 _b('text', LONG, 0.47, 0.58),
                 _b('text', '10. Wacholder S, Chanock S, Garcia-Closas M, Elghormli L, Rothman N (2004) Assessing the probability that a positive report is false: An approach for molecular epidemiology studies. J Natl Cancer Inst 96: 434–442.', 0.79, 0.83),
                 _b('footer', 'PLoS Medicine | www.plosmedicine.org 0696 August 2005 | Volume 2 | Issue 8 | e124', 0.91)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    note = next((i for i in d['items'] if i['type'] == 'note'), None)
    assert note and note['num'] == 10 and note['text'].startswith('Wacholder') and note.get('ref') == 'P1'
    assert sum(i['type'] == 'para' for i in d['items']) == 2


def test_convert_joins_paragraph_cut_by_page_break_without_flag():
    # the same scan: "...is thus" / "more likely true than false..." with no continues_prev
    sc = _pages([_b('paragraph_title', 'Modeling the Framework for False Positive Findings', 0.05, level=2), _b('text', LONG, 0.1, 0.3), _b('text', 'According to the 2 × 2 table, one gets PPV = (1 − β)R/(R − βR + α). A research finding is thus', 0.65, 0.75)],
                [_b('header', 'Open access, freely available online', 0.06), _b('text', 'more likely true than false if (1 − β)R > α. Since usually the vast majority of investigators depend on α = 0.05, this means that a research finding is more likely true than false if (1 − β)R > 0.05.', 0.1, 0.2), _b('text', LONG, 0.22, 0.4)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    paras = [i['text'] for i in d['items'] if i['type'] == 'para']
    assert len(paras) == 3 and 'A research finding is thus more likely true than false if (1 − β)R > α. Since' in paras[1]


def test_convert_equation_label_alone_is_a_fragment():
    # an equation label such as "(2a)" on a line of its own became a paragraph
    sc = _pages([_b('paragraph_title', 'Bias', 0.05, level=2), _b('text', LONG, 0.1, 0.3), _b('text', '(2a)', 0.32), _b('equation', '', 0.33, 0.4)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert [i['type'] for i in d['items'] if i['text'] == '(2a)'] == ['frag']
