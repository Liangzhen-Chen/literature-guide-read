"""Dropped glyphs belong to source boxes, not to placeholder strings."""
from types import SimpleNamespace
from pdfminer.psparser import LIT
import segment as s
from test_segment_typing import block


def document(sources):
    return dict(items=[dict(id='P1',page=1,type='para',text='A complete explanation.',
                           unmapped_glyphs=['\u27e6cid:7\u27e7'],unmapped_sources=sources),
                       dict(id='F1',page=1,type='frag',text='x = y',equation=True,bbox=[.1,.2,.5,.4])],
                crops={'F1':'crops/F1.png'})


def mark(box,page=1):
    return dict(page=page,bbox=box,codes=['\u27e6cid:7\u27e7'])


def test_same_code_in_prose_and_a_display_keeps_the_prose_warning():
    doc=document([mark([.2,.25,.3,.3]),mark([.2,.6,.3,.7])])
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']
    doc['items'][0]['unmapped_sources'].pop()
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert 'unmapped_glyphs' not in doc['items'][0]


def test_uncropped_display_and_other_page_marks_keep_their_codes():
    doc=document([mark([.2,.25,.3,.3])])
    doc['crops']={}
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']
    doc=document([mark([.2,.25,.3,.3],2)])
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']


def test_crop_widening_does_not_cover_a_neighbouring_prose_glyph():
    doc=document([mark([.7,.25,.8,.3])])
    regions=s.unmapped_equation_regions(doc['items'])
    doc['items'][1]['bbox']=[.08,.2,.92,.4]
    s.filter_cropped_unmapped(doc,regions)
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']


def test_outline_bounds_prove_coverage_when_font_wide_metrics_are_offset():
    source=mark([.2,.1,.3,.19])
    source['ink_bbox']=[.2,.19,.3,.25]
    doc=document([source])
    regions=s.unmapped_equation_regions(doc['items'])
    doc['items'][1]['crop_bbox']=[.09,.18,.51,.42]
    s.filter_cropped_unmapped(doc,regions)
    assert 'unmapped_glyphs' not in doc['items'][0]
    doc=document([source])
    s.filter_cropped_unmapped(doc,s.unmapped_equation_regions(doc['items']))
    assert doc['items'][0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']


def test_glyph_outline_bounds_use_the_fonts_matrix():
    class Glyph:
        def draw(self,pen):
            pen.moveTo((100,-200));pen.lineTo((300,-200))
            pen.lineTo((300,400));pen.lineTo((100,400));pen.closePath()
    bounds=s.unmapped_font_bounds({'NeutralForm':Glyph()},{7:'NeutralForm'},[.001,0,0,.001,0,0])
    assert bounds[7]==(.1,-.2,.3,.4)


def test_glyph_source_positions_survive_a_merge():
    first=mark([.2,.25,.3,.3]);second=mark([.2,.25,.3,.3],2)
    a=dict(unmapped_sources=[first],unmapped_glyphs=['\u27e6cid:7\u27e7'])
    s.retain_unmapped(a,dict(unmapped_sources=[second],unmapped_glyphs=['\u27e6cid:7\u27e7']))
    assert a['unmapped_sources']==[first,second]


def test_blank_standard_font_control_is_distinct_from_zero_advance_ink():
    spec=dict(BaseFont=LIT('Times-Roman'),Subtype=LIT('Type1'),Encoding=LIT('WinAnsiEncoding'))
    page=SimpleNamespace(page_obj=SimpleNamespace(resources={'Font':{'F1':spec}}),pdf=SimpleNamespace())
    props=s.font_properties(page)
    glyph=dict(text='(cid:0)',fontname='Times-Roman',size=10,x0=50,x1=50,adv=0,upright=True)
    s.repair_case_maps([glyph],props)
    assert glyph['text']==''
    props['Times-Roman']['glyph_names'][0]='uni0301'
    glyph['text']='(cid:0)'
    s.repair_case_maps([glyph],props)
    assert glyph['text']=='(cid:0)'
