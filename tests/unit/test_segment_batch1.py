from types import SimpleNamespace
from test_segment_typing import line,word,block,classify
import pytest
import segment as s


def test_cff_explicit_code_zero_keeps_adobe_glyph_name():
    from fontTools.agl import toUnicode
    top=SimpleNamespace(Encoding=['.notdef']*256,rawDict={'Encoding':2},charset=['.notdef','uni2212.variant'])
    names=s.cff_encoding_names(top,b'xx\x00\x01\x00')
    assert names=={0:'uni2212.variant'} and toUnicode(names[0])=='\u2212'


def test_encoding_differences_fill_missing_unicode_but_preserve_valid_map():
    from pdfminer.psparser import LIT
    font=SimpleNamespace(unicode_map=SimpleNamespace(cid2unichr={1:'X'}))
    spec={'BaseFont':LIT('NeutralFont'),'FontDescriptor':{},'Encoding':{'BaseEncoding':LIT('WinAnsiEncoding'),'Differences':[0,LIT('minus'),1,LIT('endash')]}}
    page=SimpleNamespace(page_obj=SimpleNamespace(resources={'Font':{'F1':spec}}),pdf=SimpleNamespace(rsrcmgr=SimpleNamespace(get_font=lambda *a:font)),flush_cache=lambda:None)
    props=s.font_properties(page);s.apply_native_case(page,props)
    assert font.unicode_map.cid2unichr[0]=='\u2212' and font.unicode_map.cid2unichr[1]=='X'


def test_unresolved_body_token_keeps_its_readable_letters_and_code_in_metadata():
    raw=dict(text='Neutral(cid:99)text',x0=50,x1=180,top=100,bottom=110,size=10,fontname='NeutralRoman')
    body=dict(raw,text='An ordinary readable body sentence stays intact.',top=120,bottom=130)
    page=SimpleNamespace(chars=[],images=[],bbox=(0,0,600,800),width=600,height=800,extract_words=lambda **k:[raw,body])
    words=s.get_words(page)
    pdf=SimpleNamespace(pages=[page])
    cache={'width_reference':{},1:dict(pno=1,w=600,h=800,words=words,figs=[])}
    blocks,_,_,_=s.from_pdf_text(pdf,[1],'auto',cache)
    for b in blocks:b['type']='para'
    items,_=s.finalize(blocks)
    assert items[0]['text']=='An ordinary readable body sentence stays intact.'
    assert items[0]['unmapped_text']==['Neutral\u27e6cid:99\u27e7text']
    assert items[0]['unmapped_glyphs']==['\u27e6cid:99\u27e7']


def test_check_reports_unresolved_glyph_even_in_hidden_table(clean):
    import check
    doc,guide=clean
    doc['items'].append(dict(id='F1',type='frag',text='\u27e6cid:99\u27e7 12.0',page=1,table=True))
    _,warns,_=check.run_checks(doc,guide)
    assert any('F1: unmapped PDF glyphs' in w for w in warns)


def test_explicit_space_anchor_out_of_order_requires_source_word_flow():
    chars=[dict(text='a',x0=10,bottom=20,size=10),dict(text=' ',x0=17,bottom=20,size=10),dict(text='b',x0=16,bottom=20,size=10)]
    assert s.source_spaces_overlap(chars)
    chars[2]['x0']=20
    assert not s.source_spaces_overlap(chars)


def test_tracking_uses_other_same_font_labels_as_group_gap_evidence():
    def tracked(text,y):
        out=[];x=50
        for token in text.split():
            for c in token:
                out.append(word(c,x,y,size=8));x=out[-1]['x1']+3
            x+=2
        for w in out:w['word_gap']=0.15
        return out
    multi=tracked('NEUTRAL LABEL',100);isolated=tracked('STATEMENT',130)
    s.learn_tracking_boundaries(multi+isolated)
    assert s.line_from_words(multi)['text']=='NEUTRAL LABEL'
    assert s.line_from_words(isolated)['text']=='STATEMENT'


def test_small_unmarked_page_foot_prose_is_a_note_but_caption_and_table_note_are_not():
    body=dict(block('An ordinary body paragraph provides enough neutral explanatory wording to establish the body region.',300,10),bottom=400)
    note=block('We acknowledge neutral help with this ordinary example.',650,8)
    mail=block('E-mail: neutral@example.invalid',680,8)
    caption=block('Figure 1. A neutral example.',710,8)
    table=block('Notes: A neutral table explanation.',740,8)
    classify([body,note,mail,caption,table])
    assert note['type']==mail['type']=='note'
    assert caption['type']=='caption' and table['type']=='frag'


def test_capital_page_continuation_needs_full_last_line_and_no_new_indent():
    a=dict(block('A neutral account remains unfinished',700),type='para',column_x0=50,column_x1=400,last_x1=300)
    b=dict(block('Another paragraph begins here.',80),type='para',page=3,column_x0=50,column_x1=400,first_x0=65)
    assert not s.paragraph_continues(a,b)
    a['last_x1']=400;b['first_x0']=50
    assert s.paragraph_continues(a,b)
    b['first_x0']=65
    assert not s.paragraph_continues(a,b)
    a['text']='A neutral account depends on'
    assert s.paragraph_continues(a,b)


