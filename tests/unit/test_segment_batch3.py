"""Synthetic typography, region and reading-order cases."""
from types import SimpleNamespace
import pytest
import segment as s
from test_segment_batch2 import line, word, block
from test_segment_typing import block as typed_block, classify


def test_large_title_kicker_keeps_adjacent_line_in_another_font():
    ls = [line('Overview:', 100, size=20),
          line('Neutral Research Findings', 125, size=20)]
    ls[0]['font'] = 'NeutralItalic'
    bs = s.build_blocks(ls, 1, 10)
    assert len(bs) == 1
    assert bs[0]['text'] == 'Overview: Neutral Research Findings'


@pytest.mark.parametrize('punct', ['.', ',', ';', ')'])
def test_geometric_note_before_punctuation_is_linked_and_retained(punct):
    ws = [word('Neutral', 50, 100), word('3', 86, 97, 6), word(punct, 90, 100)]
    para = s.finish_block(dict(lines=[s.line_from_words(ws)], page=1, key=(0, 0)))
    para['type'] = 'para'
    items, _ = s.finalize([para, dict(type='note', text='3 A neutral explanatory note.', page=1)])
    assert items[0]['text'] == 'Neutral3' + punct
    assert items[0]['notes'] == ['N1'] and items[1]['ref'] == 'P1'


def test_symbol_pua_mapping_requires_font_evidence():
    chars = [dict(text='\uf0b7', fontname=f, size=10, x0=0, x1=4) for f in ['Symbol', 'Neutral']]
    s.repair_case_maps(chars, {})
    assert [c['text'] for c in chars] == ['•', '\uf0b7']
    s.repair_case_maps(chars[1:], {'Neutral': dict(pua_glyphs={'\uf0b7': '•'})})
    assert chars[1]['text'] == '•'


@pytest.mark.parametrize('code,expected', [(0x22, '∀'), (0x2d, '−'), (0x41, 'Α'),
                                         (0x61, 'α'), (0xb7, '•'), (0xe5, '∑'),
                                         (0xf2, '∫'), (0x7f, '\uf07f'), (0xff, '\uf0ff')])
def test_full_adobe_symbol_range_requires_the_symbol_font(code, expected):
    ch = chr(0xf000 + code)
    chars = [dict(text=ch, fontname=f, size=10, x0=0, x1=4) for f in ['ABCDEF+Symbol', 'Neutral']]
    s.repair_case_maps(chars, {})
    assert [c['text'] for c in chars] == [expected, ch]


def test_embedded_symbol_glyph_map_takes_priority():
    chars = [dict(text='\uf041', fontname='Symbol', size=10, x0=0, x1=4)]
    s.repair_case_maps(chars, {'Symbol': dict(pua_glyphs={'\uf041': 'Z'})})
    assert chars[0]['text'] == 'Z'


def test_symbol_bullet_wraps_without_ending_the_item():
    a = line('• A neutral choice requires', 100)
    b = line('additional explanation.', 112, x=58)
    c = line('• Another choice is independent.', 140)
    bs = s.build_blocks([a, b, c], 1, 10)
    classify(bs)
    assert len(bs) == 2 and all(b['type'] == 'para' and b['list'] for b in bs)


@pytest.mark.parametrize('text', ['12 June 2009. The count was', '48 hours. The estimate is', 'X denotes the chosen value'])
def test_weak_heading_has_to_respect_sentence_boundaries(text):
    ls = [line('The preceding explanation continues with', 100), line(text, 112),
          line('reported in the next sentence.', 124)]
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert not any(b['type'] == 'heading' for b in bs)


def test_hypothesis_statements_are_prose_despite_math_prefix_and_gaps():
    ls = [line('The following statements are tested:', 100),
          line('H01: The first variable predicts the second', 126),
          line('H11: The first variable does not predict the second', 152),
          line('The ordinary discussion continues here.', 190)]
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert all(b['type'] == 'para' for b in bs if b['text'].startswith('H'))


