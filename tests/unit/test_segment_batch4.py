"""Synthetic page-edge, front-matter and OCR layout cases."""
import segment as s
from test_segment_typing import line, word, block


def test_citation_in_page_top_continuation_is_not_a_banner():
    rows = [line('motivation for an assumption (Neutral, pp. 12–15). The next', 80)]
    p = dict(pno=2,h=800,lines=rows)
    s.strip_margins([p],lambda p:p['lines'],lambda p,v:p.update(lines=v),[])
    assert p['lines'] == rows
    p['lines'] = [line('Vol. 5 No. 2',40)]
    s.strip_margins([p],lambda p:p['lines'],lambda p,v:p.update(lines=v),[])
    assert not p['lines']


def test_footer_metadata_does_not_hide_title_or_body():
    title = dict(block('A Neutral Investigation',150,18),page=1)
    body = dict(block('The investigation provides a complete neutral discussion.',220),page=1)
    footer = dict(block('Neutral Review, Vol. 5. Copyright © 2020. All rights reserved.',610,8),page=1)
    bs = [title,body,footer]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    assert title['type']=='heading' and title['level']==0
    assert body['type']=='para' and footer['type']=='frag'


def test_short_stacked_author_names_are_one_visible_byline():
    title=dict(block('A Neutral Investigation',100,18),page=1)
    author=dict(block('Alex Neutral and Sam Example',140,11),page=1,n_lines=3)
    body=dict(block('The body provides a neutral sentence.',220),page=1)
    bs=[title,author,body]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    items,_=s.finalize(bs)
    assert author['byline'] and items[1]['type']=='para'
    assert items[1]['text']=='Alex Neutral and Sam Example'


def test_contact_footer_does_not_release_bibliography_into_prose():
    bs = [block('References',100),block('Neutral, A. (2020). A neutral contribution.',130),
          dict(block('Example, B. (2021). Another neutral contribution.',100),page=3),
          dict(block('Author contact: a@example.org',610,8),page=3),
          dict(block('Suggested citation: https://example.org/article',630,8),page=3)]
    s.classify(bs,10,{2:dict(h=800,w=600,figs=[]),3:dict(h=800,w=600,figs=[])},2)
    s.mark_sections(bs)
    assert all(b['type']=='ref' for b in bs[:3])
    assert all(b['type']=='frag' and b['contact_footer'] for b in bs[3:])


def test_repeated_metadata_cover_is_removed_from_the_article_stream():
    cover = dict(block('A Neutral Investigation of Markets',150,20),page=1,bold=1)
    meta = dict(block('To cite this article: https://example.org/article',220),page=1)
    title = dict(block('A Neutral Investigation of Markets',150,16),page=2,bold=1)
    bs=[cover,meta,title,block('The article provides a neutral discussion.',250)]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[]),2:dict(h=800,w=600,figs=[])},1)
    assert all(b['page']==2 for b in bs) and title['level']==0


def chars(text,y,dx=0):
    return [dict(text=c,fontname='Neutral',size=10,top=y,bottom=y+10,x0=50+i*5+dx,x1=55+i*5+dx)
            for i,c in enumerate(text)]


def test_duplicate_layer_requires_matching_runs_and_displacement():
    rows=['A neutral first line','A different second line','The final neutral line']
    original=[c for i,t in enumerate(rows) for c in chars(t,100+i*14)]
    copies=[c for i,t in enumerate(rows) for c in chars(t,106+i*14,.02)]
    assert s.deduplicate_text_runs(original+copies)==copies
    assert s.deduplicate_text_runs(original+chars(rows[0],106))==original+chars(rows[0],106)
    adjacent=[c for i,t in enumerate(rows) for c in chars(t,106+i*14,100)]
    assert len(s.deduplicate_text_runs(original+adjacent))==len(original+adjacent)


def test_logo_does_not_bridge_stacked_baselines():
    logo=dict(word('Logo',20,35,30),baseline=65)
    a=dict(word('Neutral Review',60,40,8),baseline=48)
    b=dict(word('Volume 5',60,50,8),baseline=58)
    ls=s.make_lines([logo,a,b])
    assert len(ls)==2 and not any('Neutral Review Volume' in l['text'] for l in ls)


def test_repeated_formula_parts_are_not_a_duplicate_text_layer():
    rows=['x + y','x + z','y + z']
    original=[c for i,t in enumerate(rows) for c in chars(t,100+i*14)]
    repeated=[c for i,t in enumerate(rows) for c in chars(t,106+i*14)]
    assert s.deduplicate_text_runs(original+repeated)==original+repeated


def test_ellipsis_is_not_a_contents_entry_and_neighbours_are_required():
    assert not s.toc_entry('Imports ... represent a real')
    assert not s.toc_entry('A sentence ... reaches its final word')
    bs=s.build_blocks([line('An isolated heading........12',100),line('An ordinary paragraph ends here.',120)],2,10)
    assert not any(b['toc'] for b in bs)
    ls=[line('Neutral topic........12',100+i*15) for i in range(3)]
    assert all(b['toc'] for b in s.build_blocks(ls,2,10))
    assert not s.toc_entry('A matrix ' + ('\u2026     '*200) + '1.25')


