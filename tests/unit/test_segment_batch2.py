"""Synthetic layout cases: region evidence must precede block typing."""
from types import SimpleNamespace
import pytest
import segment as s
import mineru_backend as m


def word(text, x, y, size=10, **kw):
    return dict(text=text,x0=x,x1=x+len(text)*size/2,top=y,bottom=y+size,
                size=size,font='Neutral',bold=False,italic=False,**kw)


def line(text,y,size=10,x=50,**kw):
    ws=[]
    for t in text.split():
        w=word(t,x,y,size);ws.append(w);x=w['x1']+size/3
    return dict(s.line_from_words(ws),band=0,col=0,**kw)


def block(text,page=1,typ='para',**kw):
    return dict(text=text,page=page,type=typ,**kw)


def test_reference_region_stops_at_exhibit_and_keeps_later_prose():
    bs=[block('References',typ='heading',level=1),
        block('Smith J. 2004. Neutral study. 3: 10-20.'),
        block('Table 2. Summary',2,'caption'),block('Independent appendix prose explains the design.',3)]
    s.mark_sections(bs)
    assert [b['type'] for b in bs]==['ref','ref','caption','para']


def test_numbered_appendix_heading_after_references_resumes():
    bs=[block('References',typ='heading',level=1),
        block('Smith J. 2004. Neutral study. 3: 10-20.'),
        block('A. Supplementary methods',2,'heading',level=1),
        block('The supplementary argument is visible.',2)]
    s.mark_sections(bs)
    assert bs[2]['type']=='heading' and bs[3]['type']=='para'


