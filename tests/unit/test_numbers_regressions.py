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
    # An economics article: "inequality (8)", "expression (15)", "Definition 1", "Lemma 2" are labels
    from common import numbers_in
    assert numbers_in("by inequality (8), expression (15), Definition 1, Lemma 2, Theorem 3 and Corollary 4; 不等式 (8) 与定义 1") == set()

@pytest.mark.parametrize('source,note,valid', [
    ('The event occurred on July 21, 2010.', '\u4e8b\u4ef6\u53d1\u751f\u4e8e 2010 \u5e74 7 \u6708 21 \u65e5\u3002', True),
    ('The event occurred on Jul. 2010.', 'Event date: 2010-07.', True),
    ('The event occurred on July 21, 2010.', 'Event date: 2011-07.', False),
    ('July is named in an unrelated passage.', 'The value is 7.', True),
])
def test_numeric_month_matches_source_date_only(clean, source, note, valid):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = source
    guide['paras']['P2']['note'] = note
    errors, _, _ = run_checks(doc, guide)
    assert (not any('P2 note' in e for e in errors)) == valid, errors

def test_named_month_is_available_throughout_source_scope(clean):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = 'The event occurred on July 21, 2010.'
    guide['paras']['P2']['note'] = 'Event date: 2010-07; growth was 7%.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in e and '7' in e for e in errors), errors


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


@pytest.mark.parametrize('dash', ['-', '\u2013'])
@pytest.mark.parametrize('prefix', ['', 'A study ', 'The studies ', 'Conditions '])
def test_numeric_range_keeps_both_endpoints(dash, prefix):
    for gap in ['', ' ']:
        text = f'{prefix}(1970{gap}{dash}{gap}1973)'
        assert common.numbers_in(text) == {1970, 1973}
        assert {1970, 1973} <= common.source_numbers(text)


@pytest.mark.parametrize('text', ['-0.5', 'value -0.5', '(-0.5)', 'value (-0.5)'])
def test_negative_number_still_uses_magnitude(text):
    # Number checking has always compared magnitudes, including N(-496,114).
    assert common.numbers_in(text) == {.5}


@pytest.mark.parametrize('dash', ['-', '\u2013'])
def test_range_start_allowed_in_note(clean, dash):
    doc, guide = clean
    for item in doc['items']:
        item['text'] = f'The study (1970{dash}1973) reports stable output.'
    guide['paras']['P2']['note'] = 'The period begins in 1970.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in error for error in errors), errors


@pytest.mark.parametrize('text', [
    '\u65b9\u7a0b 1', '\u65b9\u7a0b (2)', '\u65b9\u7a0b 1 \u5230 4',
    '\u65b9\u7a0b (1) \u81f3 (4)', '\u56fe 1 \u5230 4', '\u8868 2 \u81f3 5',
    '\u56fe1\u52304', '\u88682\u81f35',
])
def test_chinese_reference_labels_and_ranges(text):
    assert common.numbers_in(text) == set()
    assert common.numbers_in(text + '\uff0c\u4f30\u8ba1\u503c\u4e3a 6.25') == {6.25}


@pytest.mark.parametrize('text', ['\u56fe 24.03', '\u8868 24.03', '\u56fe 1 \u5230 4.5', '\u8868 2 \u81f3 5.25'])
def test_chinese_reference_ranges_preserve_real_decimals(text):
    assert common.numbers_in(text) == ({24.03} if '24.03' in text else {4.5} if '4.5' in text else {5.25})


def test_chinese_equation_range_note_passes_checker(clean):
    doc, guide = clean
    guide['paras']['P2']['note'] = '\u65b9\u7a0b 1 \u5230 4 \u8bf4\u660e\u8f83\u5c0f\u5956\u52b1\u7684\u9009\u62e9\u3002'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in error and 'source text' in error for error in errors), errors


@pytest.mark.parametrize('source', ['58,000', '58 000', '58000', '58\u00a0000', '58\u202f000'])
@pytest.mark.parametrize('note', ['58,000', '58 000', '58000'])
def test_thousands_groupings_match_source(clean, source, note):
    assert common.numbers_in(source) == {58000}
    doc, guide = clean
    for it in doc['items']: it['text'] = 'There were '+source+' observations.'
    guide['paras']['P2']['note'] = 'The sample contains '+note+' observations.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in error and 'source text' in error for error in errors), errors


