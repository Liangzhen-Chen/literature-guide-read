from copy import deepcopy
from types import SimpleNamespace

import pytest
import segment as s


@pytest.mark.parametrize('name', ['CMMI', 'Cmmi10', 'cmmi7', 'ABCDEF+Cmmi5'])
@pytest.mark.parametrize('cid,expected', [(0, '\u0393'), (11, '\u03b1'), (12, '\u03b2'),
                                         (25, '\u03c0'), (28, '\u03c4'), (29, '\u03c5')])
def test_oml_font_and_cid(name, cid, expected):
    assert s.tex_oml_char(name, cid) == expected


@pytest.mark.parametrize('name', ['CMR10', 'CMSY10', 'CMEX10', 'Symbol', 'AdvGreekM',
                                 'OtherCMMI10', 'CMMI10Other', 'ABCDE+Cmmi10'])
def test_non_oml_fonts_untouched(name):
    assert s.tex_oml_char(name, 11) is None


def test_full_oml_table():
    assert set(s.TEX_OML) == set(range(128))
    for cid, expected in [(15, '\u03f5'), (30, '\u03d5'), (34, '\u03b5'),
                          (39, '\u03c6'), (48, '0'), (64, '\u2202'), (65, 'A'),
                          (97, 'a'), (123, '\u0131'), (126, '\u20d7'), (127, '\u0361')]:
        assert s.tex_oml_char('CMMI10', cid) == expected
    assert s.tex_oml_char('CMMI10', 128) is None


def char(text, font='ABCDEF+Cmmi10'):
    return dict(text=text, fontname=font, size=10, x0=0, x1=5, upright=True)


def test_only_unmapped_oml_glyphs_change():
    chars = [char('(cid:11)'), char('(cid:25)'), char('(cid:11)', 'OtherFont'),
             char('u'), char('\u03b8'), char('(cid:128)'), char('\x0b')]
    before = deepcopy(chars)
    s.repair_case_maps(chars, {})
    assert [c['text'] for c in chars[:2]] == ['\u03b1', '\u03c0']
    assert chars[2:] == before[2:]


@pytest.mark.parametrize('font,text', [('AdvGreekM', 'u'), ('ABCDEF+AdvMathSymb', '\u00bc'),
                                     ('CustomMathPi', 'b'), ('abcDEF+greek', 'D')])
def test_warning_names_pages_and_does_not_change_chars(font, text):
    pages = [SimpleNamespace(chars=[char(text, font), char('b', font)]),
             SimpleNamespace(chars=[char('body', 'Times-Roman')]),
             SimpleNamespace(chars=[char(text, font)])]
    before = deepcopy(pages)
    warning = s.swapped_math_warning(SimpleNamespace(pages=pages), [1, 2, 3])
    assert 'For the agent:' in warning and 'PDF pages [1, 3]' in warning
    assert 'crops or page images (method.md section 8)' in warning
    assert pages == before
    assert s.swapped_math_warning(SimpleNamespace(pages=pages), [2]) == ''


@pytest.mark.parametrize('font,text', [('Symbol', 'a'), ('SymbolMT', 'b'),
                                     ('TeX_CM_Maths_Symbols', 'x'), ('CMMathSymbols10', 'x'),
                                     ('Cmmi10', 'u'), ('CMSY10', 'x'), ('Times-Roman', '\u00bc'),
                                     ('AdvGreekM', '\u03b8'), ('AdvGreekM', '(cid:11)'),
                                     ('AdvMathSymb', '='), ('MathPi', '123')])
def test_warning_excludes_known_fonts_and_non_suspect_text(font, text):
    pdf = SimpleNamespace(pages=[SimpleNamespace(chars=[char(text, font)])])
    assert s.swapped_math_warning(pdf, [1]) == ''
