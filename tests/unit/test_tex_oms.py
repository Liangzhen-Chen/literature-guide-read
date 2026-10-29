import pytest
import segment as s


@pytest.mark.parametrize('name', ['CMSY', 'CMSY10', 'ABCDEF+CMSY7',
                                 'NUBVRQ+TeX_CM_Maths_Symbols', 'CMMathSymbols10'])
def test_oms_names_and_minus(name):
    assert s.tex_oms_char(name, 0) == '\u2212'


@pytest.mark.parametrize('name', ['Symbol', 'CMR10', 'CMMI10', 'CMEX10',
                                 'TeX_CM_Maths_Extension', 'CustomMathSymbols',
                                 'NotCMSY10', 'CMSY10Other'])
def test_other_fonts_untouched(name):
    assert s.tex_oms_char(name, 0) is None


def test_full_table_and_representative_symbols():
    assert set(s.TEX_OMS) == set(range(128))
    for cid, text in [(0, '\u2212'), (1, '\u00b7'), (2, '\u00d7'), (3, '\u2217'),
                      (4, '\u00f7'), (0x41, '\U0001d49c'), (0x7f, '\u2660')]:
        assert s.tex_oms_char('CMSY10', cid) == text
    assert s.tex_oms_char('CMSY10', 128) is None


def test_repair_only_unmapped_characters():
    def char(text, font='ABCDEF+CMSY10'):
        return dict(text=text, fontname=font, size=10, x0=0, x1=5, upright=True)
    chars = [char('(cid:0)'), char('(cid:0)', 'OtherFont'), char('x'),
             char('\x00'), char('\uf000'), char('(cid:128)')]
    s.repair_case_maps(chars, {})
    assert [c['text'] for c in chars] == ['\u2212', '(cid:0)', 'x', '\x00', '\uf000', '(cid:128)']


def test_tex_not_combines_with_its_base_without_changing_mapped_characters():
    from copy import deepcopy
    common = dict(size=10, top=0, bottom=10, upright=True, matrix=(10,0,0,10,20,30))
    mark = dict(common, text='(cid:54)', fontname='CMSY10', x0=20, x1=20)
    base = dict(common, text='=', fontname='CMR10', x0=20, x1=28)
    before = deepcopy(base)
    s.repair_case_maps([mark, base], {})
    assert base == before
    assert mark['x0'] == mark['x1'] == 28
    line = s.make_lines([dict(mark, font='CMSY10'), dict(base, font='CMR10')])[0]
    assert line['text'] == '\u2260'
