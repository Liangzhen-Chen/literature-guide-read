"""Synthetic overprints, header regions and prose/float boundaries."""
from types import SimpleNamespace

import pytest
import segment as s
from test_segment_typing import block, line, word


def test_partial_glyph_overprints_keep_real_double_letters():
    chars = [dict(text=c,fontname='Neutral',size=10,top=100,bottom=110,
                  x0=50+5*i,x1=55+5*i) for i,c in enumerate('A green bell')]
    copies = [dict(c,x0=c['x0']+.2,x1=c['x1']+.2) for c in chars if c['text'] in 'Agbl']
    assert s.deduplicate_text_runs(chars+copies)==chars
    assert s.deduplicate_text_runs(chars+[dict(chars[0])])==chars+[dict(chars[0])]


def test_rules_split_at_an_intervening_caption():
    rules = [dict(x0=40,x1=500,top=y,bottom=y+1) for y in (100,140,200,300,340,400)]
    regions=s.rule_tables(rules,0,0,600,[line('Table 2. Neutral results',270)])
    assert len(regions)==2
    assert regions[0][3]<270<regions[1][1]


def test_table_notes_do_not_expand_through_smaller_body_prose():
    cap=line('Table 2. Neutral estimates',70,size=8)
    source=line('Source: Neutral calculations.',169,size=8,italic=True)
    body=line('A new explanatory paragraph starts outside the table.',185,size=9.4)
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    box=[40,90,500,160,'table']
    regions=s.early_float_regions(page,cap['words']+source['words']+body['words'],[box],10)
    assert next(r for r in regions if len(r)>4 and r[4]=='table')[3]<body['top']
    assert not any(w.get('tab') for w in body['words'])


def test_baseline_prose_size_excludes_many_small_indices():
    ws=[word('where',50,100,10),word('parameters',90,100,10)]
    ws += [word('i',160+i*4,105,5,italic=True) for i in range(30)]
    assert s.line_from_words(ws)['size']==10


def test_body_size_raised_note_mark_delimits_a_note():
    ordinary=line('The ordinary paragraph continues on the following page',580)
    first=word('2',50,622,6)
    rest=line('A neutral explanatory note has several ordinary words.',625,58,italic=True)
    note=dict(s.line_from_words([first]+rest['words']),band=0,col=0)
    p=dict(h=800,lines=[ordinary,note,line('Its final explanatory sentence ends here.',637,italic=True)])
    s.mark_footnote_lines([p],10)
    assert not ordinary.get('footnote') and all(l.get('footnote') for l in p['lines'][1:])
    bs=s.build_blocks(p['lines'],2,10)
    assert len(bs)==2 and bs[1]['footnote']


def test_indented_quotation_after_colon_is_not_a_note():
    lead=block('A neutral author introduces this quotation:',600)
    quote=dict(block('An indented quotation continues without finishing',630,9),x0=65,n_lines=3)
    bs=[lead,quote]
    s.classify(bs,10,{2:dict(h=800,w=600,figs=[])},2)
    assert quote['type']=='para' and quote['quotation']


def test_wrapped_citation_is_not_a_list_item():
    rows=[line('A neutral discussion refers to Example (2020,',100),
          line('p. 12) and continues the argument without a break.',112),
          line('A further discussion refers to Sample (2021,',124),
          line('p. 15) and completes the ordinary sentence.',136)]
    bs=s.build_blocks(rows,2,10)
    assert not any(b.get('list') for b in bs)
    for b in bs:b['type']='para'
    assert len(s.merge_continuations(bs)[0])==1


def test_word_equation_uses_number_and_indentation():
    rows=[line('This ordinary paragraph introduces a displayed equation:',100),
          line('Total balance = annual income minus annual expenditure (1)',125,90),
          line('This ordinary paragraph explains the resulting balance.',155)]
    s.mark_display_lines(rows,'NeutralRoman',10)
    assert rows[1].get('display_region')
    assert not rows[0].get('display_region') and not rows[2].get('display_region')