def test_bibliography_subheading_with_entries_stays_in_references():
    bs=[block('References',typ='heading',level=1),
        block('Primary sources',2,'heading',level=2),
        block('Smith J. 2004. Neutral study. 3: 10-20.',2)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_decimal_is_not_a_terminal_footnote_mark():
    assert not s.end_terminal('An increase by 0.6')
    assert not s.end_terminal('A value of 3.14')
    assert s.end_terminal('An increase. 6', [])
    assert s.end_terminal('An increase. 6', [('increase.','6')])


def test_ocr_baseline_mark_retains_textual_terminal_evidence():
    a = block('The neutral result is significant.5', first_x0=50, superscripts=[])
    assert not s.paragraph_continues(a, block('We estimated another model.', 2))
    a['text'] = 'The parameter changes by 0.6'
    assert s.paragraph_continues(a, block('(with the same controls).', 2))


def test_table_rows_do_not_estimate_body_column_edges():
    prose = line('An ordinary prose line establishes the actual column width.', 200)
    rows = [line('A numeric row 12 34 56 78', 80 + 15*i, x=100, tab=True) for i in range(5)]
    blocks = s.build_blocks(rows + [prose], 1, 10)
    assert all(b['column_x0'] == prose['x0'] and b['column_x1'] == prose['x1'] for b in blocks)


def test_wrapped_table_note_tail_keeps_its_region_despite_size_jitter():
    from test_segment_typing import block as blk, classify
    note = blk('Notes: Estimates are reported for the neutral', 100, 8, font='Neutral')
    tail = blk('comparison groups', 110, 8.5, font='Neutral')
    body = blk('The following prose starts a separate paragraph.', 150, 10, font='Neutral')
    classify([note, tail, body])
    assert tail['type'] == 'frag' and tail['table'] and tail['table_note']
    assert body['type'] == 'para'


def test_fragment_above_last_merged_piece_is_not_paragraph_glue():
    lead = block('The explanation continues', page=1, _end_page=2, top=500, bottom=600)
    fragment = block('neutral row label', page=2, typ='frag', top=400, bottom=410)
    tail = block('with additional prose.', page=3)
    merged, count = s.merge_continuations([lead, fragment, tail])
    assert count == 1 and 'row label' not in merged[0]['text']
    assert merged[1] is fragment


@pytest.mark.parametrize('text', ['u', 'αβ', 'u v'])
def test_detached_math_symbols_keep_visibility_across_merged_pieces(text):
    lead = block('The explanation continues', page=1, _end_page=2, top=500, bottom=600)
    fragment = block(text, page=2, typ='frag', top=400, bottom=410)
    tail = block('with additional prose.', page=3)
    merged, count = s.merge_continuations([lead, fragment, tail])
    assert count == 1 and text in merged[0]['text']


def test_float_only_page_requires_geometry_even_for_lowercase_continuation():
    a = block('An unfinished explanation', page=1)
    b = block('with more detail.', page=3)
    assert not s.paragraph_continues(a, b)
    a.update(top=650, bottom=700, ph=800, last_x1=500, column_x1=500, size=10)
    b.update(top=70, bottom=100, ph=800, first_x0=50, column_x0=50, size=10)
    assert s.paragraph_continues(a, b)
    a['last_x1'] = 300
    assert not s.paragraph_continues(a, b)


def test_lowercase_continuation_after_colon_introduced_display():
    lead = block('The relation is defined as follows: 5', first_x0=50,
                 superscripts=[('follows:', '5')])
    equation = block('x = y + z', typ='frag', equation=True)
    tail = block('where the symbols denote independent quantities.', page=2)
    merged, count = s.merge_continuations([lead, equation, tail])
    assert count == 1
    assert merged[0]['text'].endswith(tail['text'])
    assert merged[1] is equation


def test_colon_without_display_and_complete_sentence_do_not_continue():
    tail = block('where a separate discussion begins.', page=2)
    lead = block('The following properties:', first_x0=50, superscripts=[])
    assert not s.paragraph_continues(lead, tail)
    lead['text'] = 'This sentence is complete. 5'
    lead['superscripts'] = [('complete.', '5')]
    assert not s.paragraph_continues(lead, tail, after_display=True)


def test_author_contact_doi_and_prose_table_footnote_remain_visible():
    from test_segment_typing import block as blk, classify
    body = blk('A normal body passage establishes the ordinary text region and ends with a complete sentence.', 300)
    contact = blk('Correspondence: neutral@example.invalid', 680, 8)
    doi = blk('DOI: 10.9999/neutral.1234', 720, 8)
    note = blk('The estimates use independent observations.', 740, 7)
    for b in (body, contact, doi, note):
        b['page'] = 1
    note.update(tab=True, aside=True)
    s.classify([body, contact, doi, note], 10,
               {1: dict(h=800, w=600, figs=[[40, 735, 500, 770]])}, 1)
    assert contact['type'] == doi['type'] == note['type'] == 'note'


def test_parenthetical_page_continuation():
    a=block('The parameter increases by 0.6')
    b=block('(with the same controls).',2)
    assert s.paragraph_continues(a,b)


def test_caption_regex_does_not_split_a_wrapped_body_sentence():
    ls=[line('The estimates are presented in',100),line('Table 7. We use the same sample.',112)]
    bs=s.build_blocks(ls,1,10)
    assert len(bs)==1 and bs[0]['caption_candidate'] is False


def test_standalone_caption_keeps_its_block():
    bs=s.build_blocks([line('The sentence remains open',100),line('FIGURE 2',112),line('the sentence continues here.',160)],1,10)
    assert len(bs)==3 and bs[1]['caption_candidate']


def test_alphanumeric_appendix_table_caption():
    assert s.CAPTION_RE.match('Table B2. Neutral measurements')
    assert s.CAPTION_TITLE_RE.match('TABLE A1 Definition of variables')


def test_page_top_colon_continuation_cannot_be_heading():
    pages=[dict(pno=1,lines=[line('The definition protects',700)]),
           dict(pno=2,lines=[line('all participants:',80),line('A quotation then follows with more words.',110)])]
    s.contextual_openers(pages,10)
    ls=s.prepare_typing_lines(pages[1]['lines'],10)
    assert ls[0]['page_top_continuation'] and not ls[0].get('force_heading')
    assert not s.headingish(ls[0],10)


def test_year_prefix_is_not_a_heading():
    b=dict(line('1998 provides a useful comparison',100,size=11),n_lines=1)
    assert not s.is_heading_block(b,10)


def test_adjacent_ocr_size_is_the_heading_reference():
    ls=[line('A long ordinary sentence ends on this line.',100,size=10.5),
        line('A continuing discussion of the same estimate',114,size=11),
        line('continues with the ordinary body style.',128,size=10.5)]
    for ln in ls:ln["ocr_layer"]=True
    ls=s.prepare_typing_lines(ls,10)
    assert ls[1]['local_body']==10.5
    assert not s.headingish(ls[1],10)


def test_overprinted_multiword_runs_remain_separate_lines():
    a=line('Several neutral words form one line',100,size=10)['words']
    b=line('Another distinct run occupies the page',101,size=9)['words']
    ls=s.make_lines(a+b)
    assert len(ls)==2
    assert ls[0]['text']=='Several neutral words form one line'
    assert ls[1]['text']=='Another distinct run occupies the page'


def test_font_gap_population_uses_encoded_spaces():
    def char(text,x,size=10):return dict(text=text,x0=x,x1=x+5,bottom=110,size=size,fontname='Neutral')
    cs=[];x=0
    for _ in range(8):
        for t in 'abcd':cs.append(char(t,x));x+=5
        x+=1
    assert 0 < s.font_word_tolerances(cs)['Neutral'] < 0.15
    assert s.font_word_tolerances(cs+[char(' ',x)])=={}


def test_vector_region_labels_precede_typing():
    ws=line('Neutral chart label',91,size=8)['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws+line("Figure 2. Neutral experiment",255,size=8)["words"],[[50,100,300,250]],10)
    assert all(w.get('graphic') for w in ws)


def test_shaded_prose_is_not_a_graphic():
    ls=[line('Several ordinary words describe a neutral argument.',100+12*i) for i in range(4)]
    ws=[w for l in ls for w in l['words']]
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[40,90,500,170]],10)
    assert not any(w.get('graphic') for w in ws)


