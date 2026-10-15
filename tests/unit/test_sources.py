import json
import pytest
import sources as s

@pytest.mark.parametrize('text,expected', [('arXiv:2401.04088v1','2401.04088'),('https://arxiv.org/abs/hep-th/9901001','hep-th/9901001')])
def test_detect(tmp_path,capsys,text,expected):
    p=tmp_path/'p.json'; p.write_text(json.dumps({'items':[{'text':text+' doi:10.1234/example.,;)'}]}))
    s.detect(p)
    result=json.loads(capsys.readouterr().out)
    assert result=={'arxiv':[expected],'doi':['10.1234/example']}

def test_html(tmp_path,monkeypatch):
    (tmp_path/'local.png').write_bytes(b'png fixture')
    def unavailable(*args,**kwargs): raise OSError('offline')
    monkeypatch.setattr(s,'get',unavailable)
    p=tmp_path/'open.html'
    p.write_text('''<html><figure><figcaption>Figure 1. Parent</figcaption><img src="data:image/png;base64,YQ=="><figure><figcaption>Figure 2. Child</figcaption></figure></figure>
    <figure><figcaption>Table 1. Values</figcaption><table><tr><th>A</th><td>3</td></tr></table></figure>
    <figure><figcaption>Figure 3. Local</figcaption><img src="local.png"></figure>
    <figure><figcaption>Figure 4. Missing</figcaption><img src="https://example.invalid/missing.png"></figure>
    <math display="block" alttext="x=3"></math><math alttext="inline"></math></html>''')
    s.parse_html(p,tmp_path,None,None)
    d=json.loads((tmp_path/'sources.json').read_text())
    assert len(d['figures'])==4
    assert d['figures'][0]['img']=='data:image/png;base64,YQ=='
    assert d['figures'][1]['rows']==[['A','3']]
    assert d['figures'][2]['img'].startswith('data:image/png;base64,')
    assert d['figures'][3]['img'] is None
    assert d['equations']==[{'tex':'x=3'}]

def test_tex(tmp_path):
    (tmp_path/'main.tex').write_text(r'\documentclass{article}\input{part}')
    (tmp_path/'part.tex').write_text(r'\begin{figure}\caption{A result}\end{figure}\begin{table}\caption{Values}\begin{tabular}{cc}A & B \\ 1 & 2\end{tabular}\end{table}\begin{equation}x=3\end{equation}')
    s.parse_tex(tmp_path,tmp_path,None)
    d=json.loads((tmp_path/'sources.json').read_text())
    assert [(f['kind'],f['num']) for f in d['figures']]==[('fig',1),('table',1)]
    assert d['figures'][1]['rows']==[['A','B'],['1','2']]
    assert d['equations']==[{'tex':'x=3'}]

def test_compare(tmp_path):
    text='The participants in this study chose the smaller reward after the researchers changed the available choices.'
    p=tmp_path/'p.json'; p.write_text(json.dumps({'items':[{'id':'P1','type':'para','text':text}]}))
    assert s.compare_text(p,[text])==[]
    assert s.compare_text(p,['Unrelated discussion about historical traditions and their changing interpretation across societies and eras.'])==[]
    result=s.compare_text(p,[text.replace('smaller reward','smaller immediate monetary reward')])
    assert result[0]['missing']==['immediate monetary']
