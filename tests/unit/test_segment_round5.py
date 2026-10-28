from types import SimpleNamespace
import pytest
import segment as s


def block(text, page=1, top=100, size=10, **kw):
    return dict(text=text, type='para', page=page, top=top, bottom=top+30,
                ph=800, pw=600, key=(0,0), x0=50, x1=500, size=size,
                n_lines=3, bold=0, **kw)


def test_blank_and_logo_pages_are_not_scans(monkeypatch):
    blank=SimpleNamespace(words=[], bbox=(0,0,600,800), width=600, height=800, images=[])
    logo=SimpleNamespace(**dict(vars(blank), images=[dict(x0=20,x1=80,top=20,bottom=80)]))
    scan=SimpleNamespace(**dict(vars(blank), images=[dict(x0=0,x1=600,top=0,bottom=800)]))
    text=SimpleNamespace(**dict(vars(blank), words=[dict(text='Neutral ordinary wording. '*5)]))
    monkeypatch.setattr(s,'get_words',lambda p:p.words)
    pdf=SimpleNamespace(pages=[blank,logo,scan,text])
    assert s.scan_page_numbers(pdf,[1,2,3,4]) == [3]


@pytest.mark.parametrize('text',['A result. 4','A result.) 12','A result.4'])
def test_terminal_with_separated_note_number(text):
    assert s.end_terminal(text)


def test_merges_use_last_piece_geometry_and_keep_first_page():
    a=block('An unfinished account',top=700)
    b=block('Continued account without punctuation',page=2,top=80)
    c=block('Separate table description.',page=3,top=80)
    out,n=s.merge_continuations([a,b,c])
    assert n == 1 and len(out)==2
    assert out[0]['page']==1 and out[0]['pages']=={1,2}
    assert out[0]['_end_page']==2
    assert out[0]['bottom']==110 and out[0]['_origin']['page']==1
    assert s.finalize(out)[0][0]['page']==1
    assert out[1]['text']=='Separate table description.'


def test_right_column_can_have_more_lines_than_left():
    lines=[dict(text='Neutral line of ordinary body wording',x0=x,x1=x+190,size=10,top=i*12,bottom=i*12+10)
           for x,n in [(50,12),(330,25)] for i in range(n)]
    assert 240 < s.split_by_edges(lines,600) < 330


def test_sidebar_cannot_replace_body_split(monkeypatch):
    page=SimpleNamespace(width=600,height=800,words=[])
    monkeypatch.setattr(s,'get_words',lambda _:[])
    monkeypatch.setattr(s,'figure_boxes',lambda _:[])
    monkeypatch.setattr(s,'column_gutters',lambda *a,**k:[])
    monkeypatch.setattr(s,'detect_split',lambda *a,**k:300)
    monkeypatch.setattr(s,'detect_sidebar',lambda *a:pytest.fail('body split already established'))
    seen=[]
    monkeypatch.setattr(s,'order_lines',lambda w,segs,split:seen.append(split) or [])
    s.from_pdf_text(SimpleNamespace(pages=[page]),[1],'auto')
    assert seen==[300]


@pytest.mark.parametrize('factor',[1.2,3.0])
def test_stretched_span_uses_glyph_metrics_not_page_fit(factor):
    def char(x, width, top=100, mcid=1):
        return dict(text='a',fontname='NeutralFont',size=10,x0=x,x1=x+width,top=top,mcid=mcid)
    normal=[char(20,5,50,2),char(25,5,50,2)]
    stretched=[dict(char(20+5*factor*i,5*factor), text='abc'[i % 3]) for i in range(40)]
    page=SimpleNamespace(chars=normal+stretched,bbox=(0,0,240,800))
    s.repair_stretched_text(page,{('NeutralFont',c):0.5 for c in 'abc'})
    assert stretched[-1]['x1']==pytest.approx(220)
    assert normal[0]['x0']==20 and normal[0]['x1']==25
    assert all(c['x1']<=240 for c in page.chars)


def test_offpage_unscaled_panel_is_not_rescaled():
    chars=[dict(text='a',fontname='NeutralFont',size=10,x0=500+5*i,x1=505+5*i,top=100) for i in range(20)]
    page=SimpleNamespace(chars=chars,bbox=(0,0,400,800))
    s.repair_stretched_text(page,{('NeutralFont','a'):0.5})
    assert chars[0]['x0']==500