def test_geometric_title_mark_does_not_prevent_cover_matching():
    cover=dict(block('A Neutral Investigation of Markets',100,18),page=1)
    meta=dict(block('Suggested citation: https://example.org/article',180),page=1)
    title=dict(block('A NEUTRAL INVESTIGATION OF MARKETS 1',100,9.96),bold=1,title_suffix='1')
    bs=[cover,meta,title,block('The ordinary article paragraph starts here.',250)]
    info={1:dict(h=800,w=600,figs=[]),2:dict(h=800,w=600,figs=[])}
    s.classify(bs,10,info,1)
    assert all(b['page']==2 for b in bs)
    assert title['level']==0 and not title['text'].endswith('1')
    _,reasons=s.layout_signals(bs,1,info)
    assert not any('disagrees with the detected cover' in r for r in reasons)


def test_names_and_affiliation_above_title_remain_visible():
    names=dict(block('Alex Example and Sam Neutral',70,11),page=1)
    affiliation=dict(block('Department of Neutral Studies, Example University',85,10),page=1)
    title=dict(block('A Neutral Investigation',130,18),page=1)
    body=dict(block('The ordinary body paragraph provides a complete sentence.',220),page=1)
    bs=[names,affiliation,title,body]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    items,_=s.finalize(bs)
    assert names['byline'] and affiliation['byline']
    assert items[0]['type']=='para' and 'Example University' in items[0]['text']


def test_metadata_wrap_stays_out_of_body():
    title=dict(block('A Neutral Investigation',80,18),page=1)
    label=dict(block('Keywords: neutral examples, ordinary observations,',200,8),page=1)
    tail=dict(block('Additional neutral terms.',211,8),page=1)
    body=dict(block('The ordinary body paragraph provides a complete sentence.',250),page=1)
    bs=[title,label,tail,body]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    assert label['type']==tail['type']=='frag' and body['type']=='para'


def test_placeholder_length_does_not_change_typographic_weight():
    ws=[word('ordinary',50,100,10),word('words',100,100,10),word('⟦cid:72⟧',140,100,18)]
    assert s.line_from_words(ws)['size']==10
    assert s.body_size(ws)==10


def test_right_metadata_column_is_separate_from_abstract():
    rows=[line('Abstract',100,bold=True),line('Article history',100,420,size=8),
          line('The neutral abstract explains an ordinary comparison',112),
          line('Received 1 March 2020',112,420,size=8),
          line('Several ordinary observations support the comparison',124),
          line('Accepted 1 April 2020',124,420,size=8),
          line('The final abstract sentence ends here.',136),
          line('Keywords: neutral examples',136,420,size=8),
          line('1. Introduction',180,bold=True)]
    ws=[w for l in rows for w in l['words']]
    p=dict(pno=1,w=600,h=800,words=ws,lines=rows)
    s.repair_front_regions([p],10)
    abstract=[l for l in p['lines'] if l.get('abstract')]
    meta=[l for l in p['lines'] if l.get('front_meta')]
    assert len(abstract)>=3 and len(meta)>=3
    assert all('Received' not in l['text'] and 'Accepted' not in l['text'] for l in abstract)


def test_metadata_heading_warns_the_agent():
    bs=[dict(block('Keywords',100),type='heading',level=1),
        dict(block('The ordinary paragraph contains a complete neutral sentence.',150),type='para')]
    _,reasons=s.layout_signals(bs,1)
    assert any('metadata labels entered the outline' in r for r in reasons)


def test_hanging_caption_chain_reaches_its_ruling_edge():
    cap=line('Table 2: A neutral comparison of ordinary observations',50)
    tail=line('across several independent groups',62,92)
    header=line('Variable       Estimate       Deviation',95)
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[],
                         edges=[dict(x0=40,x1=550,top=82,orientation='h')])
    s.early_float_regions(page,cap['words']+tail['words']+header['words'],[],10)
    group=cap['words'][0].get('caption_group')
    assert group is not None and all(w.get('caption_group')==group for w in tail['words'])
    assert not any(w.get('caption_group')==group for w in header['words'])


