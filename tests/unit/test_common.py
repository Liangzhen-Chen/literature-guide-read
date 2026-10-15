import json
import pytest
import common as c

@pytest.mark.parametrize('text,anchor,span', [
    ('The “claim” holds.', '"claim"', (5,10)), ('a–b', 'a-b', (0,3)),
    ('a ﬁrm', 'FIRM', (2,5)), ('a  b', 'a b', (0,4)),
    ('中文 没有空格', '中文没有空格', (0,7)), ('abc', 'absent', None),
    ('abc', '', None), ('a\u200bb', 'ab', (0,3)), ('…', '...', (0,1))])
def test_anchor(text, anchor, span):
    assert c.find_anchor(text, anchor) == span

@pytest.mark.parametrize('value,expected', [('P3-P9',(3,9)),('P3–P9',(3,9)),('P3',(3,3)),('P3-9',(3,9))])
def test_range(value, expected):
    assert c.parse_range(value) == expected

@pytest.mark.parametrize('value', ['foo','P9-P3','3-9',''])
def test_bad_range(value):
    with pytest.raises(ValueError): c.parse_range(value)

def test_helpers():
    assert c.compress([4,3,1,3,7]) == 'P1, P3-P4, P7'
    assert c.compress([]) == ''
    assert c.as_lang(None,'en') == {}
    assert c.as_lang('text','en') == {'en':'text'}
    assert c.as_lang({'en':3,'zh':None,'de':'x'},'en') == {'en':'3'}
    assert c.pnum('P12') == 12 and c.pnum('no') is None
    assert c.clean_text(' ﬁ\u00ad\t text\u00a0 ') == 'fi text'
    assert c.is_cjk('中') and not c.is_cjk('') and not c.is_cjk('A')
    assert c.fmt_num(3) == '3' and c.fmt_num(.5) == '0.5'
    assert c.suggest_anchor('A long sentence. A short one.', 'A short one.') == 'A short one.'

def test_numbers():
    assert c.numbers_in('1,234.5 .001 2.25–2.75 2:1') == {1234.5,.001,2.25,2.75,2,1}
    assert c.numbers_in('P12 Figure 2 Table 1 Experiment 1 第 3 页') == set()
    assert c.source_numbers('three twice half 二十三 两 一万二千') == {3,2,.5,23,12000}

def test_merge(tmp_path):
    a,b = tmp_path/'a.json',tmp_path/'b.json'
    a.write_text(json.dumps({'meta':{},'paras':{'P1':{'tier':'skim'}}}))
    b.write_text(json.dumps({'paras':{'P2':{'tier':'close'}}}))
    assert set(c.load_guide([a,b])['paras']) == {'P1','P2'}
    assert c.load_guide([a,a])['meta'] == {}
    b.write_text(json.dumps({'paras':{'P1':{'tier':'close'}}}))
    with pytest.raises(SystemExit, match='different content'): c.load_guide([a,b])

@pytest.mark.parametrize('data,message', [('[]','top level'), ('{"paras": []}', 'must be an object'), ('{bad','JSON error')])
def test_bad_json(tmp_path,data,message):
    p=tmp_path/'bad.json'; p.write_text(data)
    with pytest.raises(SystemExit,match=message): c.load_guide([p])

def test_meta_conflict(tmp_path):
    a,b=tmp_path/'a.json',tmp_path/'b.json'
    a.write_text('{"title":"a"}'); b.write_text('{"title":"b"}')
    with pytest.raises(SystemExit,match='field title'): c.load_guide([a,b])

def test_elements(tmp_path,monkeypatch):
    assert len(c.load_elements()) == 19
    (tmp_path/'references').mkdir()
    (tmp_path/'references/elements.md').write_text('### good | Good | 好 | 2 | facts\nDescription\n### malformed\nIgnored\n')
    monkeypatch.setattr(c,'SKILL_DIR',tmp_path)
    assert c.load_elements() == {'good':{'en':'Good','zh':'好','level':2,'family':'facts','desc':'Description'}}
    assert c.skill_version() == '?'
    (tmp_path/'CHANGELOG.md').write_text('## 0.3.0\n')
    assert c.skill_version() == '0.3.0'

def test_elements_malformed_level_skipped(tmp_path,monkeypatch):
    (tmp_path/'references').mkdir()
    (tmp_path/'references/elements.md').write_text('### bad | Bad | 错 | nope | facts\nIgnored\n### good | Good | 好 | 2 | facts\nKept\n')
    monkeypatch.setattr(c,'SKILL_DIR',tmp_path)
    assert set(c.load_elements()) == {'good'}


def test_inline_math_spans_versus_money():
    from common import inline_math_spans
    assert [m.group(1) for m in inline_math_spans('between $1 + \\eta$ and $1 + \\eta\\lambda$, except at $0$, and $1 - p_M$')] == ['1 + \\eta', '1 + \\eta\\lambda', '0', '1 - p_M']
    assert inline_math_spans('a salary of $50,000 against $60,000 expected') == []
    assert inline_math_spans('paid $5 - $3 more') == []