def test_abstract_label_splits_from_its_roman_body():
    ln=line('Abstract: A neutral result is presented here.',100)
    ls=s.prepare_typing_lines([ln],10)
    assert ls[0]['text']=='Abstract:' and ls[0]['force_heading']
    assert ls[1]['text']=='A neutral result is presented here.'


def test_mineru_continuation_title_is_demoted_before_joining():
    bs=[block('The effect depends on the exchange',1),block('Figure 2. Neutral graph',2,'caption'),
        block('rate.',2,'heading',level=1)]
    m.repair_continuation_titles(bs)
    joined,n=s.join_open_paragraphs(bs)
    assert n==1 and joined[0]['text']=='The effect depends on the exchange rate.'
    assert joined[1]['type']=='caption'


def test_mineru_float_caption_is_emitted_once(monkeypatch):
    monkeypatch.setattr(m,'_text_layer',lambda _:lambda _:None)
    sc=dict(pages=[dict(page_idx=0,blocks=[
        dict(type='chart',content='',bbox=[.1,.1,.9,.5],captions=[dict(content='Fig. 2. Neutral chart',bbox=[.1,.51,.9,.54])]),
        dict(type='text',content='**Fig. 2.** Neutral chart',bbox=[.1,.51,.9,.54])])])
    d=m.convert(sc,'neutral.pdf','missing.pdf')
    assert len(d['items'])==1 and d['items'][0]['type']=='caption'


def test_selfcheck_detects_material_hidden_as_references():
    bs=[dict(block('An ordinary paragraph contains several words.'),size=10),
        block('Table 4. Supplementary observations',4,'ref',table=True)]
    _,reasons=s.layout_signals(bs,4)
    assert any('给执行的 agent' in r and '[4]' in r for r in reasons)