def test_named_variables_are_allowed_in_a_display():
    ln = line('OutcomeIndex = PriceIndex + CostIndex (1)', 100)
    for w in ln['words']:
        w['font'] = 'NeutralMath'
    s.mark_display_lines([ln], 'OrdinaryBody')
    assert ln['display_region']
    bs = s.build_blocks([ln], 1, 10)
    classify(bs)
    assert bs[0]['type'] == 'frag' and bs[0]['equation']


def test_small_subscript_letter_groups_do_not_supply_sentence_words():
    ln = line('Outcome = Price + Cost', 100)
    ln['words'][1]['font'] = 'NeutralMath'
    ln['words'] += [word('abc', 90, 106, size=7), word('def', 150, 106, size=7)]
    s.mark_display_lines([ln], 'OtherBody', 10)
    assert ln['display_region']


def test_symbol_font_equation_survives_wrong_operator_unicode():
    ln = line('r t ¼ a þ b (1)', 100)
    for w in ln['words']:
        w['symbolic'] = True
    s.mark_display_lines([ln], 'OrdinaryBody')
    assert ln['display_region']


def test_operator_font_evidence_survives_a_wrong_map_and_function_word():
    ln = line('u ¿ a § b func v (2)', 100)
    for w in ln['words']:
        w['symbolic'] = w['text'] in ['¿', '§']
    numerator = line('uv', 93)
    numerator['words'][0]['italic'] = True
    s.mark_display_lines([numerator, ln], 'OtherBody', 10)
    assert ln['display_region'] and numerator['display_region']


def test_inline_math_does_not_hide_ordinary_prose():
    ln = line('The relation y = x explains the result.', 100)
    for w in ln['words']:
        w['font'] = 'OrdinaryBody'
    ln['words'][3]['symbolic'] = True
    s.mark_display_lines([ln], 'OrdinaryBody')
    assert not ln.get('display_region')


def test_inline_notation_continues_an_unfinished_prose_line():
    a = line('The reported result uses a neutral value of', 100)
    b = line('u = .42).', 112)
    for w in b['words']: w['font'] = 'NeutralMath'
    s.mark_display_lines([a, b], 'OtherBody', 10)
    assert not b.get('display_region')


def test_url_equality_sign_is_not_a_display():
    ln = line('https://example.invalid/path?value=neutral', 100)
    for w in ln['words']: w['symbolic'] = True
    s.mark_display_lines([ln], 'OtherBody', 10)
    assert not ln.get('display_region')


@pytest.mark.parametrize('italic,size', [(True, 10), (False, 8)])
def test_sentence_words_with_inline_math_survive_other_fonts_and_sizes(italic, size):
    ln = line('a = b for another neutral function.', 100, size=size)
    for w in ln['words']:
        w['font'] = 'OtherText'
        w['italic'] = italic
    ln['words'][0]['font'] = 'NeutralMath'
    s.mark_display_lines([ln], 'OrdinaryBody', 10)
    assert not ln.get('display_region')


def test_symbolic_font_flag_alone_does_not_hide_a_latin_title():
    ln = line('A neutral investigation of choices', 100, size=18)
    for w in ln['words']: w['symbolic'] = True
    s.mark_display_lines([ln], 'OrdinaryBody', 10)
    assert not ln.get('display_region')


def test_smaller_note_with_inline_math_is_still_prose():
    ln = line('The estimated values assume a = 0.1 for independent groups.', 100, size=8)
    for w in ln['words']:
        w['font'] = 'AnotherRoman'
        w['symbolic'] = True
    s.mark_display_lines([ln], 'OrdinaryBody', 10)
    assert not ln.get('display_region')


def test_numeric_citation_is_not_a_symbol_font_display():
    ln = line('[29].', 100)
    for w in ln['words']: w['symbolic'] = True
    s.mark_display_lines([ln], 'OrdinaryBody', 10)
    assert not ln.get('display_region')


