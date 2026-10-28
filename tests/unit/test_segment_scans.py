"""Basic-tier scan handling uses synthetic pages and mocked engine boundaries."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import segment as s


def page(text='',scan=False):
    return SimpleNamespace(words=[dict(text=text)] if text else [],bbox=(0,0,600,800),width=600,height=800,
                           images=[dict(x0=0,x1=600,top=0,bottom=800)] if scan else [])


def test_mixed_pdf_keeps_text_and_blank_pages_and_reports_scans_once(monkeypatch):
    pdf=SimpleNamespace(pages=[page('A neutral readable paragraph explains an ordinary example.'),page(scan=True),page(),page(scan=True)])
    calls=[]
    monkeypatch.setattr(s,'get_words',lambda p:calls.append(p) or p.words)
    keep,messages=s.basic_text_pages(pdf,[1,2,3,4])
    assert keep==[1,3] and len(calls)==4
    assert messages==['给执行的 agent（不是给用户的）：已跳过扫描页 [2, 4]；这些页是扫描件，MinerU 可以读取。']


def test_scan_only_pdf_stops_with_agent_mineru_offer(monkeypatch):
    pdf=SimpleNamespace(pages=[page(scan=True),page()])
    monkeypatch.setattr(s,'get_words',lambda p:p.words)
    with pytest.raises(SystemExit) as exc:s.basic_text_pages(pdf,[1,2])
    assert str(exc.value)=='给执行的 agent（不是给用户的）：基础版无法读取扫描 PDF。已安装 MinerU 时请用 --engine mineru 重试；否则按 SKILL.md 第 0 步向用户提供 MinerU 选项，用户同意后由 agent 安装。'


def test_basic_cli_segments_only_kept_pages(tmp_path,monkeypatch,capsys):
    import pdfplumber
    import crops
    source=tmp_path/'neutral.pdf';source.write_bytes(b'synthetic source')
    out=tmp_path/'out'
    pdf=SimpleNamespace(pages=[page('A neutral readable paragraph explains an ordinary example.'),page(scan=True),page()])
    monkeypatch.setattr(pdfplumber,'open',lambda _:nullcontext(pdf))
    monkeypatch.setattr(s,'get_words',lambda p:p.words)
    monkeypatch.setattr(crops,'crop_regions',lambda *args:{})
    def choose(pdf,pnos,columns):
        assert pnos==[1,3]
        b=dict(text='A neutral readable paragraph explains an ordinary example.',type='para',page=1)
        return dict(blocks=[b],body=10,info={},stats=dict(two_col=0,removed=0,labels=[]),n_refs=0,merges=0),[]
    monkeypatch.setattr(s,'choose_columns',choose)
    monkeypatch.setattr(sys,'argv',['segment.py',str(source),'--out',str(out),'--engine','pdfplumber','--pages','1-3'])
    s.main()
    doc=json.loads((out/'paragraphs.json').read_text(encoding='utf-8'))
    assert [x['text'] for x in doc['items']]==['A neutral readable paragraph explains an ordinary example.']
    assert capsys.readouterr().out.count('已跳过扫描页 [2]')==1


@pytest.mark.parametrize('option,value',[('--ocr','on'),('--lang','eng'),('--dpi','300')])
def test_removed_basic_ocr_options_are_rejected(option,value,monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['segment.py','neutral.pdf','--out','unused',option,value])
    with pytest.raises(SystemExit) as exc:s.main()
    assert exc.value.code==2
    assert 'unrecognized arguments' in capsys.readouterr().err


def test_auto_engine_still_uses_installed_mineru(tmp_path,monkeypatch):
    import crops
    import mineru_backend as mb
    source=tmp_path/'neutral.pdf';source.write_bytes(b'synthetic source')
    out=tmp_path/'out'
    fixture=Path(__file__).resolve().parents[1]/'fixtures'/'mineru_structured_small.json'
    monkeypatch.setattr(mb,'available',lambda:sys.executable)
    monkeypatch.setattr(mb,'run',lambda *args:fixture)
    monkeypatch.setattr(crops,'crop_regions',lambda *args:{})
    monkeypatch.setattr(s,'basic_text_pages',lambda *args:pytest.fail('basic tier must not run'))
    monkeypatch.setattr(sys,'argv',['segment.py',str(source),'--out',str(out),'--engine','auto'])
    s.main()
    assert any(x['type']=='para' for x in json.loads((out/'paragraphs.json').read_text(encoding='utf-8'))['items'])
