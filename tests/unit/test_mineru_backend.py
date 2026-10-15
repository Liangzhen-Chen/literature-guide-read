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