def test_small_denominator_row_belongs_to_adjacent_display():
    numerator = line('u = v + w',100)
    for w in numerator['words']: w['font'] = 'NeutralMath'
    denominator = line('reference x y',112,size=7)
    for w in denominator['words']: w['font'] = 'BodyFace' if w['text']=='reference' else 'NeutralMath'
    s.mark_display_lines([numerator,denominator],'BodyFace',10)
    assert numerator['display_region'] and denominator['display_region']


@pytest.mark.parametrize('text',['1','u','KL'])
def test_small_notation_rows_need_an_established_neighbouring_display(text):
    display = line('u = v + w',100)
    part = line(text,112,size=7)
    for ln in (display,part):
        for w in ln['words']: w['font'] = 'NeutralMath'
    s.mark_display_lines([part],'BodyFace',10)
    assert not part.get('display_region')
    s.mark_display_lines([display,part],'BodyFace',10)
    assert part['display_region']


def test_logical_continuation_merges_across_a_display():
    lead = block('The relation is defined as follows:', top=100, bottom=110)
    display = block('a = b + c', typ='frag', equation=True, display_region=True, top=120, bottom=130)
    tail = block('where each symbol has a distinct role.', top=140, bottom=150)
    result, n = s.merge_continuations([lead, display, tail])
    assert result == [lead, display] and n == 1
    assert lead['text'] == 'The relation is defined as follows: where each symbol has a distinct role.'
    assert display['equation'] and display['display_region']
    assert not any('continuation' in b or 'continued_from' in b for b in result)


@pytest.mark.parametrize('ending,joins', [(':', 0), (',', 1)])
def test_new_crop_evidence_does_not_broaden_display_join_evidence(ending, joins):
    lead = block('The neutral relation is specified' + ending, top=100, bottom=110)
    display = block('u = v', typ='frag', equation=True, display_region=True,
                    join_equation=False, top=120, bottom=130)
    tail = block('where the variables have a neutral interpretation.', top=140, bottom=150)
    result, n = s.merge_continuations([lead, display, tail])
    assert n == joins and len(result) == 3 - joins


def test_capitalized_prose_keeps_a_tightly_embedded_display_in_its_paragraph():
    lead = block('The neutral relation can be expressed as', top=100, bottom=110, size=10)
    display = block('u = v', typ='frag', equation=True, display_region=True,
                    top=113, bottom=123, size=10)
    tail = block('Using this relation gives the next neutral result.', top=126, bottom=136, size=10)
    _, joins = s.merge_continuations([lead, display, tail])
    assert joins == 1


def test_tight_display_does_not_join_a_new_sentence_after_a_complete_lead_in():
    lead = block('We obtain the neutral final relation', top=100, bottom=110, size=10)
    display = block('u = v', typ='frag', equation=True, display_region=True,
                    top=113, bottom=123, size=10)
    tail = block('A separate interpretation follows here.', top=126, bottom=136, size=10)
    _, joins = s.merge_continuations([lead, display, tail])
    assert joins == 0


def test_complete_short_prose_after_equation_rows_is_not_a_formula():
    bs = [typed_block('u = v',100),typed_block('(1)',112),
          typed_block('Thus the argument is complete.',124)]
    classify(bs)
    assert bs[-1]['type'] == 'para'


def test_heading_wrap_uses_style_and_geometry_not_initial_case():
    ls = [line('3 A neutral heading continues', 100, size=12),
          line('with a lower case ending', 114, size=12),
          line('A separate body paragraph follows.', 145)]
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert bs[0]['type'] == 'heading' and 'lower case ending' in bs[0]['text']
    assert bs[-1]['type'] == 'para'


def test_body_sized_heading_in_a_distinct_font_wraps_then_stops_at_body():
    ls = [line('5.4 Neutral section title',100,body_font=False),
          line('continued in lower case',112,x=68,body_font=False),
          line('A separate body paragraph follows.',140,body_font=True)]
    for ln in ls[:2]:
        ln['font'] = 'HeadingFace'
        for w in ln['words']: w['font'] = 'HeadingFace'
    ls[-1]['font'] = 'BodyFace'
    bs = s.build_blocks(ls,1,10)
    classify(bs)
    assert len(bs) == 2 and bs[0]['type'] == 'heading' and 'continued in lower case' in bs[0]['text']
    assert bs[1]['type'] == 'para'