def test_page_labels_choose_sequence_over_a_repeated_numeric_logo():
    pairs=[(p,str(p+20)) for p in range(1,8)]+[(p,'555') for p in range(1,8)]
    assert s.page_labels_from(pairs,list(range(1,8)))=={str(p):str(p+20) for p in range(1,8)}


def test_full_given_name_bibliography_is_not_resumed_as_prose():
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan. 2003. A neutral bibliographic entry.'),
        block('Brown, Taylor. 2008. A second neutral bibliographic entry.',2)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_bibliography_author_and_year_may_occupy_separate_blocks():
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan, and Taylor Brown',2,'heading',level=1),
        block('A neutral title. Example Series, 2004, 3, 20-40.',2)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_prose_inside_column_box_does_not_become_graphic():
    ws=[w for i in range(4) for w in line('A neutral discussion explains the observed result.',100+12*i,x=40)['words']]
    ws += [w for i in range(4) for w in line('A different text column accompanies this passage.',100+12*i,x=340)['words']]
    page=SimpleNamespace(bbox=(0,0,700,800),width=700,rects=[])
    s.early_float_regions(page,ws,[[35,90,320,160]],10)
    assert not any(w.get('graphic') for w in ws)


def test_numeric_table_with_shaded_header_keeps_notes_inside_region():
    cap=line('Table A2. Neutral estimates',70,size=8)['words']
    rows=[line('Group 0.12 0.23 0.34',100+14*i,size=8)['words'] for i in range(5)]
    notes=line('Standard errors are shown in parentheses.',172,size=8)['words']
    ws=cap+[w for row in rows for w in row]+notes
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    regions=s.early_float_regions(page,ws,[[40,90,500,110]],10)
    assert any(len(r)>4 for r in regions)
    assert all(w.get('tab') for row in rows for w in row)
    assert all(w.get('tab') for w in notes)


def test_candidate_rule_span_does_not_extend_into_following_notes():
    cap = line('Table 2. Neutral estimates', 70, size=8)['words']
    note = line('An explanatory sentence follows the candidate.', 169, size=8)['words']
    page = SimpleNamespace(bbox=(0, 0, 600, 800), width=600, rects=[])
    candidate = [40, 90, 500, 160, 'rules']
    regions = s.early_float_regions(page, cap + note, [candidate], 10)
    assert next(r for r in regions if len(r) > 4 and r[4] == 'rules') == candidate


def test_selfcheck_reports_overprinted_runs_to_agent():
    bs=[dict(block('A normal paragraph ends here.'),size=10,overprinted=True)]
    _,reasons=s.layout_signals(bs,1)
    assert any('duplicated-word runs' in r for r in reasons)


def test_numbered_preprint_reference_without_explicit_year_stays_excluded():
    bs=[block('References',typ='heading',level=1),
        block('[12] A. Green. A neutral technical note. arXiv:2201.00000.',2)]
    s.mark_sections(bs)
    assert bs[1]['type']=='ref'
    assert s.reference_entry_evidence(bs[1]['text'])


def test_font_spacing_preserves_consecutive_font_runs(monkeypatch):
    from pdfplumber.utils import extract_words
    chars=[dict(text=t,x0=x,x1=x+w,top=100,bottom=110,doctop=100,size=10,fontname=f,upright=True)
           for t,x,w,f in [('a',50,5,'Neutral'),('+',55,.2,'Symbol'),('b',55.2,5,'Neutral')]]
    page=SimpleNamespace(chars=chars,bbox=(0,0,600,800),width=600,height=800,
                         extract_words=lambda **kw:extract_words(chars,**kw))
    monkeypatch.setattr(s,'font_properties',lambda _: {})
    monkeypatch.setattr(s,'font_word_tolerances',lambda _: {'Neutral':.05})
    ws=s.get_words(page)
    assert [w['text'] for w in ws]==['a','+','b']


