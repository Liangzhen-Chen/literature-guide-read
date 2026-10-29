from types import SimpleNamespace
import pytest
import segment as s


def word(text,x,y,size=10,bold=False,italic=False):
    return dict(text=text,x0=x,x1=x+max(3,len(text)*size/2),top=y,bottom=y+size,size=size,
                font='NeutralItalic' if italic else 'NeutralBold' if bold else 'NeutralRoman',bold=bold,italic=italic)


def line(text,y,x=50,size=10,bold=False,italic=False):
    words=[]
    for token in text.split():
        w=word(token,x,y,size,bold,italic)
        words.append(w)
        x=w['x1']+3
    return dict(s.line_from_words(words),band=0,col=0)


def block(text,y=100,size=10,**kw):
    return dict(text=text,page=2,key=(0,0),top=y,bottom=y+size,x0=50,x1=400,size=size,
                bold=0,n_lines=1,ph=800,pw=600,**kw)


def classify(blocks,body=10):
    s.classify(blocks,body,{b['page']:dict(h=800,w=600,figs=[]) for b in blocks},1)
    return blocks


def test_numeric_citation_tail_across_layout_band_stays_with_prose():
    lead = block('The ordinary comparison follows earlier evidence (see Neutral Agency', 600,
                 font='NeutralRoman', line_gap=5)
    tail = block('Office, 2020).', 615, font='NeutralRoman', line_gap=5)
    tail['key'] = (1, 0)
    classify([lead, tail])
    assert lead['type'] == tail['type'] == 'para'
    joined, count = s.merge_continuations([lead, tail])
    assert count == 1 and len(joined) == 1
    assert joined[0]['text'].endswith('Neutral Agency Office, 2020).')


def test_citation_tail_needs_matching_style_and_normal_line_gap():
    lead = dict(block('The ordinary comparison follows evidence (see Green', 600),
                type='para', font='NeutralRoman', line_gap=5)
    tail = dict(block('2020).', 650), font='NeutralRoman')
    assert not s.bracket_wrap(lead, tail)
    tail.update(top=615, font='NeutralItalic')
    assert not s.bracket_wrap(lead, tail)


def test_list_wraps_currency_without_splitting_or_joining_items():
    lines=[line('• A neutral choice costs',100),line('£50 for each person.',112,x=58),
           line('• Another neutral choice costs',135),line('£80 for each person.',147,x=58)]
    # Text begins after the standalone bullet at x=58.
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and all(b['list'] and b['type']=='para' for b in blocks)
    assert '£50' in blocks[0]['text'] and '£80' in blocks[1]['text']
    assert len(s.merge_continuations(blocks)[0])==2


def test_repeated_lost_marker_ink_preserves_list_boundaries():
    lines=[line('A neutral first choice',100,x=70),line('Another neutral choice',130,x=70)]
    boxes=[(55,60,100,110),(55,60,130,140)]
    for ln in lines:
        for w in ln['words']:w['unmapped_boxes']=boxes
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and all(b['type']=='para' and b['list'] for b in blocks)


def test_repeated_hanging_indent_identifies_unmarked_items():
    lines=[line('A neutral choice requires',100),line('some additional explanation.',112,x=65),
           line('Another choice requires',135),line('some different explanation.',147,x=65)]
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and all(b['type']=='para' and b['list'] for b in blocks)


def test_short_prose_rows_are_not_a_table_without_cell_alignment():
    blocks=[block(t,100+i*15) for i,t in enumerate(['A first neutral sentence ends here.',
            'A second neutral sentence ends here.','A third neutral sentence ends here.'])]
    classify(blocks)
    assert all(b['type']=='para' and not b.get('table') for b in blocks)


def test_interior_cell_boundaries_establish_table_rows():
    blocks=[block('Item value',100+i*15,cell_edges=[[200]]) for i in range(3)]
    classify(blocks)
    assert all(b['type']=='frag' and b.get('table') for b in blocks)


@pytest.mark.parametrize('text,size,bold',[('benefits of a neutral method',15,0),('why choose this method?',12,0),('why choose this method?',10,1)])
def test_clear_typography_overrides_lowercase_and_question_ending(text,size,bold):
    assert s.is_heading_block(dict(text=text,size=size,bold=bold,n_lines=1),10)


