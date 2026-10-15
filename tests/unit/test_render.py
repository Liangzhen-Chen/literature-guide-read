import json
from types import SimpleNamespace
import pytest
import render as r
from check import run_checks

@pytest.mark.parametrize('text,key',[('Figure 2. Test',['fig',2]),('表 3 示例',['table',3]),('body',None)])
def test_cap_key(text,key): assert r.cap_key(text)==key

def test_mentions(): assert r.mentions('Figure 2 and Table 3; 图4 表5')==[['fig',2],['table',3],['fig',4],['table',5]]

def test_build(clean):
    doc,g=clean
    doc['items'][0]['text'] += ' Figure 1 shows choices.'
    doc['items'][1]['text'] += ' Figure 1 repeats choices.'
    doc['items'].insert(1,{'id':'C1','type':'caption','text':'Figure 1. Choices','page':2})
    doc['items'].insert(2,{'id':'F1','type':'frag','text':'10 20','page':2,'table':True})
    _,_,comp=run_checks(doc,g)
    d=r.build_data(doc,g,comp,None,{},None)
    assert d['figs']['C1']['host']=='P1' and d['table_pages']=={'P1':2}
    assert d['logic']['rels']['A']==g['parts'][0]['rel']
    assert d['logic']['flows']['A'][0]['x']=={'en':'Buyers choose.'}

def test_roundtrip(clean,tmp_path):
    doc,g=clean
    args=SimpleNamespace(density=None,force=False,sources=None,no_page_images=True,pdf=None,lang=None)
    a,b=tmp_path/'a.html',tmp_path/'b.html'
    r.render(doc,g,a,args)
    r.dump(a,tmp_path/'dump')
    r.render(json.loads((tmp_path/'dump/paragraphs.json').read_text()),json.loads((tmp_path/'dump/guide.json').read_text()),b,args)
    assert json.loads(r.DATA_RE.search(a.read_text()).group(1)) == json.loads(r.DATA_RE.search(b.read_text()).group(1))


def _with_formula(clean, bbox=True):
    doc, g = clean
    doc['items'][0]['text'] = 'The share is s = 3 / 5, so three in five buyers chose it.'
    if bbox:
        doc['items'][0]['bbox'] = [0.1, 0.1, 0.9, 0.2]
    g['paras']['P1']['els'] = [{'t': 'formula', 'a': 's = 3 / 5', 'tex': 's = \\frac{3}{5}', 'syms': [{'s': 's', 'm': 'share'}], 'x': 'three in five', 'why': 'baseline'}]
    return doc, g


def test_build_formula_fields_and_flags(clean):
    doc, g = _with_formula(clean)
    _, _, comp = run_checks(doc, g)
    d = r.build_data(doc, g, comp, None, {}, None, crops={'P1': 'data:image/png;base64,AAAA'})
    e = d['guide']['P1']['els'][0]
    assert e['tex'] == 's = \\frac{3}{5}' and e['syms'] == [{'s': 's', 'm': {'en': 'share'}}] and e['why'] == {'en': 'baseline'}
    assert d['has_tex'] is True and d['crops'] == {'P1': 'data:image/png;base64,AAAA'}


def test_build_formula_without_bbox(clean):
    doc, g = _with_formula(clean, bbox=False)
    _, _, comp = run_checks(doc, g)
    d = r.build_data(doc, g, comp, None, {}, None)
    assert d['has_tex'] is True and d['crops'] == {}


def test_render_inlines_katex_only_with_tex(clean, tmp_path):
    args = SimpleNamespace(density=None, force=False, sources=None, no_page_images=True, pdf=None, lang=None)
    doc, g = clean
    r.render(doc, g, tmp_path / 'plain.html', args)
    plain = (tmp_path / 'plain.html').read_text()
    assert 'data:font/woff2' not in plain and '__KATEX__' not in plain and 'function(e,t)' not in plain
    doc, g = _with_formula(clean, bbox=False)
    r.render(doc, g, tmp_path / 'math.html', args)
    html = (tmp_path / 'math.html').read_text()
    assert 'KaTeX' in html and 'data:font/woff2' in html and '__KATEX__' not in html


def test_roundtrip_tex(clean, tmp_path):
    args = SimpleNamespace(density=None, force=False, sources=None, no_page_images=True, pdf=None, lang=None)
    doc, g = _with_formula(clean, bbox=False)
    g['paras']['P1']['els'][0]['tex'] = 'a </script> \\\\ b'
    a, b = tmp_path / 'a.html', tmp_path / 'b.html'
    r.render(doc, g, a, args)
    r.dump(a, tmp_path / 'dump')
    r.render(json.loads((tmp_path / 'dump/paragraphs.json').read_text()), json.loads((tmp_path / 'dump/guide.json').read_text()), b, args)
    assert json.loads(r.DATA_RE.search(a.read_text()).group(1)) == json.loads(r.DATA_RE.search(b.read_text()).group(1))