def test_multiline_bold_heading_does_not_set_its_own_body_size():
    ls=[line('Several Capitalized Words Define',100,size=11),line('A Second Heading Line Here',112,size=11),
        line('Ordinary body discussion follows the heading.',140)]
    for ln in ls[:2]:
        ln['bold']=1
        for w in ln['words']:w['bold']=True
    ls=s.prepare_typing_lines(ls,10)
    assert all(not ln.get('local_body') for ln in ls[:2])


def test_overlapping_inline_math_does_not_split_a_prose_line():
    a=line('Several neutral words form one line',100,size=10)['words']
    b=line('A mathematical span occupies this position',101,size=9)['words']
    for w in b:w['font']='MathSymbol'
    assert len(s.make_lines(a+b))==1


def test_italic_titles_inside_an_open_sentence_are_not_headings():
    a=line('The examples include the two works',100)
    b=line('Neutral Tale Different Story',112)
    for w in b['words']:w['italic']=True
    b=s.line_from_words(b['words'])|dict(band=0,col=0)
    c=line('which readers compare in the experiment.',124)
    ls=s.prepare_typing_lines([a,b,c],10)
    assert not any(l.get('force_heading') for l in ls)


def test_caption_tail_is_not_swept_into_an_adjacent_vector_region():
    label=line('Figure 3. An ordinary caption continues with',251,size=8)
    tail=line('several more neutral words.',261,size=8)
    ws=label['words']+tail['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,100,300,255]],10)
    assert not any(w.get('graphic') for w in tail['words'])


def test_local_size_evidence_cannot_promote_a_formula_lead_in():
    ln=line('The integration step gives the following expression',100,size=10)
    ln['local_body']=8
    assert not s.headingish(ln,10)


def test_author_identifier_block_is_metadata_even_away_from_abstract():
    from test_segment_typing import block as blk, classify
    a=blk('Morgan Green https://example.invalid/0000-0000-0000-000X',200)
    classify([a])
    assert a['type']=='frag'


def test_caption_context_uses_observed_leading_not_a_fixed_gap():
    ls=[line('The estimate follows the ordinary leading',100),
        line('Table 2. A wrapped mention continues here.',116)]
    bs=s.build_blocks(ls,1,10)
    assert len(bs)==1 and bs[0]['caption_candidate'] is False


def test_reference_continuation_page_does_not_resume_body_without_sentence_evidence():
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan. 2004. A long bibliographic title continues'),
        block('in the neutral proceedings edited by several authors and issued in a series of research volumes at a neutral institution.',2)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_native_small_heading_keeps_the_document_body_reference():
    ls=[line('Several ordinary words on the previous line.',100,size=11),
        line('A Short Heading',130,size=10.5),line('Several ordinary words begin the following paragraph.',155,size=11)]
    ls=s.prepare_typing_lines(ls,10)
    assert not ls[1].get('local_body')


def test_caption_tail_can_follow_a_different_font_in_the_caption_label():
    cap=line('Figure 3. An ordinary caption continues with',251,size=8)
    cap['font']='LabelBold'
    cap['words'][0]['font']='LabelBold'
    tail=line('several more neutral words.',261,size=8)
    ws=cap['words']+tail['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,100,300,255]],10)
    assert not any(w.get('graphic') for w in tail['words'])


def test_caption_tail_uses_its_own_column():
    cap=line('Figure 4. An ordinary caption continues with',251,size=8,x=350)
    tail=line('several more neutral words.',263,size=8,x=350)
    other=line('A different column continues its own prose.',262,size=10,x=40)
    ws=cap['words']+tail['words']+other['words']
    page=SimpleNamespace(bbox=(0,0,700,800),width=700,rects=[])
    s.early_float_regions(page,ws,[[350,100,650,255]],10)
    assert not any(w.get('graphic') for w in tail['words'])


def test_author_year_disambiguation_suffix_is_reference_evidence():
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan. 2004a. A neutral bibliographic title.'),
        block('Green, Morgan. 2004b. A second bibliographic title.',2,'heading',level=1)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_unvalidated_rule_span_does_not_force_adjacent_prose_into_table():
    ws=line('An ordinary passage can sit beside a ruled table.',130)['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[40,100,500,200,'rules']],10)
    assert not any(w.get('tab') for w in ws)


def test_unheaded_terminal_bibliography_resumes_after_exhibits():
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan. 2004. A neutral reference.'),
        block('Figure 2. Neutral exhibit',2,'caption'),
        block('A supplementary argument is visible.',3),
        block('of neutral proceedings. Green, Morgan. 2004a. “First neutral title.”',4),
        block('. 2004b. “Second neutral title.”',4)]
    s.mark_sections(bs)
    assert bs[2]['type']=='caption' and bs[3]['type']=='para'
    assert bs[4]['type']==bs[5]['type']=='ref'


def test_reference_boundaries_accept_unpaginated_text():
    bs=[block('References',None,'heading',level=1),
        block('Green, Morgan. 2004a. “First neutral title.”',None),
        block('Green, Morgan. 2004b. “Second neutral title.”',None)]
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs)


def test_year_led_heading_still_needs_and_can_have_real_heading_typography():
    ln=dict(line('2024 Results',100,size=16),n_lines=1)
    assert s.is_heading_block(ln,10)


def test_small_heading_label_between_disconnected_panels_is_graphic_text():
    left=line('Neutral Left',110,size=8,x=60)['words']
    right=line('Neutral Right',110,size=8,x=360)['words']
    ws=left+right
    for w in ws:w['bold']=True
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[[50,100,180,200],[350,100,480,200]],10)
    lines=[dict(s.line_from_words(ws),band=0,col=0),line('An ordinary body passage is long enough to establish the body stream and to remain visible to every reader.',300)]
    bs=s.build_blocks(lines,2,10)
    s.classify(bs,10,{2:dict(h=800,figs=[])},1)
    assert bs[0]['type']=='frag' and bs[0]['graphic']
    assert bs[1]['type']=='para'


