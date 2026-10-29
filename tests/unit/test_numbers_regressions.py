import pytest
import common
from check import run_checks

@pytest.mark.parametrize('text,expected',[
 ('N(496,114)',{496,114}),
 ('N(496, 114)',{496,114}),
 ('N(49.6,114)',{49.6,114}),
 ('N(-496,114)',{496,114}),
 ('There were 496,114 observations.',{496114}),
 ('A total (496,114) was recorded.',{496114}),
])
def test_distribution_comma_is_not_thousands(text,expected):
    assert common.numbers_in(text)==expected

def test_distribution_note_allowed_by_stated_parameters(clean):
    doc,g=clean
    doc['items'][0]['text']='The mean is 496 and the standard deviation is 114.'
    g['paras']['P1']={'tier':'skim','role':'Normal model','note':'The normal model is N(496,114).'}
    errors,_,_=run_checks(doc,g)
    assert not any('496114' in e for e in errors)


def test_cjk_table_reference_does_not_split_a_decimal():
    # "表 24.03" is a statistic, not a reference to Table 24
    from common import numbers_in
    assert numbers_in('4 × 3 表 24.03') == {4.0, 3.0, 24.03}


def test_equation_references_are_not_data():
    from common import numbers_in
    assert numbers_in('对数似然是公式 (3)，见式 (2b) 和 equation (1)') == set()


def test_bare_shi_is_not_a_reference():
    from common import numbers_in
    assert numbers_in('以这种方式 30% 的人受益') == {30.0}
    assert numbers_in('见式 (2) 和公式 3') == set()


def test_numbered_statements_are_references_not_data():
    # Kőszegi & Rabin (2006): "inequality (8)", "expression (15)", "Definition 1", "Lemma 2" are labels
    from common import numbers_in
    assert numbers_in("by inequality (8), expression (15), Definition 1, Lemma 2, Theorem 3 and Corollary 4; 不等式 (8) 与定义 1") == set()

@pytest.mark.parametrize('source,note,valid', [
    ('The event occurred on July 21, 2010.', '\u4e8b\u4ef6\u53d1\u751f\u4e8e 2010 \u5e74 7 \u6708 21 \u65e5\u3002', True),
    ('The event occurred on Jul. 2010.', 'Event date: 2010-07.', True),
    ('The event occurred on July 21, 2010.', 'Event date: 2011-07.', False),
    ('July is named in an unrelated passage.', 'The value is 7.', False),
])
def test_numeric_month_matches_source_date_only(clean, source, note, valid):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = source
    guide['paras']['P2']['note'] = note
    errors, _, _ = run_checks(doc, guide)
    assert (not any('P2 note' in e for e in errors)) == valid, errors

def test_date_month_does_not_exempt_same_number_elsewhere(clean):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = 'The event occurred on July 21, 2010.'
    guide['paras']['P2']['note'] = 'Event date: 2010-07; growth was 7%.'
    errors, _, _ = run_checks(doc, guide)
    assert any('P2 note' in e and '7' in e for e in errors), errors


def test_date_in_part_claim_uses_paragraph_source_scope(clean):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = 'The event occurred on July 21, 2010.'
    guide['parts'][0]['claim'] = 'The event occurred on 2010-07-21.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('A claim' in e for e in errors), errors


@pytest.mark.parametrize('source,note,valid', [
    ('The trend continued in the 1960s.', '趋势出现在 20 世纪 60 年代。', True),
    ('The account covers 1900 through 1999.', '这发生在 20 世纪。', True),
    ('The trend began in 1970.', '趋势出现在 20 世纪 60 年代。', False),
    ('The trend began in 1865.', '这发生在 20 世纪。', False),
    ('The account covers 1900 through 1999.', 'It changed in the 20th century.', True),
])
def test_century_and_decade_note_numbers(clean, source, note, valid):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = source
    guide['paras']['P2']['note'] = note
    errors, _, _ = run_checks(doc, guide)
    assert (not any('P2 note' in e for e in errors)) == valid, errors
