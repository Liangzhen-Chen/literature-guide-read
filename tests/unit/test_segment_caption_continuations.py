"""Caption text-block evidence, independent of any source document."""
from types import SimpleNamespace
import segment as s
from test_segment_batch2 import line, word


def test_centered_title_does_not_need_a_filled_measure():
    a=line('Figure 2. Independent observations',100,size=10)
    a['x1']=350
    b=line('A second title line',112,size=10,x=150)
    b['x1']=250
    assert s.caption_wrap(a,b,50,550)
    assert not s.caption_wrap(a,dict(b,tab=True),50,550)


def test_hanging_title_paragraph_keeps_short_aligned_lines():
    a=line('A short title continuation',100,size=8,x=120)
    a['caption_indent']=120
    b=line('An independent subtitle',110,size=8,x=120)
    assert s.caption_wrap(a,b,50,550)
    assert not s.caption_wrap(a,dict(b,cell_edges=[200]),50,550)


def test_ocr_caption_tail_is_protected_before_prose_assembly():
    a=line('Figure 2. Independent observations across several groups',100,size=9,x=50,ocr_layer=True)
    b=line('A second title line',111,size=9,x=110,ocr_layer=True)
    c=line('The body starts its own independent explanation.',180,size=10)
    out=s.prepare_typing_lines([a,b,c],10)
    assert out[0]['caption_group']==out[1]['caption_group']
    assert out[1]['caption_candidate']
    assert not out[2].get('caption_group')


def test_tracked_caption_label_keeps_its_number_after_rebuilding_lines():
    ws=[word(ch,50+7*i,80,size=8) for i,ch in enumerate('FIGURE')]
    ws += [word('1',94,80,size=8),word('Independent',104,80,size=8)]
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[],edges=[])
    s.early_float_regions(page,ws,[[50,10,200,70]],10)
    rebuilt=s.make_lines(ws,gap_split=True)
    assert len(rebuilt)==1
    assert rebuilt[0]['text'].startswith('FIGURE 1')
    assert rebuilt[0]['caption_group'] is not None


def test_distinct_same_row_captions_keep_separate_groups():
    a=line('Fig. 2. Neutral observations',100,size=8)
    b=line('Fig. 3. Independent observations',100,size=8,x=350)
    ws=a['words']+b['words']
    page=SimpleNamespace(bbox=(0,0,600,800),width=600,rects=[],edges=[])
    s.early_float_regions(page,ws,[],10)
    rebuilt=s.make_lines(ws)
    assert len(rebuilt)==2
    assert rebuilt[0]['caption_group']!=rebuilt[1]['caption_group']
    blocks=[dict(l,page=1,n_lines=1) for l in reversed(rebuilt)]
    assert [b['x0'] for b in s.combine_caption_groups(blocks)]==[50,350]


def test_styled_sentence_tail_is_not_a_runin_heading():
    a=line('The observations also contribute to an independent',100,size=12)
    a['words']=[dict(w,bold=True,font='NeutralBold') for w in a['words']]
    a.update(s.line_from_words(a['words']))
    b=line('index. These observations support a separate comparison.',114,size=12)
    b['words'][0].update(bold=True,italic=True,font='NeutralBoldItalic')
    out=s.prepare_typing_lines([a,b],12)
    assert len(out)==2
    assert not out[1].get('force_heading')
    assert out[1]['text'].startswith('index. These')