@pytest.mark.parametrize('name,number', [(name,n) for name,n in common.MONTH_NAMES.items()])
def test_month_names_and_abbreviations_in_source(name, number):
    assert number in common.source_numbers(name.title()+'.')
    assert common.source_numbers(name+'suffix') == set()


@pytest.mark.parametrize('source,note', [('July', '7 \u6708'),('June 3','6 \u6708 3 \u65e5'),('Jan.','1 \u6708')])
def test_chinese_month_note(clean, source, note):
    doc, guide = clean
    for it in doc['items']: it['text'] = 'Event date: '+source+'.'
    guide['paras']['P2']['note'] = note
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in error and 'source text' in error for error in errors), errors


def test_unrelated_counts_are_not_thousands():
    assert common.numbers_in('25 75') == {25,75}


def test_chinese_page_ranges_are_reference_labels():
    from common import numbers_in
    assert numbers_in('引文见第 109–110 页') == set()
    assert numbers_in('见第 12 至 14 页') == set()
    assert numbers_in('第 3 页有 25 人') == {25.0}


@pytest.mark.parametrize('dash', ['-', '\u2013'])
@pytest.mark.parametrize('start,end,expanded', [(2006, '08', 2008), (2004, '19', 2019),
                                               (1998, '02', 2002), (2006, '06', 2006)])
def test_source_expands_abbreviated_year_range_only(dash, start, end, expanded):
    source = f'The study ({start}{dash}{end}) reports output.'
    assert expanded in common.source_numbers(source)
    assert common.numbers_in(source) == {start, int(end)}


@pytest.mark.parametrize('source', ['12006-08', '2006-080', '2006-2008'])
def test_short_year_range_does_not_match_partial_numbers(source):
    assert common.source_numbers(source) == common.numbers_in(source)


@pytest.mark.parametrize('space', [' ', '\u00a0', '\u202f'])
def test_grouped_thousands_before_sentence_period(space):
    text = f'Cost was \u00a3 16{space}000.'
    assert common.numbers_in(text) == {16000}
    assert common.source_numbers(text) == {16000}
    assert common.numbers_in(f'16{space}000.5') == {16, .5}


def test_grouped_decimal_does_not_normalize_a_prefix():
    assert common.numbers_in('16 000 000.5') == {16, 0, .5}


def test_sentence_ending_grouped_amount_in_source(clean):
    doc, guide = clean
    doc['items'][0]['text'] = 'The cost was \u00a3 16 000.'
    guide['paras']['P1']['els'] = []
    guide['paras']['P1']['note'] = 'The cost was \u00a3 16,000.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P1 note' in error and 'source text' in error for error in errors), errors


def test_abbreviated_year_source_accepts_expanded_note(clean):
    doc, guide = clean
    for it in doc['items']:
        it['text'] = 'Output increased during 1998-02.'
    guide['paras']['P2']['note'] = 'Output increased through 2002.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P2 note' in error and 'source text' in error for error in errors), errors


def test_text_layer_space_before_decimal_point():
    from common import source_numbers
    assert 62.8 in source_numbers('a share of 62 .8 percent')
    assert 5.26 in source_numbers('rose by 5 .26 points')
    assert 0.5 not in source_numbers('ends here. 5 apples')


def test_parenthesised_count_after_label_word_is_data():
    from common import source_numbers
    assert 14 in source_numbers('The environment part (14 questions) included items.')
    assert 3 not in source_numbers('Equation (3) shows the bound')
    assert 2 not in source_numbers('as Study 2 shows')


def test_number_glued_to_chinese_is_read_whole():
    from common import source_numbers
    assert source_numbers('利率约为12.5%，共有37个区') == {12.5, 37.0}
    assert 1234 in source_numbers('当铺数量为1,234家') and 234 not in source_numbers('当铺数量为1,234家')
    assert not source_numbers('x2 与 P12')
    assert not source_numbers('援引第13(3)条')


def test_wrong_number_glued_to_chinese_is_caught(clean):
    doc, guide = clean
    guide['paras']['P1']['note'] = {'zh': '份额约为61.5%。'}
    guide['meta']['notes_lang'] = ['zh']
    errors, _, _ = run_checks(doc, guide)
    assert any('P1 note' in error and '61.5' in error for error in errors), errors
    guide['paras']['P1']['note'] = {'zh': '份额约为60.2%。'}
    errors, _, _ = run_checks(doc, guide)
    assert not any('P1 note' in error and 'source text' in error for error in errors), errors