def test_roundtrip_crops(clean, tmp_path):
    args = SimpleNamespace(density=None, force=False, sources=None, no_page_images=True, pdf=None, lang=None)
    doc, g = _with_formula(clean)
    work = tmp_path / 'work'; (work / 'crops').mkdir(parents=True)
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 20
    (work / 'crops' / 'P1.png').write_bytes(png)
    doc['crops'] = {'P1': 'crops/P1.png'}
    a = tmp_path / 'a.html'
    r.render(doc, g, a, args, work_dir=work)
    r.dump(a, tmp_path / 'dump')
    d2 = json.loads((tmp_path / 'dump/paragraphs.json').read_text())
    assert d2['crops'] == {'P1': 'crops/P1.png'} and (tmp_path / 'dump/crops/P1.png').read_bytes() == png
    b = tmp_path / 'b.html'
    r.render(d2, json.loads((tmp_path / 'dump/guide.json').read_text()), b, args, work_dir=tmp_path / 'dump')
    assert json.loads(r.DATA_RE.search(a.read_text()).group(1))['crops'] == json.loads(r.DATA_RE.search(b.read_text()).group(1))['crops']


def test_table_crop_attaches_to_citing_paragraph(clean):
    doc, g = clean
    doc['items'][0]['text'] += ' Table 1 lists the choices.'
    doc['items'].insert(2, {'id': 'C1', 'type': 'caption', 'text': 'Table 1. Choices', 'page': 1})
    doc['items'].insert(3, {'id': 'F1', 'type': 'frag', 'text': '10 20', 'page': 1, 'table': True, 'bbox': [0.1, 0.1, 0.9, 0.2]})
    _, _, comp = run_checks(doc, g)
    d = r.build_data(doc, g, comp, None, {}, None, crops={'F1': 'data:image/png;base64,AAAA'})
    assert d['frag_crops'] == {'P1': ['F1']}


def test_katex_placeholder_in_text_does_not_break_page(clean, tmp_path):
    args = SimpleNamespace(density=None, force=False, sources=None, no_page_images=True, pdf=None, lang=None)
    doc, g = _with_formula(clean, bbox=False)
    doc['items'][1]['text'] = 'A paragraph that literally says __KATEX__ and __DATA__.'
    g['paras']['P2']['note'] = 'Says __KATEX__.'
    out = tmp_path / 'k.html'
    r.render(doc, g, out, args)
    html = out.read_text()
    assert html.count('<script id="guide-data"') == 1
    assert json.loads(r.DATA_RE.search(html).group(1))['items']['P2']['text'].endswith('__DATA__.')


def test_build_recall_and_glossary(clean):
    doc, g = clean
    g['parts'][0]['recall'] = [{'q': 'Who chose?', 'a': 'Three buyers.'}]
    g['paras']['P1']['els'] = [{'t': 'def', 'term': 'reward', 'a': 'smaller reward', 'x': 'the payment offered'},
                               {'t': 'formula', 'a': 'Three buyers', 'tex': 's = 1', 'syms': [{'s': 'share', 'm': 'the fraction'}]}]
    _, _, comp = run_checks(doc, g)
    d = r.build_data(doc, g, comp, None, {}, None)
    assert d['parts'][0]['recall'] == [{'q': {'en': 'Who chose?'}, 'a': {'en': 'Three buyers.'}}]
    assert {'term': 'reward', 'x': {'en': 'the payment offered'}, 'src': 'P1'} in d['glossary']
    assert {'term': 'share', 'x': {'en': 'the fraction'}, 'src': 'P1'} in d['glossary']


def test_roundtrip_recall(clean, tmp_path):
    args = SimpleNamespace(density=None, force=False, sources=None, no_page_images=True, pdf=None, lang=None)
    doc, g = clean
    g['parts'][0]['recall'] = [{'q': 'Who chose?', 'a': 'Three buyers.'}]
    a, b = tmp_path / 'a.html', tmp_path / 'b.html'
    r.render(doc, g, a, args)
    r.dump(a, tmp_path / 'dump')
    assert json.loads((tmp_path / 'dump/guide.json').read_text())['parts'][0]['recall'][0]['q'] == {'en': 'Who chose?'}
    r.render(json.loads((tmp_path / 'dump/paragraphs.json').read_text()), json.loads((tmp_path / 'dump/guide.json').read_text()), b, args)
    assert json.loads(r.DATA_RE.search(a.read_text()).group(1))['parts'] == json.loads(r.DATA_RE.search(b.read_text()).group(1))['parts']


def test_build_reader_brief(clean):
    doc, g = clean
    g['meta'].update({'purpose': 'core claims only', 'familiarity': 'new to the field'})
    g['questions'] = [{'q': 'Do buyers prefer small rewards?', 'a': 'Yes.', 'p': ['P1']}]
    _, _, comp = run_checks(doc, g)
    d = r.build_data(doc, g, comp, None, {}, None)
    assert d['meta']['purpose'] == {'en': 'core claims only'} and d['meta']['familiarity'] == {'en': 'new to the field'}
    assert d['questions'] == [{'q': {'en': 'Do buyers prefer small rewards?'}, 'a': {'en': 'Yes.'}, 'p': ['P1']}]
