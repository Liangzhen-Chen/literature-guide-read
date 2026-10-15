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