def test_centered_numeric_final_line_remains_part_of_its_sentence():
    def centered(text,y):
        l=line(text,y,size=15);shift=300-(l['x0']+l['x1'])/2
        for w in l['words']:w['x0']+=shift;w['x1']+=shift
        return dict(l,**s.line_from_words(l['words']))
    blocks=s.build_blocks([centered('An ordinary report describes neutral observations in the year',100),centered('2020.',117)],2,10)
    assert len(blocks)==1 and blocks[0]['text'].endswith('year 2020.')


def test_colon_ended_standalone_label_becomes_a_heading():
    blocks=s.build_blocks([line('Neutral Considerations:',100),line('The ordinary paragraph discusses a complete neutral example.',115)],2,10)
    classify(blocks)
    assert blocks[0]['type']=='heading' and blocks[1]['type']=='para'


def test_small_type_column_gutter_is_kept_separate_from_body_column():
    ls=[line('An ordinary body passage explains a neutral result.',100+i*15,x=40) for i in range(12)]
    ls += [line('A brief side note.',100+i*15,x=350,size=8) for i in range(12)]
    words=[w for l in ls for w in l['words']]
    pdf=SimpleNamespace(pages=[SimpleNamespace(chars=[],images=[])])
    cache={'width_reference':{},1:dict(pno=1,w=600,h=800,words=words,figs=[])}
    blocks,_,_,_=s.from_pdf_text(pdf,[1],'auto',cache)
    assert len({b['key'] for b in blocks})>=2
    assert not any('result. A brief' in b['text'] for b in blocks)


def test_long_merged_bibliography_heading_still_triggers_column_retry():
    para=dict(block('An ordinary complete neutral paragraph.'),type='para')
    mixed=dict(block('References Example A (2020), 12(3):10-20. '+('Additional neutral entry text. '*40),600),type='note')
    _,reasons=s.layout_signals([para,mixed],2)
    assert any('bibliography heading merged' in r for r in reasons)


def test_only_numeric_centered_suffix_bypasses_indent_not_address_lines():
    lines=[line('A Neutral Organization',100,x=150),line('An Ordinary Avenue',112,x=160)]
    blocks=s.build_blocks(lines,2,10)
    assert len(blocks)==2


def test_unmapped_evidence_survives_grouping_and_continuation():
    a=dict(block('x y z',100),math_style=True,type='frag')
    b=dict(block('a b c',115),math_style=True,type='frag',unmapped_glyphs=['\u27e6cid:7\u27e7'],unmapped_text=['\u27e6cid:7\u27e7'])
    rows=[a,b];s.group_display_rows(rows)
    assert len(rows)==1 and rows[0]['unmapped_glyphs']==['\u27e6cid:7\u27e7']
    assert rows[0]['unmapped_text']==['\u27e6cid:7\u27e7']


def test_independent_small_type_column_is_body_not_footnote():
    body=dict(block('A neutral body paragraph explains an ordinary scientific example in sufficient detail.',100),bottom=400)
    side=block('A separate small-type abstract explains an ordinary result in a narrow column.',110,8,independent_text=True)
    classify([body,side])
    assert side['type']=='para'


def test_large_contact_url_does_not_become_an_outline_heading():
    b=block('Neutral material is available at https://example.invalid',100,15)
    assert not s.is_heading_block(b,10)


def test_starred_table_note_is_not_body_prose():
    note=block('* Note: Ordinary table details explain the neutral measurements.',200,8)
    classify([note])
    assert note['type']=='frag' and note.get('table')


def test_centered_unicode_math_is_not_a_numeric_prose_suffix():
    a=line('A neutral expectation becomes',100)
    b=line('\U0001d445 = 0.5',115)
    shift=(a['x0']+a['x1']-b['x0']-b['x1'])/2
    for w in b['words']:w['x0']+=shift;w['x1']+=shift
    b=dict(b,**s.line_from_words(b['words']))
    blocks=s.build_blocks([a,b],2,10)
    assert len(blocks)==2 and '=' not in blocks[0]['text']


def test_copyright_footer_is_metadata_not_an_unmarked_note():
    body=dict(block('An ordinary body paragraph supplies enough neutral wording for a running text region.',300),bottom=400)
    footer=block('\u00a9 2020 Neutral Example Institute',740,8)
    classify([body,footer])
    assert footer['type']=='frag'


def test_footer_metadata_is_never_absorbed_by_a_continuing_body_paragraph():
    a=dict(block('An unfinished neutral account',650),type='para')
    footer=dict(block('\u00a9 2020 Neutral Example Institute',740,8),type='frag',front_meta=True)
    b=dict(block('continues on the next ordinary page.',80),page=3,type='para')
    out,n=s.merge_continuations([a,footer,b])
    assert n==1 and len(out)==2
    assert out[0]['text']=='An unfinished neutral account continues on the next ordinary page.'
    assert out[1]['type']=='frag' and out[1]['front_meta']