def test_caption_uppercase_tail_and_explicit_next_caption():
    a = typed_block('Figure 2. A neutral caption continues with', 100, 8, type='caption', font='Neutral')
    b = typed_block('An additional neutral detail.', 110, 8, type='note', font='Neutral')
    c = typed_block('Table 3. A separate caption', 120, 8, type='caption', font='Neutral')
    bs = [a, b, c]
    s.join_wrapped_blocks(bs, 10)
    assert len(bs) == 2 and 'An additional' in bs[0]['text'] and bs[1] is c


def test_explicit_caption_is_not_a_heading_continuation():
    ls = [line('3.2 Neutral estimates', 100, size=12), line('Table 3. Neutral results', 114, size=12)]
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert [b['type'] for b in bs] == ['heading', 'caption']


def test_standalone_reference_label_does_not_absorb_same_style_entries():
    ls = [line('References',100,size=12), line('Green, A. 2004. An ordinary neutral reference.',114,size=12),
          line('Blue, B. 2005. Another independent reference.',128,size=12)]
    bs = s.build_blocks(ls,1,10)
    classify(bs)
    s.mark_sections(bs)
    assert bs[0]['text'] == 'References'
    assert all(b['type'] == 'ref' for b in bs)


@pytest.mark.parametrize('labels', [['123', '123', '123'], ['10', '9', '8']])
def test_nonincreasing_labels_are_not_a_folio_sequence(labels):
    assert s.page_labels_from(list(enumerate(labels, 1)), [1, 2, 3]) == {}


def test_byline_can_follow_a_large_blank_title_area():
    title = typed_block('A neutral investigation of choices', 100, 18, font='Title')
    author = typed_block('Alex Neutral, Institute of Research', 260, 10, font='Names')
    second = typed_block('Sam Example, Research Fellow', 274, 10, font='Names')
    heading = typed_block('1 Introduction', 330, 11, font='Head')
    bs = [title, author, second, heading]
    for b in bs: b['page'] = 1
    classify(bs)
    items, _ = s.finalize(bs)
    assert author['byline'] and second['byline']
    assert any(x['type'] == 'para' and 'Alex Neutral' in x['text'] and 'Sam Example' in x['text'] for x in items)


def test_title_repeated_after_a_cover_opens_the_article():
    cover = typed_block('A neutral investigation of choices', 300, 24, font='Cover')
    title = typed_block('A neutral investigation of choices', 100, 18, font='Title')
    author = typed_block('Alex Neutral and Sam Example', 150, 20, font='Names')
    for b in (title, author): b['page'] = 3
    bs = [cover, title, author]
    s.classify(bs, 10, {2:dict(h=800,w=600,figs=[]),3:dict(h=800,w=600,figs=[])}, 2)
    assert cover['type'] == 'frag' and title.get('level') == 0 and author['byline']


def test_copyright_line_above_abstract_is_metadata():
    bs = [typed_block('A neutral investigation of choices', 100, 18),
          typed_block('© Neutral Research Group 2016', 250, 8),
          typed_block('Abstract', 280, 10)]
    for b in bs: b['page'] = 1
    classify(bs)
    assert bs[1]['type'] == 'frag'


@pytest.mark.parametrize('text', ['1 The copyright rule changes the incentives for independent creators.',
                                 'Copyright protection can affect competition in this neutral example.'])
def test_page_foot_note_discussing_copyright_stays_visible(text):
    body = typed_block('The body discussion reaches its final complete sentence here.', 690, 10)
    note = typed_block(text, 745, 7)
    classify([body, note])
    assert note['type'] == 'note'


