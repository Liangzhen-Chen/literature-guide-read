"""Warn about broken reading text, while accepting an equation shown as a crop."""
import pytest
from check import run_checks


@pytest.mark.parametrize('crop,warning',[(False,True),(True,False)])
def test_equation_crop_resolves_the_readers_unmapped_glyph_warning(clean,crop,warning):
    doc,guide=clean
    doc['items'].append(dict(id='F1',type='frag',page=1,equation=True,text='x \u27e6cid:7\u27e7 y'))
    if crop:doc['crops']={'F1':'crops/F1.png'}
    _,warns,_=run_checks(doc,guide)
    assert any('F1: unmapped PDF glyphs' in w for w in warns)==warning


def test_dropped_prose_glyph_warns_even_without_a_placeholder(clean):
    doc,guide=clean
    doc['items'][0]['unmapped_glyphs']=['\u27e6cid:7\u27e7']
    _,warns,_=run_checks(doc,guide)
    assert any('P1: unmapped PDF glyphs' in w for w in warns)
    doc['items'][0]['text']+=' \u27e6cid:7\u27e7'
    _,warns,_=run_checks(doc,guide)
    assert any('P1: unmapped PDF glyphs' in w for w in warns)


def test_equation_part_is_covered_by_the_combined_display_crop(clean):
    doc,guide=clean
    doc['items'] += [dict(id='F1',type='frag',page=1,equation=True,text='x = y',bbox=[.1,.2,.9,.5]),
                     dict(id='F2',type='frag',page=1,equation=True,eq_part=True,text='\u27e6cid:7\u27e7',bbox=[.1,.4,.9,.5]),
                     dict(id='F3',type='frag',page=1,equation=True,text='\u27e6cid:8\u27e7',bbox=[.1,.6,.9,.7])]
    doc['crops']={'F1':'crops/F1.png'}
    _,warns,_=run_checks(doc,guide)
    assert not any('F2: unmapped PDF glyphs' in w for w in warns)
    assert any('F3: unmapped PDF glyphs' in w for w in warns)
