import json
from pathlib import Path
import mineru_backend as mb

FIX = Path('tests/fixtures/mineru_structured_small.json')


def _doc():
    return mb.convert(json.loads(FIX.read_text()), 'list2003.pdf', '/x/list2003.pdf')


def test_convert_drops_running_heads_and_keeps_labels():
    d = _doc()
    texts = [i['text'] for i in d['items']]
    assert not any('QUARTERLY JOURNAL' in t for t in texts)
    assert d['page_labels']['9'] == '48'


def test_convert_equation_table_heading_note():
    d = _doc()
    eq = next(i for i in d['items'] if i.get('equation'))
    assert 'trade' in eq['tex'].replace(' ', '')
    assert eq['bbox'] == [0.104, 0.857, 0.622, 0.878]
    tab = next(i for i in d['items'] if i.get('table'))
    assert tab['html'].startswith('<table>') and any(i['type'] == 'caption' and i['text'].startswith('TABLE II') for i in d['items'])
    head = next(i for i in d['items'] if i['type'] == 'heading')
    assert head['level'] == 1 and head['text'].startswith('III.')
    note = next(i for i in d['items'] if i['type'] == 'note' and i.get('num'))
    assert note['num'] == 7 and note.get('ref', '').startswith('P')


def test_convert_merges_continuation():
    d = _doc()
    cont = [i for i in d['items'] if i['type'] == 'para' and i.get('pages')]
    assert cont and cont[0]['pages'] == [9, 10]


def test_convert_without_page_numbers():
    sc = json.loads(FIX.read_text())
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
    sc = json.loads(FIX.read_text())
    sc['pages'][0]['blocks'].insert(0, {'type': 'paragraph_title', 'level': None, 'content': 'Appendix', 'bbox': [0.1, 0.1, 0.5, 0.12]})
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert any(i['type'] == 'heading' and i['text'] == 'Appendix' and i['level'] == 1 for i in d['items'])


def test_convert_drops_empty_and_stray_math_footnotes():
    # Kőszegi & Rabin (2006) scan: MinerU emitted footnote blocks holding "" or stray symbols such as "μ(·)"
    sc = json.loads(FIX.read_text())
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


LONG = 'We develop a model of reference-dependent preferences and loss aversion where gain-loss utility is derived from standard consumption utility. ' * 3


def test_convert_journal_masthead_is_not_the_title():
    # Kőszegi & Rabin (2006), QJE scan: MinerU labelled the journal masthead doc_title; the article title is the running head
    sc = _pages(
        [_b('doc_title', 'THE QUARTERLY JOURNAL OF ECONOMICS', 0.04, 0.14), _b('text', 'Vol. CXXI November 2006 Issue 4', 0.16),
         _b('text', 'A MODEL OF REFERENCE-DEPENDENT PREFERENCES* BOTOND KŐSZEGI AND MATTHEW RABIN', 0.21, 0.26), _b('text', LONG, 0.28, 0.47),
         _b('paragraph_title', 'I. INTRODUCTION', 0.5, level=2), _b('text', LONG, 0.52, 0.58)],
        [_b('header', 'QUARTERLY JOURNAL OF ECONOMICS', 0.06), _b('text', LONG, 0.1, 0.3)],
        [_b('header', 'A MODEL OF REFERENCE-DEPENDENT PREFERENCES', 0.06), _b('text', LONG, 0.1, 0.3)],
        [_b('header', 'QUARTERLY JOURNAL OF ECONOMICS', 0.06), _b('text', LONG, 0.1, 0.3)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert d['title_guess'] == 'A MODEL OF REFERENCE-DEPENDENT PREFERENCES'
    assert not any(i['type'] == 'heading' and 'QUARTERLY' in i['text'] for i in d['items'])


def test_convert_numbered_text_at_page_bottom_is_a_footnote():
    # the same scan: footnote 2 came back as a text block at the foot of the page
    sc = _pages([_b('paragraph_title', 'II. UTILITY', 0.28, level=2), _b('text', 'If c is drawn according to the probability measure F, the person\'s utility is given by2', 0.31, 0.4),
                 _b('text', LONG, 0.47, 0.58),
                 _b('text', '2. Despite the clear evidence that people\'s evaluation of prospects is not linear in probabilities, our model simplifies things by assuming preferences are linear.', 0.79, 0.83),
                 _b('footer', 'This content downloaded from JSTOR', 0.91)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    note = next((i for i in d['items'] if i['type'] == 'note'), None)
    assert note and note['num'] == 2 and note['text'].startswith('Despite') and note.get('ref') == 'P1'
    assert sum(i['type'] == 'para' for i in d['items']) == 2


def test_convert_joins_paragraph_cut_by_page_break_without_flag():
    # the same scan: "...mixture of these" / "two feelings.3 That a person's utility..." with no continues_prev
    sc = _pages([_b('paragraph_title', 'II. UTILITY', 0.05, level=2), _b('text', LONG, 0.1, 0.3), _b('text', 'This formulation captures the notion that the overall sensation is a mixture of these', 0.65, 0.75)],
                [_b('header', 'QUARTERLY JOURNAL OF ECONOMICS', 0.06), _b('text', 'two feelings.3 That a person\'s utility depends on a reference lottery is similar to several previous theories.', 0.1, 0.2), _b('text', LONG, 0.22, 0.4)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    paras = [i['text'] for i in d['items'] if i['type'] == 'para']
    assert len(paras) == 3 and 'mixture of these two feelings.3 That' in paras[1]


def test_convert_equation_label_alone_is_a_fragment():
    # List (2003): "(2a)" became a paragraph of its own
    sc = _pages([_b('paragraph_title', 'III. MODEL', 0.05, level=2), _b('text', LONG, 0.1, 0.3), _b('text', '(2a)', 0.32), _b('equation', '', 0.33, 0.4)])
    d = mb.convert(sc, 'x.pdf', '/x.pdf')
    assert [i['type'] for i in d['items'] if i['text'] == '(2a)'] == ['frag']
