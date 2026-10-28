from test_segment_typing import line, word, block, classify
import segment as s


def test_numeric_table_edges_tolerate_jitter_at_page_word_gap_scale():
    lines=[]
    for i,shift in enumerate([0,1,-1,0.5]):
        ws=[word('Neutral',40,100+i*12),word(str(10+i),150+shift,100+i*12),word(str(20+i),240-shift,100+i*12)]
        for w in ws:w['word_gap']=0.3
        lines.append(dict(s.line_from_words(ws),band=0,col=0))
    s.mark_numeric_regions(lines,10)
    assert all(l.get('tab') for l in lines)
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert all(b['type']=='frag' and b['table'] for b in bs)


def test_prose_list_with_numbers_does_not_become_numeric_table():
    lines=[line('\u2022 A neutral item costs 12 units for each person.',100+i*15) for i in range(4)]
    s.mark_numeric_regions(lines,10)
    assert not any(l.get('tab') for l in lines)
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert len(bs)==4 and all(b['type']=='para' for b in bs)


def test_contents_page_includes_its_heading_but_an_isolated_entry_stays_readable():
    lines=[line('Contents',70,bold=True)]+[line('Neutral topic ........ '+str(i+1),100+i*12) for i in range(4)]
    s.mark_contents_page(lines)
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert all(b['type']=='frag' for b in bs)
    lone=[line('A neutral entry ........ 12',100),line('An ordinary complete paragraph follows here.',130)]
    s.mark_contents_page(lone)
    assert not any(l.get('contents_page') for l in lone)


def test_abstract_uses_its_own_gutter_and_cover_sheet_is_hidden():
    title=line('A Neutral Scientific Investigation',70,size=20,bold=True)
    cover=dict(pno=1,w=600,h=800,words=title['words'],lines=[dict(title,band=0,col=0)])
    lines=[line('A Neutral Scientific Investigation',70,size=20,bold=True),
           line('Received: 1 January',200,size=8),line('Accepted: 2 February',215,size=8),
           line('Abstract.',200,x=250,size=9,bold=True),
           line('A neutral abstract explains an ordinary scientific investigation.',215,x=250,size=9),
           line('Keywords: neutral',270,size=8),line('1. Introduction',350,size=12,bold=True),
           line('The ordinary body begins here.',380)]
    page=dict(pno=2,w=600,h=800,words=[w for l in lines for w in l['words']],lines=lines)
    s.repair_front_regions([cover,page],10)
    assert all(l.get('front_meta') for l in cover['lines'])
    abstract=[l for l in page['lines'] if l.get('abstract')]
    assert any('explains' in l['text'] for l in abstract)
    bs=s.build_blocks(page['lines'],2,10);classify(bs)
    assert all(b['type']=='para' for b in bs if b.get('abstract'))
    assert all(b['type']=='frag' for b in bs if b.get('front_meta'))


def test_numbered_bold_heading_is_not_a_hanging_list():
    lines=[line('3.1. A Neutral Section Continues',100,bold=True),line('with More Neutral Detail',112,x=65,bold=True),
           line('An ordinary paragraph starts below.',140)]
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert bs[0]['type']=='heading' and not bs[0]['list']
    assert bs[0]['text'].endswith('Neutral Detail')


def test_heading_continuation_on_its_own_baseline_before_roman_body():
    lines=[line('2.1. An Ordinary Neutral Heading Continues',100,italic=True),line('Further',112,italic=True),
           line('The ordinary body begins on the next line.',124,x=62)]
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert len(bs)==2 and bs[0]['type']=='heading' and bs[0]['text'].endswith('Further')
    assert not bs[1]['text'].startswith('Further')


def test_slightly_smaller_runin_prefix_splits_at_style_change():
    ws=[word('2.1.',50,100,9.4,bold=True),word('Neutral',70,100,9.4,bold=True),word('Heading.',110,100,9.4,bold=True),
        word('Ordinary',160,100,10),word('body',205,100,10),word('continues.',235,100,10)]
    bs=s.build_blocks([dict(s.line_from_words(ws),band=0,col=0)],2,10);classify(bs)
    assert len(bs)==2 and bs[0]['type']=='heading' and bs[1]['type']=='para'


def test_italic_identifiers_in_prose_are_not_standalone_headings():
    lines=[line('A complete neutral paragraph ends here.',80),
           line('Metric_1yr, Metric_2yr, and Metric_3yr,',100,italic=True),line('are measured in ordinary units for this example.',112)]
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert not any(b['type']=='heading' for b in bs)


def test_differentials_with_indices_remain_a_display_without_mapped_operators():
    lines=[line('mk rk dFk ck dFk rk mk ck',100,italic=True),line('mk rk dFk ck dFk rk mk ck',130,italic=True)]
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert all(b['type']=='frag' and b.get('equation') for b in bs)
    assert not any(b.get('list') for b in bs)


def test_sparse_chart_label_before_caption_is_not_an_outline_heading():
    lines=[line('A neutral axis label',170,size=12),line('Figure 1. A neutral chart',190),
           line('The ordinary body starts with a complete neutral sentence.',230)]
    s.mark_graphic_labels(lines,10)
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert bs[0]['type']=='frag' and not bs[0].get('table')
    assert bs[1]['type']=='caption' and bs[2]['type']=='para'


def test_byline_fragments_emit_one_visible_paragraph_after_classification():
    rows=[dict(block('Alex Neutral',100),type='frag',byline=True),dict(block('Sam Example',115),type='frag',byline=True)]
    items,_=s.finalize(rows)
    assert len(items)==1 and items[0]['type']=='para' and items[0]['text']=='Alex Neutral Sam Example'


def test_figure_reference_sentence_does_not_hide_a_preceding_list():
    lines=[line('\u2022 A neutral list item',100),line('\u2022 Another neutral list item',115),
           line('Figure 2-2 shows these ordinary activities.',140)]
    s.mark_graphic_labels(lines,10)
    bs=s.build_blocks(lines,2,10);classify(bs)
    assert len(bs)==3 and all(b['type']=='para' for b in bs)


def test_numeric_region_does_not_hide_neighboring_column_prose():
    rows=[]
    for i in range(4):
        ws=[word('Neutral',330,100+i*12),word(str(20+i),420,100+i*12),word(str(30+i),500,100+i*12)]
        rows.append(dict(s.line_from_words(ws),band=0,col=2))
    prose=line('Ordinary prose remains in the neighboring column.',110,x=40)
    prose['x1']=280
    s.mark_numeric_regions(rows+[prose],10)
    assert all(l.get('tab') for l in rows) and not prose.get('tab')


def test_merged_bibliography_header_triggers_layout_retry_signal():
    para=dict(block('An ordinary complete neutral paragraph.'),type='para')
    mixed=dict(block('References Example A (2020) Neutral. Example 12(3):10-20.',600),type='note')
    _,reasons=s.layout_signals([para,mixed],2)
    assert any('bibliography heading merged' in r for r in reasons)


def test_intentional_cover_metadata_does_not_trigger_fragment_warning():
    para=dict(block('An ordinary complete neutral paragraph.'),type='para')
    metadata=dict(block('Received and accepted dates and other neutral scholarly metadata.',70),type='frag',front_meta=True)
    _,reasons=s.layout_signals([para,metadata],2)
    assert not any('most page text' in r for r in reasons)