def test_small_unmarked_table_note_stays_with_table_but_marked_note_does_not():
    body=block('An ordinary paragraph introduces the neutral estimates.',400)
    caption=block('Table 2. Neutral estimates',480)
    table=dict(block('Variable Estimate Deviation 1 2 3 4 5 6',500,8),tab=True,n_lines=8,bottom=620)
    note=dict(block('Independent observations describe the neutral estimates.',630,8),n_lines=2)
    foot=dict(block('1 A separate numbered footnote explains the example.',670,8),n_lines=2)
    bs=[body,caption,table,note,foot]
    s.classify(bs,10,{2:dict(h=800,w=600,figs=[])},2)
    assert note['type']=='frag' and note['table']
    assert foot['type']=='note' and not foot.get('table')


def test_unresolved_symbol_cid_is_visible_without_guessing_an_encoding_byte():
    raw=dict(text='(cid:39)',x0=50,x1=56,top=100,bottom=110,size=10,fontname='ABCDEF+Symbol')
    page=SimpleNamespace(chars=[],images=[],bbox=(0,0,600,800),width=600,height=800,
                         extract_words=lambda **kw:[raw])
    ws=s.get_words(page)
    assert ws[0]['text']=='⟦cid:39⟧'
    assert ws[0]['unmapped_sources'][0]['codes']==['⟦cid:39⟧']


def test_unshaded_final_cells_continue_a_table_without_absorbing_prose():
    rows=[line('Table 2. Neutral definitions',70,size=8),
          line('First label',110,size=8),line('A first neutral definition',110,200,size=8),
          line('Second label',169,size=8),line('Another neutral definition',169,200,size=8),
          line('The ordinary paragraph spans both columns and stays visible.',195,size=9.4)]
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    box=[40,90,500,160,'table']
    s.early_float_regions(page,[w for l in rows for w in l['words']],[box],10)
    assert all(w.get('tab') for l in rows[3:5] for w in l['words'])
    assert not any(w.get('tab') for w in rows[-1]['words'])


def test_deduplication_survives_font_map_cache_refresh(monkeypatch):
    from pdfplumber.utils import extract_words
    cs=[dict(text=c,fontname='Neutral',size=10,x0=50+5*i,x1=55+5*i,
             top=100,bottom=110,doctop=100,upright=True) for i,c in enumerate('A green bell')]
    cs += [dict(c,x0=c['x0']+.2,x1=c['x1']+.2) for c in cs]
    class Page:
        width,height,bbox=600,800,(0,0,600,800)
        objects={'char':cs}
        @property
        def chars(self):return self.objects['char']
        def extract_words(self,**kw):return extract_words(self.chars,**kw)
    monkeypatch.setattr(s,'font_properties',lambda _: {})
    monkeypatch.setattr(s,'apply_native_case',lambda p,_:p.objects.update(char=list(cs)))
    assert [w['text'] for w in s.get_words(Page())]==['A','green','bell']


def test_touching_source_runs_join_only_without_a_source_space():
    left=word('neu',50,100)
    right=word('tral',65,100)
    assert s.line_from_words([left,right])['text']=='neutral'
    left=dict(word('of',50,100),space_after=True)
    right=word('firms',60,100)
    assert s.line_from_words([left,right])['text']=='of firms'


def test_interleaved_space_from_another_baseline_is_not_ocr_evidence():
    cs=[dict(text='a',x0=50,bottom=110,size=10),dict(text=' ',x0=70,bottom=200,size=10),
        dict(text='b',x0=65,bottom=110,size=10)]
    assert not s.source_spaces_overlap(cs)