def test_ocr_title_subtitle_and_byline_stay_out_of_body():
    ls=[line('A NEUTRAL INVESTIGATION',100,size=12),line('OF MARKET CHOICES',112,size=12),
        line('AN ANALYTICAL SUBTITLE',136,size=11),line('By ALEX NEUTRAL and SAM EXAMPLE',156,size=8),
        line('Neutral Institute of Research',170,size=9),line('The ordinary body paragraph starts here.',200)]
    for l in ls:
        shift=300-(l['x0']+l['x1'])/2
        l['x0']+=shift;l['x1']+=shift;l['ocr_layer']=True
    p=dict(pno=1,h=800,w=600,lines=ls)
    s.repair_ocr_openers([p],10)
    assert all(l['article_title'] for l in ls[:2])
    assert ls[2]['subtitle'] and all(l['byline'] for l in ls[3:5])
    assert not ls[-1].get('byline')


def test_ocr_linebreak_repair_needs_document_word_evidence():
    ls=[line('The study considers neutral mar',100),line('kets and local choices.',112),
        line('Other markets provide evidence.',140),line('This moves in',170),line('to a different place.',182)]
    for l in ls:l['ocr_layer']=True
    p=dict(lines=ls)
    s.repair_ocr_linebreaks([p])
    assert ls[0]['ocr_join_next'] and not ls[3].get('ocr_join_next')
    bs=s.build_blocks(ls,2,10)
    assert 'markets' in bs[0]['text'] and 'mar kets' not in bs[0]['text']


def test_repeated_line_edge_fragments_are_not_independent_words():
    pages=[]
    for y in [100,200]:
        ls=[line('The study considers neutral mar',y),line('kets and local choices.',y+12)]
        for l in ls:l['ocr_layer']=True
        pages.append(dict(lines=ls))
    pages.append(dict(lines=[line('Other markets provide evidence.',100)]))
    s.repair_ocr_linebreaks(pages)
    assert all(p['lines'][0]['ocr_join_next'] for p in pages[:2])


def test_real_function_words_keep_their_spaces_even_with_closed_forms():
    ls=[line('The person moved in',100),line('to the room.',112),
        line('They moved into the room.',140),line('They kept a',170),
        line('part for later.',182),line('They worked apart from neighbours.',210)]
    for l in ls:l['ocr_layer']=True
    s.repair_ocr_linebreaks([dict(lines=ls)])
    assert not ls[0].get('ocr_join_next') and not ls[3].get('ocr_join_next')


def test_indented_ocr_equation_and_verbal_gloss_form_a_display():
    ls=[line('(A - B) = (C + D)',100,x=100),line('Net total = Domestic balance',120,x=70),
        line('where the terms have their usual meanings.',150)]
    for l in ls:l['ocr_layer']=True
    s.mark_display_lines(ls,'NeutralRoman',10)
    assert all(l.get('display_region') for l in ls[:2])
    assert not ls[-1].get('display_region')


def test_numeric_title_mark_uses_superscript_geometry():
    ls=[line('Neutral Findings',100,size=18)]
    mark=dict(word('1',195,96,size=9),font=ls[0]['words'][0]['font'])
    ls=[s.line_from_words(ls[0]['words']+[mark])]
    assert s.trailing_title_marker(ls)=='1'


def test_selfcheck_reports_missing_title_only_for_a_full_pdf_layout():
    bs=[dict(block('A complete neutral paragraph ends here.'),type='para')]
    assert not any('title' in r for r in s.layout_signals(bs,1)[1])
    assert any('article title' in r for r in s.layout_signals(bs,1,{2:dict(h=800,w=600)})[1])


def test_quoted_inset_uses_its_own_measure():
    ls=[line('An ordinary paragraph finishes here.',50),
        line('\u201cThe neutral discussion starts with a claim',100,x=85),
        line('and adds a complete sentence.',112,x=85),
        line('Whether the claim holds requires evidence.\u201d',124,x=85)]
    ls[0]['x1']=450
    ls[1]['x1']=ls[2]['x1']=365
    ls[3]['x1']=370
    bs=s.build_blocks(ls,2,10)
    assert len(bs)==2 and 'Whether' in bs[1]['text']


def test_same_ocr_heading_style_has_one_rank_despite_size_jitter():
    bs=[]
    for i,size in enumerate([10.0,10.2,12.1,11.4]):
        b=block(f'Neutral Topic {chr(75+i)}',100+i*70,size)
        b.update(bold=1,italic=1,ocr_layer=True,font=f'Proxy{i%2}',x0=100,x1=300,pw=400)
        bs.append(b)
    s.classify(bs,9,{2:dict(h=800,w=400,figs=[])},1)
    assert all(b['type']=='heading' for b in bs)
    assert len({b['level'] for b in bs})==1