def tracked_words(text, reference=0.5):
    words, x = [], 50
    for token in text.split():
        for letter in token:
            words.append(dict(text=letter,font='NeutralRoman',size=10,bold=False,
                              x0=x,x1=x+5,top=100,bottom=110,word_gap=reference))
            x += 6
        x += 4
    return words


@pytest.mark.parametrize('text',['REFERENCES','FIGURE 1','DATA AVAILABILITY STATEMENT','ACKNOWLEDGMENTS','an unfamiliar label'])
def test_letterspacing_uses_geometry_for_any_vocabulary(text):
    assert s.line_from_words(tracked_words(text))['text']==text


@pytest.mark.parametrize('text',['A B','a b'])
def test_initial_pairs_remain_separate(text):
    assert s.line_from_words(tracked_words(text))['text']==text


def test_isolated_uniform_run_without_word_gap_evidence_is_ambiguous():
    words=tracked_words('ABC',None)
    assert s.line_from_words(words)['text']=='A B C'


def test_tracked_groups_supply_their_own_word_gap_evidence():
    assert s.line_from_words(tracked_words('NEUTRAL LABEL',None))['text']=='NEUTRAL LABEL'


def test_irregular_singleton_gaps_do_not_define_tracking():
    words=tracked_words('ABCDE')
    for i,w in enumerate(words):
        w['x0']+=i*(i-1)/2
        w['x1']+=i*(i-1)/2
    assert s.line_from_words(words)['text']=='A B C D E'


def test_letterspaced_reference_heading_ends_body():
    heading=s.finish_block(dict(lines=[s.line_from_words(tracked_words('REFERENCES'))],page=1,key=(0,0)))
    blocks=[block('An ordinary sentence in the document.'),heading,block('Neutral bibliographic entry.',top=350,size=8)]
    s.classify(blocks,10,{1:dict(h=800)},1)
    s.mark_sections(blocks)
    assert blocks[1]['type']=='ref' and blocks[2]['type']=='ref'


def test_paragraph_enclosure_is_not_table_but_numeric_rows_are():
    lines=[dict(text=t,x0=50,x1=400,top=100+i*12,bottom=110+i*12,size=10) for i,t in enumerate([
        'This ordinary paragraph describes a neutral observation in a study',
        'and explains the measurements taken during the experiment.',
        'The final sentence gives some additional neutral context.'])]
    assert s.text_container([20,20,580,780,'rules'],lines,10)
    for ln in lines: ln['text']='12 24 36 48 60 72'
    assert not s.text_container([20,20,580,780,'rules'],lines,10)


def test_title_kicker_and_existing_colon():
    for first in ['Overview','Overview:']:
        lines=[dict(text=first,font='NeutralItalic',size=20,bold=0,x0=50,x1=150,top=100,bottom=120),
               dict(text='A Neutral Investigation',font='NeutralRoman',size=20,bold=0,x0=50,x1=400,top=125,bottom=145)]
        b=s.finish_block(dict(lines=lines,page=1,key=(0,0)))
        s.classify([b],10,{1:dict(h=800)},1)
        assert b['text']=='Overview: A Neutral Investigation'


@pytest.mark.parametrize("metadata",["https://example.org/issues/current", "ISSN 0000-0000", "doi:10.0000/neutral"])
def test_header_metadata_excludes_larger_masthead(metadata):
    blocks=[block('Neutral Periodical',top=50,size=22),block(metadata,top=100,size=8),block('An Ordinary Research Title',top=200,size=20)]
    s.classify(blocks,10,{1:dict(h=800)},1)
    assert blocks[0]['type']=='frag' and blocks[2].get('level')==0


def test_small_marked_author_note_is_not_merged_into_body():
    blocks=[block('An ordinary body paragraph that ends with a full stop.',top=500),
            block('† A neutral author affiliation and acknowledgement.',top=700,size=8)]
    s.classify(blocks,10,{1:dict(h=800)},1)
    assert blocks[1]['type']=='note'
    assert len(s.merge_continuations(blocks)[0])==2