def test_geometric_reassembly_retains_ocr_encoded_word_spaces(monkeypatch):
    from pdfplumber.utils import extract_words
    cs=[dict(text=c,x0=x,x1=r,top=100,bottom=110,doctop=100,size=10,
             fontname='Neutral',upright=True) for c,x,r in
        [('o',50,55),('f',55,74),(' ',70,75),('f',69,74),('i',74,79),('r',79,84),('m',84,89),('s',89,94)]]
    page=SimpleNamespace(chars=cs,bbox=(0,0,600,800),width=600,height=800,
                         extract_words=lambda **kw:extract_words(cs,**kw))
    monkeypatch.setattr(s,'font_properties',lambda _: {})
    assert s.line_from_words(s.get_words(page))['text']=='of firms'


def test_duplicate_layer_lookup_uses_position_not_a_source_order_window():
    text='A green bell and several other ordinary letters repeat across this line'
    cs=[dict(text=c,fontname='Neutral',size=10,top=100,bottom=110,x0=20+5*i,x1=25+5*i)
        for i,c in enumerate(text)]
    cs += [dict(text='a',fontname='Neutral',size=10,top=200,bottom=210,x0=i*5,x1=i*5+5)
           for i in range(30)]
    copies=[dict(c,x0=c['x0']+.2,x1=c['x1']+.2) for c in cs]
    assert s.deduplicate_text_runs(cs+copies)==cs


def test_overprinted_hidden_metadata_is_not_a_body_text_warning():
    bs=[dict(block('A Neutral Investigation',70,18),type='heading',level=0),
        dict(block('The ordinary body paragraph provides a complete neutral sentence.',150),type='para'),
        dict(block('Copyright 2020. Neutral distribution terms.',680,8),type='frag',front_meta=True,overprinted=True)]
    _,reasons=s.layout_signals(bs,1)
    assert not any('duplicated-word runs' in r for r in reasons)


def test_small_abstract_is_prose_and_source_repetition_is_preserved():
    text='This ordinary abstract explains a neutral comparison and describes several independent observations.'
    title=dict(block('A Neutral Investigation',70,18),page=1)
    label=dict(block('Abstract',140,8),page=1,force_heading=True)
    abstract=dict(block(text,155,8),page=1,n_lines=3)
    keywords=dict(block('Keywords: neutral examples',220,8),page=1)
    licence=dict(block('Creative Commons License',245,8),page=1)
    body=dict(block(text,100,10),page=2,n_lines=3)
    bs=[title,label,abstract,keywords,licence,body]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[]),2:dict(h=800,w=600,figs=[])},1)
    assert label['type']=='heading' and abstract['type']==body['type']=='para'
    assert keywords['type']==licence['type']=='frag'
    assert abstract['text']==body['text']==text


@pytest.mark.parametrize('start,space_bounds',[(84.2,(81.7,87.5)),(85,(85,85))])
def test_explicit_space_spanning_word_edges_survives_geometric_reassembly(monkeypatch,start,space_bounds):
    def char(text,x0,x1):
        return dict(text=text,x0=x0,x1=x1,top=100,bottom=110,size=10,fontname='Neutral')
    cs=[char(c,50+5*i,55+5*i) for i,c in enumerate('neutral')]
    cs += [char(' ',*space_bounds)]
    cs += [char(c,start+5*i,start+5*i+5) for i,c in enumerate('words')]
    tokens=[dict(cs[0],text='neutral',x1=85),dict(cs[-5],text='words',x1=start+25)]
    page=SimpleNamespace(chars=cs,bbox=(0,0,600,800),width=600,height=800,
                         extract_words=lambda **kw:tokens)
    monkeypatch.setattr(s,'font_properties',lambda _: {})
    monkeypatch.setattr(s,'source_spaces_overlap',lambda _:False)
    ws=s.get_words(page)
    assert ws[0]['space_after'] and ws[1]['space_before']
    assert s.line_from_words(ws)['text']=='neutral words'
