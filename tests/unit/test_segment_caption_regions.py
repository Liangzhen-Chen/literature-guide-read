"""Synthetic caption regions and styled colon labels."""
from types import SimpleNamespace
import segment as s
from test_segment_batch2 import word, line
from test_segment_typing import block, classify


def test_raster_caption_and_legend_share_their_column_past_a_doi():
    title=line('Figure 1. Neutral measurements across observations',220,size=8)
    continuation=line('with independent observations',228.5,size=8)
    legend=line('Panels describe independent estimates',240,size=8.5)
    # The first line fills the caption measure; the legend is a new paragraph.
    width=title['x1']
    image=dict(x0=50,x1=width,top=20,bottom=195)
    doi=line('DOI: 10.0000/neutral',201,size=7)
    ws=sum([l['words'] for l in [doi,title,continuation,legend]],[])
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,height=800,
                         rects=[],images=[image],edges=[])
    s.early_float_regions(page,ws,[],9)
    group=title['words'][0].get('caption_group')
    assert group is not None
    assert all(w.get('caption_group')==group for w in legend['words'])


def test_table_cells_are_not_a_caption_wrap_even_in_the_same_font():
    a = block('Table 1. Neutral measurements',100,type='caption',column_x1=550,last_x1=260)
    b = block('Dependent variable:',114,type='frag',column_x1=550)
    bs=[a,b]
    s.join_wrapped_blocks(bs,10)
    assert bs == [a,b]
    assert not s.caption_wrap(dict(a,last_x1=550),dict(b,tab=True))


def test_caption_wrap_requires_the_measure_and_no_cell_gaps():
    a = line('A neutral caption reaches its right edge',100)
    a['x1']=548
    b = line('and continues on this line.',112)
    assert s.caption_wrap(a,b,50,550)
    assert not s.caption_wrap(dict(a,x1=300),b,50,550)
    cells = dict(b,cell_edges=[250])
    assert not s.caption_wrap(a,cells,50,550)


def test_label_and_adjacent_title_share_the_caption_not_the_header():
    label=line('Table 1',50)
    title=line('Neutral summary measurements',50,x=135)
    header=[word('Variable',50,80),word('Mean',250,80)]
    ws=label['words']+title['words']+header
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,75,550,200,'table']],10)
    group=label['words'][0]['caption_group']
    assert all(w.get('caption_group')==group for w in title['words'])
    assert all(w.get('caption_group') is None for w in header)
    assert all(w.get('tab') for w in header)


def test_broad_rule_candidate_does_not_hide_a_title_above_the_real_header():
    label=line('Table 1',50)
    title=line('Neutral summary measurements',52,x=135)
    header=[word('Variable',50,82),word('Mean',250,82)]
    ws=label['words']+title['words']+header
    rect=dict(x0=50,x1=550,top=75,bottom=95)
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[rect])
    s.early_float_regions(page,ws,[[50,10,550,200,'rules'],[50,75,550,200,'table']],10)
    assert all(w.get('caption_group') is not None for w in title['words'])
    assert all(w.get('caption_group') is None for w in header)


def test_centered_caption_year_wraps_above_the_table_separator():
    cap=line('Table 2. Neutral estimates for independent choices',50,x=70)
    year=line('2001-02',62)
    center=(cap['x0']+cap['x1'])/2
    shift=center-(year['x0']+year['x1'])/2
    for w in year['words']:w['x0']+=shift;w['x1']+=shift
    year.update(s.line_from_words(year['words']))
    cap['caption_center']=center
    assert s.caption_wrap(cap,year,50,cap['x1'])


def test_caption_source_paragraph_is_not_confused_with_a_table_header():
    cap=line('Figure 1. A neutral comparison.',200,size=8)
    note=line('Source: Independent neutral observations supply these measurements.',210,size=8)
    ws=cap['words']+note['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,50,550,195]],10)
    assert all(w.get('caption_group')==cap['words'][0]['caption_group'] for w in note['words'])


def test_horizontal_curve_edges_bound_a_wrapped_title_before_header_cells():
    cap=line('Table 1. A neutral title reaches',50)
    tail=line('the final part of its title.',62)
    header=line('Dependent variable:',82)
    ws=cap['words']+tail['words']+header['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[],
                         edges=[dict(x0=50,x1=550,top=78,orientation='h')])
    s.early_float_regions(page,ws,[[50,10,550,300,'rules']],10)
    assert all(w.get('caption_group')==cap['words'][0]['caption_group'] for w in tail['words'])
    assert all(w.get('caption_group') is None for w in header['words'])


def test_small_caption_legend_can_start_a_separate_paragraph():
    a=line('Figure 1. A neutral explanation requires an independent comparison',200,size=8)
    b=line('A second neutral explanation requires another independent comparison',210,size=8)
    c=line('for neutral choices.',220,size=8)
    legend=line('Independent observations explain the comparison.',235,size=8)
    ws=sum([l['words'] for l in [a,b,c,legend]],[])
    right=max(a['x1'],b['x1'])
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,50,right,195]],10)
    assert all(w.get('caption_group')==a['words'][0]['caption_group'] for w in legend['words'])


def test_label_can_anchor_through_a_contiguous_multiline_title_to_its_rule():
    lines=[line(t,y,size=8) for t,y in [('Table 1',50),('A neutral caption title',62),
            ('Source: An independent neutral explanation',74),('supports these neutral observations',86),
            ('Further comparisons.',98)]]
    ws=sum([l['words'] for l in lines],[])
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[],
                         edges=[dict(x0=50,x1=550,top=115,orientation='h')])
    s.early_float_regions(page,ws,[[50,115,550,300,'table']],10)
    group=lines[0]['words'][0]['caption_group']
    assert all(w.get('caption_group')==group for l in lines[1:] for w in l['words'])


def colon_line(text,y):
    ln=line(text,y)
    for w in ln['words']:
        w['font']='NeutralBold'
        w['bold']=True
        if w['text'].endswith(':'):break
    return ln


def test_bold_colon_label_with_body_is_one_visible_paragraph():
    ls=[colon_line('A neutral programme: Independent participants make choices.',100),
        line('The following sentence explains those choices.',112)]
    bs=s.build_blocks(ls,2,10)
    classify(bs)
    assert len(bs)==1 and bs[0]['type']=='para'
    assert bs[0]['text'].startswith('A neutral programme: Independent')


def test_wrapped_bold_colon_label_keeps_its_body_in_the_paragraph():
    first=line('An extended neutral programme',100)
    for w in first['words']:w['font']='NeutralBold';w['bold']=True
    first.update(s.line_from_words(first['words']))
    ls=[first,colon_line('(NIP): Independent participants make choices.',112),line('The explanation continues here.',124)]
    bs=s.build_blocks(ls,2,10)
    classify(bs)
    assert len(bs)==1 and bs[0]['type']=='para'
    assert 'programme (NIP): Independent' in bs[0]['text']


def test_heading_does_not_extend_with_its_mixed_font_body_tail():
    a=block('A neutral label',100,type='heading',font='NeutralBold',end_font='NeutralRoman')
    a['bold']=1
    b=block('Independent body prose follows.',114,type='para',font='NeutralRoman',body_font=True)
    bs=[a,b]
    s.join_wrapped_blocks(bs,10)
    assert bs==[a,b]