def test_diagnostics_ignore_numbered_heads_and_explicit_endnotes():
    blocks=[block('A neutral paragraph ends here.',page=i) for i in range(1,5)]
    blocks += [dict(type='heading',text=f'{i}. Neutral subsection',page=1,level=1) for i in range(20)]
    blocks += [block('An explanatory endnote with some neutral wording.',page=4,top=100+i*15,endnote=True) for i in range(10)]
    for b in blocks:
        if b.get('endnote'): b['type']='note'
    assert s.layout_signals(blocks,4)[1]==[]


def test_diagnostics_flag_page_fragment_majority():
    blocks=[block('A neutral paragraph ends here.',page=1)]
    blocks += [dict(block('Several ordinary words are scattered through this page.',page=2,top=100+i*20),type='frag') for i in range(12)]
    assert any('fragments' in r for r in s.layout_signals(blocks,2)[1])


def test_diagnostics_flag_relative_length_outlier():
    blocks=[block('A neutral observation ends here. '*i) for i in range(2,20)]
    blocks.append(block('A neutral observation continues. '*1000,breaks=3))
    assert any('length outliers' in r for r in s.layout_signals(blocks,1)[1])


def test_decimal_chart_labels_survive_margin_removal():
    pages=[dict(pno=p,h=800,lines=[dict(text='0.60',top=90,bottom=100),
                                 dict(text='Neutral chart label 0.70',top=105,bottom=115)]) for p in range(1,5)]
    assert s.strip_margins(pages,lambda p:p['lines'],lambda p,v:p.update(lines=v),[])==0


@pytest.mark.parametrize('marker',['*','†','‡'])
def test_small_symbol_marked_footer_is_note(marker):
    blocks=[block('A neutral body sentence ends here.',top=400),
            block(marker+' A neutral acknowledgement ends here.',top=700,size=8)]
    s.classify(blocks,10,{1:dict(h=800)},1)
    assert blocks[-1]['type']=='note'


def test_different_marker_font_and_italics_alone_do_not_make_a_note():
    words=[dict(text=t,font=f,size=10,bold=False,x0=50+i*40,x1=85+i*40,top=700,bottom=710)
           for i,(t,f) in enumerate([('y','NeutralMarker'),('A','NeutralItalic'),('neutral','NeutralItalic'),('affiliation.','NeutralItalic')])]
    marked=s.finish_block(dict(lines=[s.line_from_words(words)],page=1,key=(0,0)))
    s.classify([marked],10,{1:dict(h=800)},1)
    assert marked['type']=='para'
    assert 'symbol_note' not in marked


def test_small_fragment_endnotes_label_exempts_following_notes():
    blocks=[dict(type='frag',text='Endnotes',page=1)]+[dict(block('An explanatory note ends here.',top=100+i*20),type='note') for i in range(12)]
    s.mark_sections(blocks)
    assert all(b.get('endnote') for b in blocks[1:])
    assert s.layout_signals([block('A neutral paragraph ends here.')]+blocks,1)[1]==[]


def test_remaining_raster_text_overflow_is_reported():
    reasons=s.layout_signals([block('A neutral paragraph ends here.')],1,{1:dict(text_overflow=True)})[1]
    assert any('beyond page bounds' in r for r in reasons)


def test_text_enclosure_keeps_reading_order_boundary(monkeypatch):
    box=[220,50,580,350]
    page=SimpleNamespace(width=600,height=800,words=[])
    monkeypatch.setattr(s,'get_words',lambda _:[])
    monkeypatch.setattr(s,'figure_boxes',lambda _:[box])
    monkeypatch.setattr(s,'text_container',lambda *a:True)
    monkeypatch.setattr(s,'column_gutters',lambda *a,**k:[200,400])
    seen=[]
    monkeypatch.setattr(s,'order_columns',lambda segs,gutters,body,boxes,page:seen.extend(boxes) or [])
    _,_,info,_=s.from_pdf_text(SimpleNamespace(pages=[page]),[1],'auto')
    assert seen==[box] and info[1]['figs']==[]


