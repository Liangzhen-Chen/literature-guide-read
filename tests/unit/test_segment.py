import pytest
import segment as s

@pytest.mark.parametrize('text', ['Done.”','Done.)','Done.2','完成。','Done.'])
def test_terminal(text): assert s.end_terminal(text)

@pytest.mark.parametrize('text', ['', 'unfinished', 'done,'])
def test_nonterminal(text): assert not s.end_terminal(text)

@pytest.mark.parametrize('a,b,out',[('hy-','phen','hyphen'),('中文','继续','中文继续'),('one','two','one two'),('','x','x'),('x','','x')])
def test_join(a,b,out): assert s.join_text(a,b)==out

@pytest.mark.parametrize('text,size,bold,expected',[
 ('Reward Choices',10.5,0,True),('Methods',10,0,True),('2 Results',10,0,True),
 ('一、研究方法',10,0,True),('（一）研究结果',10,0,True),('Type specialization.',10,1,True),
 ('i 1 t 1 Outer Tree',10,0,False),('This sentence explains a finding.',10,0,False)])
def test_heading(text,size,bold,expected):
    assert bool(s.is_heading_block({'text':text,'size':size,'bold':bold,'n_lines':1},10)) == expected

@pytest.mark.parametrize('text,expected',[('Figure 1. Caption',True),('Figure 2 A typical result',True),('Figure 3 shows the result.',False)])
def test_caption(text,expected): assert bool(s.CAPTION_RE.match(text) or s.CAPTION_TITLE_RE.match(text)) == expected

@pytest.mark.parametrize('text,expected',[('2Differences',True),('① 这里',True),('1. Smith',False),('98, 1325',False)])
def test_footmark(text,expected): assert bool(s.FOOT_MARK_RE.match(text)) == expected

def test_page_banner():
    assert s.PAGE_NUM_RE.match('— 12 —') and s.PAGE_NUM_RE.match('iv')
    assert not s.PAGE_NUM_RE.match('12 buyers')
    assert s.BANNER_RE.search('Volume 12') and not s.BANNER_RE.search('Results')

@pytest.mark.parametrize('text,note', [('Finding.1','1 Explanation'),("Finding.'",'1 Explanation'),('结果。①','① 说明')])
@pytest.mark.parametrize('note_page',[1,2])
def test_link_notes(text,note,note_page):
    items=[{'id':'P1','type':'para','text':text,'page':1},{'id':'N1','type':'note','text':note,'page':note_page}]
    s.link_notes(items)
    assert items[1].get('ref') == ('P1' if note_page==1 else None)

def test_merge_page_capital():
    out,n=s.merge_continuations([{'type':'para','text':'The finding concerns','page':1},{'type':'para','text':'London markets.','page':2}])
    assert n==1 and out[0]['text']=='The finding concerns London markets.'
    assert out[0]['pages']=={1,2}

def test_result_closes_question():
    out,n=s.merge_continuations([{'type':'para','text':'Choose a reward','page':1},{'type':'frag','text':'N = 130','page':1},{'type':'para','text':'another question','page':1}])
    assert n==1 and len(out)==2 and out[0]['closed']

def test_sections():
    items=[{'type':'heading','text':'References'}, {'type':'para','text':'Smith (2020)'},
           {'type':'note','text':'2Differences remain.'}, {'type':'heading','text':'Appendix'},
           {'type':'para','text':'Additional result.'}, {'type':'heading','text':'Notes'}, {'type':'para','text':'1. Endnote'}]
    assert s.mark_sections(items)==1
    assert [x['type'] for x in items]==['ref','ref','note','heading','para','heading','note']

def test_heading_size_cluster():
    blocks=[{'text':t,'size':sz,'bold':1,'n_lines':1,'page':1,'top':y,'bottom':y+15,'x0':50,'x1':300}
            for t,sz,y in [('Methods',12,450),('Results',12.7,550)]]
    s.classify(blocks,10,{1:{'h':800}},1)
    assert all(b['type']=='heading' for b in blocks)
    assert blocks[0]['level']==blocks[1]['level']
