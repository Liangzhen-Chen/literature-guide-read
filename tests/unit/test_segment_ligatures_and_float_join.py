"""Synthetic glyph, graphic-boundary and uncertainty ownership cases."""
from types import SimpleNamespace
import pytest
import segment as s
from test_segment_typing import word, block


def test_touching_ligature_fallback_uses_the_actual_baseline():
    a=word('pro',50,100)
    b=dict(word('fi',65.05,98),font='NeutralFallback',ligature=True)
    c=word('le.',75.1,100)
    for w in [a,b,c]:w['baseline']=110
    assert s.line_from_words([a,b,c])['text']=='profile.'
    b['baseline']=105
    assert s.line_from_words([a,b,c])['text']=='pro fi le.'


def test_a_real_word_space_before_a_ligature_stays():
    a=word('of',50,100)
    b=dict(word('fi',63,98),font='NeutralFallback',ligature=True)
    c=word('rms',73.05,100)
    for w in [a,b,c]:w['baseline']=110
    assert s.line_from_words([a,b,c])['text']=='of firms'
    b['x0']=a['x1']+.05
    b['space_before']=True
    assert s.line_from_words([a,b])['text']=='of fi'


@pytest.mark.parametrize('glyph',['\ufb01','fi'])
def test_extraction_retains_single_glyph_ligature_evidence(glyph):
    raw=dict(text=glyph,x0=50,x1=56,top=98,bottom=108,size=10,fontname='NeutralFallback')
    char=dict(raw,matrix=(1,0,0,1,50,690),upright=True)
    second=dict(raw,top=118,bottom=128,matrix=(1,0,0,1,50,670),upright=True)
    page=SimpleNamespace(chars=[char,second],bbox=(0,0,600,800),width=600,height=800,
                         extract_words=lambda **kw:[char,second])
    ws=s.get_words(page)
    assert ws[0]['text']=='fi' and ws[0]['ligature']
    assert ws[0]['baseline']==110
    assert ws[1]['baseline']==130


def test_plot_title_uses_panel_label_font_and_does_not_block_a_page_join():
    ws=[dict(word('Horizontal',120,103,size=12),font='NeutralPlot-Oblique'),
        dict(word('1',110,150,size=6),font='NeutralPlot'),
        dict(word('2',160,180,size=6),font='NeutralPlot')]
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,height=800,rects=[],edges=[])
    s.early_float_regions(page,ws,[[100,120,300,300]],10)
    assert ws[0]['graphic']
    a=dict(block('The components include capital,',700),page=1,type='para')
    plot=dict(block('Horizontal',100),page=2,type='frag',graphic=True)
    caption=dict(block('Figure 1. Neutral observations.',350),page=2,type='caption')
    b=dict(block('labour, and other inputs.',410),page=2,type='para')
    out,_=s.merge_continuations([a,plot,caption,b],10)
    assert out[0]['text']=='The components include capital, labour, and other inputs.'
    assert 'Horizontal' not in out[0]['text']
    a=dict(block('The components were measured.5',700),page=1,type='para')
    assert not s.paragraph_continues(a,b)


def test_final_items_do_not_inherit_a_cropped_equations_glyph_codes():
    source=dict(page=2,bbox=[.2,.2,.3,.3],codes=['\u27e6cid:7\u27e7'])
    p=dict(block('An intact explanation.',100),type='para',unmapped_glyphs=['\u27e6cid:7\u27e7'],unmapped_sources=[source])
    items,_=s.finalize([p])
    assert items[0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']
    equation=dict(id='F1',page=2,type='frag',equation=True,bbox=[.1,.1,.4,.4],text='x = y')
    doc=dict(items=items+[equation],crops={'F1':'crops/F1.png'})
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert 'unmapped_glyphs' not in items[0]
    p['text']='An explanation with \u27e6cid:7\u27e7 still broken.'
    items,_=s.finalize([p])
    assert items[0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']


def test_small_table_title_is_not_a_large_plot_title():
    title=dict(word('Neutral summary',120,103,size=8),font='NeutralPlot')
    ws=[title,dict(word('1',110,150,size=6),font='NeutralPlot'),
        dict(word('2',160,180,size=6),font='NeutralPlot')]
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,height=800,rects=[],edges=[])
    s.early_float_regions(page,ws,[[100,120,300,300]],10)
    assert not title.get('graphic')


def test_written_glyph_list_keeps_dropped_marks_until_crop_geometry_is_known(tmp_path):
    doc={'items':[dict(id='P1',type='para',page=1,text='An intact explanation.',
                      unmapped_glyphs=['\u27e6cid:7\u27e7'],unmapped_text=['\u27e6cid:7\u27e7'],
                      unmapped_sources=[dict(page=1,bbox=[.2,.2,.3,.3],codes=['\u27e6cid:7\u27e7'])]),
                  dict(id='P2',type='para',page=1,text='Still broken \u27e6cid:8\u27e7.') ]}
    s.write_outputs(doc,tmp_path,1000)
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']
    equation=dict(id='F1',page=1,type='frag',equation=True,bbox=[.1,.1,.4,.4],text='x = y')
    doc['items'].append(equation)
    doc['crops']={'F1':'crops/F1.png'}
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert 'unmapped_glyphs' not in doc['items'][0]
    assert doc['items'][1]['unmapped_glyphs']==['\u27e6cid:8\u27e7']