def test_content_warning_does_not_select_new_columns(monkeypatch):
    calls=[]
    result=dict(columns='auto',score=0,reasons=['most page text is in fragments on pages [1]'])
    def segment(pdf,pnos,columns,cache):
        calls.append(columns)
        return result
    monkeypatch.setattr(s,'segment_text_layer',segment)
    best,messages=s.choose_columns(None,[1],'auto')
    assert calls==['auto'] and best is result
    assert any('most page text' in message for message in messages)


def test_trailing_title_marker_uses_font_evidence():
    words=[dict(text=t,font=f,size=z,bold=False,x0=50+i*70,x1=100+i*70,top=100,bottom=100+z)
           for i,(t,f,z) in enumerate([('A','NeutralRoman',20),('Neutral','NeutralRoman',20),('Title','NeutralRoman',20),('q','NeutralMarker',10)])]
    title=s.finish_block(dict(lines=[s.line_from_words(words)],page=1,key=(0,0)))
    s.classify([title],10,{1:dict(h=800)},1)
    assert title['text']=='A Neutral Title'


def test_display_rows_form_one_region_without_swallowing_prose():
    before=block('We express the relation as',top=50)
    rows=[dict(block(t,top=y),n_lines=1,math_style=True) for t,y in [('x u dv',100),('y u dv',140),('z u dv.',180)]]
    after=block('Rearranging the relation gives the next result.',top=240)
    blocks=[before]+rows+[after]
    s.group_display_rows(blocks)
    assert len(blocks)==3 and blocks[1]['type']=='frag' and blocks[1]['equation']
    assert blocks[1]['top']==90 and blocks[1]['bottom']==225
    assert s.is_display_equation(blocks[1])
    out,joins=s.merge_continuations(blocks)
    assert joins==0 and [b['text'] for b in out if b['type']=='para']==[before['text'],after['text']]


def test_display_grouping_respects_tables_and_equation_numbers():
    rows=[dict(block('x y z',top=100),math_style=True),dict(block('(2) x y z',top=140),math_style=True),
          dict(block('a b c',top=180),math_style=True,table=True)]
    s.group_display_rows(rows)
    assert len(rows)==3


def test_scan_detection_counts_are_reused(monkeypatch):
    pdf=SimpleNamespace(pages=[SimpleNamespace(words=[dict(text='Neutral words '*5)],images=[])])
    calls=[]
    monkeypatch.setattr(s,'get_words',lambda page:calls.append(page) or page.words)
    counts={}
    assert s.scan_page_numbers(pdf,[1],counts)==[]
    assert counts=={1:70}
    assert len(calls)==1


def test_visible_unmapped_operators_are_not_letter_spacing():
    words=tracked_words('ABC')
    for w in words: w['unmapped_boxes']=[(55,56,100,110),(61,62,100,110)]
    assert s.line_from_words(words)['text']=='A B C'


def test_tracking_does_not_cross_baselines():
    words=tracked_words('ABC')
    words[1]['bottom']+=2
    words[1]['top']+=2
    assert s.line_from_words(words)['text']=='A B C'


def test_tracking_rejoins_fragments_already_merged_by_word_extractor():
    words=tracked_words('NEUTRAL LABEL')
    words[:2]=[dict(words[0],text='NE',x1=words[1]['x1'])]
    assert s.line_from_words(words)['text']=='NEUTRAL LABEL'


def test_display_crop_retains_unmapped_operator_ink():
    rows=[dict(block('x y z',top=100),math_style=True,unmapped_ink=[(40,48,90,140)]),
          dict(block('a b c',top=150),math_style=True,unmapped_ink=[(40,48,140,190)])]
    s.group_display_rows(rows)
    assert len(rows)==1 and rows[0]['equation']
    assert rows[0]['x0']==40 and rows[0]['top']==90 and rows[0]['bottom']==190


def test_unmapped_ink_stays_in_its_own_column():
    word=dict(text='x',unmapped_boxes=[(40,48,90,140),(340,348,90,140)])
    line=dict(x0=50,x1=200,top=100,bottom=110,words=[word])
    assert s.unmapped_ink([line],dict(column_x0=30,column_x1=250))==[(40,48,90,140)]


def test_kerning_can_narrow_one_gap_inside_tracked_word():
    words=tracked_words('NEUTRAL LABEL')
    words[1]['x0']-=0.2
    assert s.line_from_words(words)['text']=='NEUTRAL LABEL'