def test_two_line_bold_heading_stays_separate_from_roman_body():
    lines=[line('2. A Neutral Investigation of',100,bold=True),line('Several Ordinary Choices',112,bold=True),
           line('The body explains an ordinary observation.',124)]
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading' and blocks[0]['n_lines']==2
    assert blocks[1]['type']=='para'


def test_runin_heading_splits_at_style_change():
    head=[word('2.1.2.1.',50,100,italic=True),word('Neutral',95,100,italic=True),word('Scale.',135,100,italic=True)]
    tail=[word('An',170,100),word('ordinary',190,100),word('observation',235,100),word('follows.',295,100)]
    blocks=s.build_blocks([dict(s.line_from_words(head+tail),band=0,col=0)],2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading' and blocks[0]['text']=='2.1.2.1. Neutral Scale.'
    assert blocks[1]['type']=='para' and blocks[1]['text']=='An ordinary observation follows.'


def test_runin_last_line_joins_its_previous_bold_heading_line():
    first=line('A Longer Styled Heading Continues',100,bold=True)
    last=dict(s.line_from_words([word('Here.',50,112,bold=True),word('The',85,112),word('body',110,112),word('starts.',140,112)]),band=0,col=0)
    blocks=s.build_blocks([first,last],2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['text']=='A Longer Styled Heading Continues Here.'
    assert blocks[0]['type']=='heading' and blocks[1]['type']=='para'


def test_italic_paragraph_tail_is_not_a_runin_heading():
    first=line('An ordinary italic paragraph has several words',100,italic=True)
    last=dict(s.line_from_words([word('ending.',50,112,italic=True),word('(Code',90,112),word('12)',125,112)]),band=0,col=0)
    blocks=s.build_blocks([first,last],2,10)
    classify(blocks)
    assert all(b['type']!='heading' for b in blocks)


def test_standalone_italic_phrase_is_a_heading_before_roman_body():
    blocks=s.build_blocks([line('A neutral concept',100,italic=True),line('The following body explains the concept.',112)],2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading' and blocks[1]['type']=='para'


def test_case_map_repair_requires_native_encoding_and_advance_agreement():
    chars=[dict(text='a',fontname='Neutral',size=10,x0=0,x1=7),dict(text='a',fontname='Neutral',size=10,x0=0,x1=5)]
    s.repair_case_maps(chars,{'Neutral':dict(cases={'a':[('A',0.7),('a',0.5)]})})
    assert [c['text'] for c in chars]==['A','a']
    ambiguous=[dict(text='a',fontname='Neutral',size=10,x0=0,x1=7)]
    s.repair_case_maps(ambiguous,{'Neutral':dict(cases={'a':[('A',0.7),('a',0.7)]})})
    assert ambiguous[0]['text']=='a'


def test_pdf_descriptor_weight_and_embedded_weight_are_style_evidence(monkeypatch):
    from pdfminer.psparser import LIT
    from pdfminer.pdftypes import PDFStream
    import fontTools.ttLib
    font=SimpleNamespace(usWeightClass=700,fsSelection=1)
    monkeypatch.setattr(fontTools.ttLib,'TTFont',lambda _: {'OS/2':font})
    spec=dict(BaseFont=LIT('NeutralFace'),FontDescriptor=dict(FontFile2=PDFStream({},b'\x00\x01\x00\x00')))
    page=SimpleNamespace(page_obj=SimpleNamespace(resources={'Font':{'F1':spec}}),pdf=SimpleNamespace())
    props=s.font_properties(page)['NeutralFace']
    assert props['bold'] and props['italic']


def test_chapter_opener_joins_tag_and_title_lines():
    blocks=[block('CH 4',50,20,font='NeutralBold'),block('A NEUTRAL',200,30,font='NeutralBold'),
            block('CHAPTER TITLE:',230,30,font='NeutralBold'),block('MORE DETAIL',260,30,font='NeutralBold'),
            block('The ordinary body begins here.',320)]
    joined=s.join_chapter_openers(blocks,10)
    classify(joined)
    assert len(joined)==2 and joined[0]['type']=='heading' and joined[0]['level']==1
    assert joined[0]['text']=='CH 4: A NEUTRAL CHAPTER TITLE: MORE DETAIL'


def test_both_authors_on_same_baseline_are_not_section_headings():
    title=block('A Neutral Investigation',50,20)
    a=block('Alex Neutral',100,12)
    b=dict(block('Sam Example',100,12),x0=250)
    abstract=block('Abstract',150)
    intro=dict(block('1 INTRODUCTION',300),bold=1)
    for b0 in [title,a,b,abstract,intro]: b0["page"]=1
    classify([title,a,b,abstract,intro])
    assert a['type']==b['type']=='frag' and intro['type']=='heading'


def test_smaller_prose_font_inside_box_is_not_table_or_footnote():
    lines=[line(t,100+i*12,size=9) for i,t in enumerate([
        'This neutral paragraph contains ordinary explanatory wording',
        'and describes a small experiment in some detail.',
        'The final line gives an additional neutral observation.'])]
    assert s.text_container([40,80,500,180],lines,12)
    b=block('This neutral explanatory paragraph remains readable.',500,9,text_box=(40,480,500,600),n_lines_override=3)
    b['n_lines']=b.pop('n_lines_override')
    classify([b],12)
    assert b['type']=='para'


@pytest.mark.parametrize('text',['Table 1?A Neutral Title','Table 2—A Neutral Title','FIGURE 1'])
def test_caption_label_recognizes_noisy_dash(text):
    assert s.CAPTION_RE.match(text)


def test_caption_does_not_absorb_lowercase_body_across_large_gap():
    a=block('Figure 1. A caption continues',100,8,type='caption')
    b=block('and an ordinary body paragraph follows.',160,type='para')
    out,merges=s.merge_continuations([a,b])
    assert len(out)==2 and merges==0
    b['top']=a['bottom']+2
    assert len(s.merge_continuations([dict(a),dict(b)])[0])==1


def test_caption_starts_a_block_even_after_an_open_sentence():
    blocks=s.build_blocks([line('A sentence remains open because',100),line('FIGURE 1',112),line('the explanation continues below the figure.',150)],2,10)
    classify(blocks)
    assert [b['type'] for b in blocks]==['para','caption','para']
    out,_=s.merge_continuations(blocks)
    assert len(out)==2 and out[0]['text'].endswith('the explanation continues below the figure.')


def test_contents_entries_remain_individual_readable_items():
    blocks=s.build_blocks([line('A Neutral Section........12',100),line('Another Section..........18',120),line('Final Section............24',140)],2,10)
    classify(blocks)
    assert len(blocks)==3 and all(b['type']=='para' and b['toc'] for b in blocks)
    assert len(s.merge_continuations(blocks)[0])==3


def test_further_reading_resumes_readable_text_after_references():
    blocks=[dict(type='heading',text='References',level=1),dict(type='para',text='A neutral bibliography entry.'),
            dict(type='frag',text='Suggested reading'),dict(type='note',text='A recommended neutral book.')]
    s.mark_sections(blocks)
    assert [b['type'] for b in blocks]==['ref','ref','heading','para']


def test_terminal_contact_page_is_readable_after_references():
    blocks=[block('References',100),block('A neutral bibliography entry.',150),
            dict(block('Tel: +44 (0)20 1234 5678',100,8),page=3),
            dict(block('https://example.org/publications',130,8),page=3),
            dict(block('Example Street, Neutral City',160,8),page=3)]
    classify(blocks)
    s.mark_sections(blocks)
    assert all(b['type']=='para' and b.get('backmatter') for b in blocks[-3:])
    assert len(s.merge_continuations(blocks[-3:])[0])==3


def test_single_variable_display_is_not_a_body_paragraph():
    ln=dict(s.line_from_words([word('X',100,100,italic=True),word('Y',120,100,italic=True),word('Z',140,100,italic=True)]),band=0,col=0)
    blocks=s.build_blocks([ln],2,10)
    classify(blocks)
    assert blocks[0]['type']=='frag' and s.is_display_equation(blocks[0])


def test_variable_rich_prose_is_not_hidden_as_a_formula():
    ln=line('Let x y z vary while the ordinary result follows.',100)
    for w in ln['words']:
        if len(w['text'])==1:w['italic']=True
    assert not s.display_variable_style([ln])


def test_superscript_reference_mark_is_kept_attached_and_linked():
    ln=s.line_from_words([word('Finding.',50,100),word('2',95,98,size=6)])
    assert ln['superscripts']==[('Finding.','2')]
    para=s.finish_block(dict(lines=[ln],page=1,key=(0,0)))
    para['type']='para'
    note=dict(type='note',text='2 An explanatory note.',page=1)
    items,_=s.finalize([para,note])
    assert items[0]['text']=='Finding.2' and s.end_terminal(items[0]['text'])
    assert items[1]['ref']=='P1'


def test_raised_powers_do_not_become_note_references():
    ln=s.line_from_words([word('m',50,100),word('2',60,98,size=6)])
    assert ln['text']=='m 2' and ln['superscripts']==[]
    ln=s.line_from_words([word('Duration',50,100),word('2',95,98,size=6)])
    para=s.finish_block(dict(lines=[ln],page=1,key=(0,0)))
    para['type']='para'
    assert s.finalize([para])[0][0]['text']=='Duration 2'


def test_hidden_list_marker_is_an_actionable_self_check_signal():
    blocks=[block('A neutral body sentence ends here.',type='para'),block('• A neutral choice',200,type='frag')]
    assert any('list markers hidden' in r for r in s.layout_signals(blocks,1)[1])


def test_character_codes_resolve_equal_advance_case_ambiguity():
    font=SimpleNamespace(unicode_map=SimpleNamespace(cid2unichr={65:'a',97:'a'}))
    s.repair_case_cids(font,{65:'A'})
    assert font.unicode_map.cid2unichr=={65:'A',97:'a'}


def test_numbered_heading_is_not_limited_to_eight_words():
    heading=dict(text='B. Evidence from a Neutral Investigation of Several Ordinary Choices',size=10,bold=0,n_lines=1)
    assert s.is_heading_block(heading,10)


@pytest.mark.parametrize('name,expected',[('Neutral.B',(True,False)),('Neutral.I',(False,True)),('Neutral-Bd2',(True,False)),('Neutralbi',(False,False))])
def test_delimited_font_style_abbreviations(name,expected):
    assert s.font_name_style(name)==expected


def test_bold_heading_last_line_with_period_stays_with_its_heading():
    lines=[line('A Longer Bold Heading Continues',100,bold=True),line('to a neutral conclusion.',112,bold=True),
           line('The ordinary body follows below.',124)]
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading'
    assert blocks[0]['text']=='A Longer Bold Heading Continues to a neutral conclusion.'


def test_symbolic_roman_display_does_not_become_prose():
    assert s.symbolic_display('T EMP = (x + y) (1.2)')
    assert not s.symbolic_display('Let x y z vary while a result follows.')


def test_uppercase_continuation_after_comma_survives_a_large_intervening_table():
    a=dict(block('The result depends on a quantity,',650),type='para')
    b=dict(block('G, whose value is measured here.',600),type='para',page=3)
    out,joins=s.merge_continuations([a,b])
    assert joins==1 and len(out)==1 and out[0]['pages']=={2,3}


def test_small_internal_box_label_does_not_become_an_outline_heading():
    box=(40,80,500,400)
    head=dict(block('A NEUTRAL BOX',100,9,text_box=box),bold=1)
    prose=block('This ordinary explanatory paragraph describes a neutral example.',150,10,text_box=box)
    label=dict(block('LABELS',250,8,text_box=box),bold=1)
    classify([head,prose,label])
    assert head['type']=='heading' and prose['type']==label['type']=='para'


def test_typography_changes_inside_small_notes_do_not_split_runin_headings():
    ln=dict(s.line_from_words([word('A',50,100,8,italic=True),word('minor',60,100,8,italic=True),
                              word('point.',85,100,8,italic=True),word('The',115,100,8),word('note',135,100,8),word('continues.',160,100,8)]),band=0,col=0)
    blocks=s.build_blocks([ln],2,10)
    assert len(blocks)==1 and not blocks[0]['force_heading']


def test_intentional_lists_and_contents_do_not_trigger_prose_self_check():
    blocks=[block('A complete neutral sentence ends here.',type='para')]
    blocks += [block('an unfinished list label',150+i*15,type='para',list=True) for i in range(15)]
    blocks += [block('a contents entry ........12',450,type='para',toc=True)]
    assert not any('lower case' in r or 'without a full stop' in r for r in s.layout_signals(blocks,3)[1])


def test_small_numbered_note_first_line_does_not_split_from_its_continuation():
    lines=[line('12 A neutral explanatory note begins with several ordinary words',100,size=8),
           line('and its explanatory text continues on the following line.',110,size=8)]
    blocks=s.build_blocks(lines,2,10)
    assert len(blocks)==1 and blocks[0]['n_lines']==2


def test_multirow_marked_byline_can_follow_a_subtitle_and_whitespace():
    title=block('A Neutral Investigation',50,20)
    subtitle=block('An Ordinary Secondary Title',75,20)
    first=block('Alex Neutral † Sam Example †',145,10)
    second=block('Taylor Sample † Morgan Person †',172,10)
    affiliation=block('† Example University',195,10)
    abstract=block('Abstract',230,12)
    for b in [title,subtitle,first,second,affiliation,abstract]: b['page']=1
    classify([title,subtitle,first,second,affiliation,abstract])
    assert first['type']==second['type']==affiliation['type']=='frag'
    assert abstract['type']=='heading'


def test_open_list_item_can_continue_across_page_but_not_into_another_item():
    a=dict(block('• A neutral explanation continues',700),type='para',list=True)
    b=dict(block('with more ordinary explanatory text.',80),type='para',page=3)
    assert s.paragraph_continues(a,b)
    assert not s.paragraph_continues(a,dict(b,list=True))


def test_long_numbered_sentence_is_not_split_at_its_first_line():
    lines=[line('1. Suppose that a neutral participant expects another ordinary outcome',100),
           line('and considers all available alternatives before deciding.',112)]
    blocks=s.build_blocks(lines,2,10)
    assert len(blocks)==1 and not s.is_heading_block(blocks[0],10)


def test_multiline_emphasized_heading_keeps_its_short_lowercase_last_line():
    lines=[line('2.2. Neutral Sources and Sample',100,bold=True),
           line('and Measurements',112,bold=True),line('The ordinary body begins here.',130)]
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading'
    assert blocks[0]['text'].endswith('and Measurements')


def test_standard_math_functions_are_not_prose_in_symbolic_display():
    assert s.symbolic_display('ln x = y + z (1.2)')
    assert not s.symbolic_display('The quantity ln x = y is defined here.')


def test_reading_section_ends_before_appendix_and_keeps_equations():
    reading=dict(block('Further reading'),type='heading',level=1)
    entry=dict(block('A neutral recommended source.'),type='frag')
    appendix=dict(block('Appendix'),type='heading',level=1)
    formula=dict(block('x = y + z'),type='frag',equation=True)
    s.mark_sections([reading,entry,appendix,formula])
    assert entry['type']=='para' and formula['type']=='frag'
    assert not formula.get('reading')


def test_indented_second_heading_line_keeps_same_style_heading():
    lines=[line('2.2. Neutral Sources and Sample',100,bold=True),
           line('and Measurements',112,x=70,bold=True),line('The ordinary body begins here.',130)]
    blocks=s.build_blocks(lines,2,10)
    classify(blocks)
    assert len(blocks)==2 and blocks[0]['type']=='heading'
    assert blocks[0]['text'].endswith('and Measurements')


def test_tracked_italic_question_label_is_not_a_variable_display():
    ln=line('W H A T I S A N E U T R A L L A B E L ?',100,italic=True)
    ln['text']='WHAT IS A NEUTRAL LABEL?'
    assert not s.display_variable_style([ln])