def test_title_warning_cannot_change_column_order(monkeypatch):
    calls=[]
    def segment(pdf,pnos,columns,cache):
        calls.append(columns)
        return dict(reasons=['missing or implausible article title'],score=0,stats=dict(two_col=0,multi_col=0))
    monkeypatch.setattr(s,'segment_text_layer',segment)
    s.choose_columns(None,[1,2],'auto')
    assert calls==['auto']


def test_captioned_table_column_numbers_do_not_hide_rows_without_a_crop():
    caption=block('Table 1. Neutral estimates',100)
    rows=[block('Neutral models (1) (2) (3)',130),block('Alpha .10 .20 .30',150),
          block('Beta .20 .30 .40',170),block('Gamma .30 .40 .50',190)]
    for b in rows:b['cell_edges']=[[240,300,360]]
    bs=[caption]+rows
    s.classify(bs,10,{2:dict(h=800,w=600,figs=[])},1)
    assert caption['type']=='caption'
    assert all(b['type']=='frag' and b['table'] and not b.get('equation') for b in rows)


def test_named_cover_title_overrides_larger_session_label():
    cover='Neutral Association\nA Study of Neutral Choices\nAuthor(s): Alex Example\nSource: Neutral Proceedings'
    session=dict(block('A LARGE SESSION LABEL',100,16),article_title=True)
    title=dict(block('A STUDY OF NEUTRAL CHOICES',145,11),subtitle=True)
    body=block('The article discusses a complete neutral example.',240)
    bs=[session,title,body]
    info={2:dict(h=800,w=600,figs=[],cover_titles=s.cover_title_candidates(cover))}
    s.classify(bs,10,info,2)
    assert title['type']=='heading' and title['level']==0
    assert session['type']=='frag' and session['front_meta']
    assert not any('disagrees' in r for r in s.layout_signals(bs,1,info)[1])
    title['text']='A DIFFERENT ARTICLE TITLE'
    assert any('disagrees' in r for r in s.layout_signals(bs,1,info)[1])


def test_repeated_cover_block_is_authoritative_under_a_session_label():
    cover=dict(block('A Neutral Investigation of Choices',100,18),page=1,bold=1)
    session=dict(block('A Broad Session Label',80,20),bold=1,article_title=True)
    title=dict(block('A Neutral Investigation of Choices',150,16),bold=1)
    bs=[cover,session,title,block('A complete neutral article paragraph ends here.',240)]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[]),2:dict(h=800,w=600,figs=[])},1)
    assert title['level']==0 and session['type']=='frag'


def test_centred_standalone_roman_section_cannot_glue_to_prose():
    ls=[line('Neutral Institute',165),line('I',190,x=297.5),
        line('The first paragraph makes a complete neutral claim.',210)]
    page=dict(pno=2,w=600,h=800,lines=ls)
    s.mark_roman_sections([page],10)
    bs=s.build_blocks(ls,2,10)
    s.classify(bs,10,{2:dict(h=800,w=600,figs=[])},1)
    assert any(b['type']=='heading' and b['text']=='I' for b in bs)
    assert not any(b['text'].startswith('I The') for b in bs)
    folio=line('I',40,x=297.5)
    s.mark_roman_sections([dict(page,lines=[folio,ls[2]])],10)
    assert not folio.get('roman_section')


def test_affiliation_continues_byline_without_bracket_punctuation():
    title=dict(block('A Neutral Investigation',100,18),page=1)
    author=dict(block('Alex Example and Sam Neutral;',130,12),page=1)
    affiliation=dict(block('department of neutral studies, example institute.',143,8),page=1)
    body=dict(block('The article makes a complete neutral claim.',240),page=1)
    bs=[title,author,affiliation,body]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    items,_=s.finalize(bs)
    assert author['byline'] and affiliation['byline']
    assert items[1]['text']==author['text']+' '+affiliation['text']
    assert not body.get('byline') and 'byline_bracket' not in title


def test_smaller_affiliation_keeps_the_existing_two_line_byline_gap():
    title=dict(block('A Neutral Investigation',100,18),page=1)
    author=dict(block('Alex Example and Sam Neutral;',130,12),page=1)
    affiliation=dict(block('department of neutral studies, example institute.',160,8),page=1,n_lines=3)
    bs=[title,author,affiliation]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    assert author['byline'] and affiliation['byline']


def test_smaller_prose_paragraph_under_byline_is_not_an_affiliation():
    title=dict(block('A Neutral Investigation',100,18),page=1)
    author=dict(block('Alex Example and Sam Neutral',130,12),page=1)
    abstract=dict(block('The study compares neutral choices. We discuss the resulting observations.',160,8),page=1,n_lines=4)
    bs=[title,author,abstract]
    s.classify(bs,10,{1:dict(h=800,w=600,figs=[])},1)
    assert author['byline'] and not abstract.get('byline')