def test_partial_width_text_container_keeps_its_columns_together():
    box = [210, 80, 590, 300]
    ls = [line('Ordinary outside discussion continues here.', y, x=30) for y in [100,112,124,136]]
    for x, label in [(220, 'BoxLeft'), (420, 'BoxRight')]:
        for y in [100,112,124]:
            ln = line(label, y, x=x)
            ln['text_box'] = tuple(box)
            ls.append(ln)
        ls.extend(line('BelowBox', y, x=x) for y in [350,362,374])
    ordered = s.order_columns(ls, [200,400], 10, [box], (600,800))
    labels = [ln['text'] for ln in ordered]
    assert max(i for i,t in enumerate(labels) if t=='BoxLeft') < labels.index('BoxRight')
    assert max(i for i,t in enumerate(labels) if t=='BoxRight') < labels.index('BelowBox')


def test_text_container_detects_paragraphs_inside_two_interleaved_columns():
    ls = []
    for y in [100,112,124,136]:
        for x in [50,350]:
            ls.append(line('An independent neutral explanation ends here.', y, x=x))
    assert s.text_container([40,80,590,170], ls, 10, column_flow=True)


def test_text_container_allows_short_sentence_ends_in_narrow_columns():
    phrases = ['A neutral example provides', 'several useful observations about',
               'independent neutral choices and their', 'possible consequences for ordinary', 'readers.']
    ls = [line(t, 100 + i*12, x=x) for i,t in enumerate(phrases) for x in [50,350]]
    assert s.text_container([40,80,590,170], ls, 10, column_flow=True)


def test_publication_notice_at_the_foot_is_metadata_even_on_one_page():
    notice = typed_block('Published by the Neutral Research Society', 740, 7)
    notice['page'] = 1
    classify([notice])
    assert notice['type'] == 'frag'


def test_caption_region_does_not_absorb_adjacent_table_cells():
    a = word('Table 2. Neutral caption', 50, 100, 8, caption_group=(50,100))
    b = word('continued label', 50, 110, 8, caption_group=(50,100))
    cell = word('1', 200, 110, 8)
    ls = s.make_lines([a,b,cell])
    assert len(ls) == 3
    bs = s.build_blocks([dict(l,band=0,col=0) for l in ls],1,10)
    result = s.combine_caption_groups(bs)
    caption = next(b for b in result if b.get('caption_group'))
    assert 'continued label' in caption['text'] and not caption['text'].endswith('1')


def test_unanchored_table_mention_does_not_create_a_caption_region():
    ws = line('The incomplete sentence continues with',100)['words'] + line('Table 2. The discussion continues.',112)['words']
    page = SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[])
    s.early_float_regions(page,ws,[],10)
    assert not any(w.get('caption_group') for w in ws)


def test_heading_sizes_use_the_same_resolution_as_the_body_estimate():
    b = typed_block('3 Neutral section',100,11.2,heading_boundary=False)
    assert s.is_heading_block(b,10)


def test_multiline_affiliations_follow_an_identified_byline():
    title = typed_block('A neutral investigation of choices',100,18,font='Title')
    author = typed_block('Alex Neutral and Sam Example',150,11,font='Names')
    affiliation = typed_block('1 Institute of Neutral Studies 2 Example Research College',168,8,font='Affiliation')
    affiliation['n_lines'] = 4
    for b in (title,author,affiliation): b['page'] = 1
    bs = [title,author,affiliation]
    classify(bs)
    assert author['byline'] and affiliation['byline']


def test_regional_column_projection_ignores_full_width_front_matter():
    full = [line('A full width metadata line covering the entire page area', 80+i*12, x=50) for i in range(10)]
    for l in full: l['x1'] = 550
    columns = [line('Neutral body text with ordinary width', 300+i*12, x=x) for i in range(10) for x in [50, 330]]
    for l in columns: l['x1'] = l['x0']+220
    assert s.regional_gutters(full+columns, 600, 10)


def test_numeric_cells_do_not_supply_regional_body_columns():
    cells = [line('12 34 56',100+12*i,x=x) for i in range(12) for x in [50,330]]
    assert not s.regional_gutters(cells,600,10)