def test_known_reference_heading_is_not_a_small_graphic_label():
    ln=line('References',100,size=8,graphic_label=True)
    bs=s.build_blocks([ln],2,10)
    s.classify(bs,10,{2:dict(h=800,figs=[])},1)
    assert bs[0]['type']=='heading'


@pytest.mark.parametrize('label,typ',[('Notes','note'),('Further reading','para')])
def test_terminal_bibliographic_entries_do_not_override_explicit_notes_or_reading(label,typ):
    bs=[block('References',typ='heading',level=1),
        block('Green, Morgan. 2004. A neutral reference.'),
        block(label,2,'heading',level=1),
        block('Green, Morgan. 2004a. “First neutral title.”',3),
        block('Green, Morgan. 2004b. “Second neutral title.”',3)]
    s.mark_sections(bs)
    assert bs[3]['type']==bs[4]['type']==typ


def test_acknowledgement_with_url_and_grant_number_remains_a_note():
    from test_segment_typing import block as blk, classify
    body=blk('A normal body passage establishes the ordinary text region and ends with a complete sentence.',300)
    note=blk('We thank the team at https://example.invalid for support through grant 2024',680,8)
    body["page"]=note["page"]=1
    classify([body,note])
    assert note['type']=='note'


@pytest.mark.parametrize('text',['journal.example.invalid/archive | 42','DOI: 10.9999/example.1234'])
def test_standalone_bibliographic_footer_is_metadata(text):
    from test_segment_typing import block as blk, classify
    body=blk('A normal body passage establishes the ordinary text region and ends with a complete sentence.',300)
    footer=blk(text,740,7)
    body["page"]=footer["page"]=1
    classify([body,footer])
    assert footer['type']=='frag' and footer['front_meta']