def test_repeated_column_template_guides_a_sparse_region_only_when_it_fits():
    pages = []
    for pno in range(1,4):
        ws = [w for i in range(10) for x in [50,330]
              for w in line('Neutral body text with ordinary column width',100+12*i,x=x)['words']]
        pages.append(dict(pno=pno,w=600,words=ws))
    prior = s.document_gutters(pages,10)
    assert len(prior) == 1
    sparse = [line('Neutral prose continues across ordinary lines',100+12*i,x=x) for i in range(3) for x in [50,330]]
    assert s.regional_gutters(sparse,600,10,[g*600 for g in prior])
    full = line('A full width body paragraph must veto the template',100)
    full['x1'] = 550
    assert not s.regional_gutters([full],600,10,[g*600 for g in prior])


def test_repeated_large_pull_quote_does_not_depend_on_next_word():
    prose = line('Another neutral source requires a separate explanation here.', 100)
    quote = line('Another neutral source requires a separate explanation here.', 200, size=14)
    box = [quote['x0']-2, 198, quote['x1']+2, 218]
    pull, boxes = s.repeated_pull_quotes([prose, quote], [box], [], 10)
    assert pull == [quote] and boxes == [box] and quote['pull']


def test_gutter_crossing_body_lines_trigger_selfcheck():
    b = typed_block('Ordinary body prose ends with a complete sentence.', 100, type='para', gutter_crossings=3)
    _, reasons = s.layout_signals([b], 1)
    assert any('cross a column gutter' in r for r in reasons)


def test_hyphens_use_encoded_compounds_and_uppercase_line_end_evidence():
    assert s.join_words('Neutral-', 'Choices') == 'Neutral-Choices'
    t = s.join_marked('Neutral-', 'Choices')
    resolved, _ = s.resolve_hyphens([t, 'A neutral-choices label occurs here.'])
    assert resolved[0] == 'Neutral-Choices'


def test_hyphen_word_evidence_includes_an_independent_plural():
    text = s.join_marked('A small-', 'group comparison.')
    resolved, _ = s.resolve_hyphens([text, 'The small independent groups agree.'])
    assert resolved[0] == 'A small-group comparison.'


def test_capital_after_line_end_hyphen_needs_compound_evidence():
    text = s.join_marked('A neutral part-', 'Separate Label')
    resolved, _ = s.resolve_hyphens([text])
    assert resolved[0] == 'A neutral part- Separate Label'


@pytest.mark.parametrize('labels,definition', [(('AX', 'BY', 'CZ'), 'Neutral first definition'),
                                               (('A2', 'ByZ', 'CD'), 'Explanation')])
def test_word_cells_with_repeated_tab_stops_do_not_glue_into_prose(labels, definition):
    ls = []
    for y, label in zip((100, 130, 160), labels):
        ws = [word(label, 50, y)] + line(definition, y, x=125)['words']
        ls.append(dict(s.line_from_words(ws), band=0, col=0))
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert all(b['type'] == 'frag' and b['table'] for b in bs)


def test_aligned_variable_definitions_continuing_a_sentence_stay_visible():
    ls = []
    for y, label, description in [(100, 'AX', 'a neutral first measure,'),
                                   (130, 'BY', 'another neutral measure, and'),
                                   (160, 'CZ', 'the final neutral measure.')]:
        ws = [word(label, 50, y)] + line(description, y, x=125)['words']
        ls.append(dict(s.line_from_words(ws), band=0, col=0))
    bs = s.build_blocks(ls, 1, 10)
    classify(bs)
    assert all(b['type'] == 'para' for b in bs)


def test_numbered_reference_count_counts_entries_inside_one_block():
    bs = [dict(text='References', type='heading', page=1),
          dict(text='1. Green A. 2001. Neutral work. 2. Blue B. 2002. Another work.',type='para',page=1,
               line_texts=['1. Green A. 2001. Neutral work.', '2. Blue B. 2002. Another work.'])]
    assert s.mark_sections(bs) == 2
    assert all(b['type'] == 'ref' for b in bs)
