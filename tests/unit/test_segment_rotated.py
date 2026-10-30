import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from PIL import Image
import pytest
import segment
from conftest import _pdf_bytes


@pytest.mark.parametrize('rotation,upright,expected', [(0,True,False),(0,False,True),(90,True,True),(270,True,True),(180,True,False)])
def test_rotated_detection(rotation, upright, expected):
    char = dict(text='X',upright=upright,x0=10,x1=30,top=40,bottom=90)
    page = SimpleNamespace(chars=[char],bbox=(0,0,100,200),width=100,height=200,rotation=rotation)
    regions = segment.rotated_text_regions(SimpleNamespace(pages=[page]), [1])
    assert bool(regions) == expected
    if expected:
        assert regions[0]['bbox'] == [.1,.2,.3,.45]
        assert regions[0]['table'] and regions[0]['rotated']


def test_rotated_pdf_emits_agent_line_and_crop(tmp_path):
    # Rotated content dominates; ordinary body text still supplies guide paras.
    injection = ') Tj ET q 0 1 -1 0 550 80 cm BT /F1 6 Tf 0 0 Td (' + 'Rotated table values 123 '*12 + ') Tj ET Q BT /F1 12 Tf 60 400 Td ('
    source = tmp_path/'rotated.pdf'
    source.write_bytes(_pdf_bytes([[(60,700,'The paragraph explains the table with enough words to make a complete argument.'),
                                  (60,680,'A second sentence makes this a readable paragraph for the segmentation test.'),
                                  (60,400,injection)]]))
    out = tmp_path/'work'
    result = subprocess.run([sys.executable,str(Path(segment.__file__)),str(source),'--engine','pdfplumber','--out',str(out)],capture_output=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr+result.stdout
    assert '\u7ed9\u6267\u884c\u7684 agent' in result.stdout and '\u65cb\u8f6c\u6587\u5b57' in result.stdout
    doc = json.loads((out/'paragraphs.json').read_text(encoding='utf-8'))
    rotated = [it for it in doc['items'] if it.get('rotated')]
    assert len(rotated) == 1 and rotated[0]['type'] == 'frag'
    crop = out/doc['crops'][rotated[0]['id']]
    with Image.open(crop) as image: assert image.width > 0 and image.height > 0


def test_incidental_vertical_label_is_not_a_rotated_page():
    chars = [dict(text='X',upright=True,x0=10,x1=30,top=40,bottom=90) for _ in range(3)]
    chars.append(dict(chars[0],upright=False))
    page = SimpleNamespace(chars=chars,bbox=(0,0,100,200),width=100,height=200,rotation=0)
    assert segment.rotated_text_regions(SimpleNamespace(pages=[page]), [1]) == []


def test_rotate_metadata_covers_table_not_only_rotated_page_number():
    table = dict(text='TABLE DATA',upright=True,x0=10,x1=80,top=40,bottom=150)
    footer = dict(text='1',upright=False,x0=90,x1=95,top=180,bottom=190)
    page = SimpleNamespace(chars=[table,dict(table),footer],bbox=(0,0,100,200),width=100,height=200,rotation=90)
    region = segment.rotated_text_regions(SimpleNamespace(pages=[page]),[1])[0]
    assert region['bbox'] == [.1,.2,.95,.95]
    assert 'TABLE DATA' in region['text']


def test_rotated_character_order_does_not_change_prose_repairs(tmp_path):
    ordinary = dict(id='P1',type='para',page=1,text='com'+segment.HY+'pound')
    from copy import deepcopy
    baseline = dict(items=[deepcopy(ordinary)])
    with_table = dict(items=[deepcopy(ordinary),dict(id='F1',type='frag',page=1,text='com-pound',rotated=True,table=True)])
    segment.write_outputs(baseline,tmp_path/'before',12000)
    segment.write_outputs(with_table,tmp_path/'after',12000)
    assert with_table['items'][0]['text'] == baseline['items'][0]['text']
    assert with_table['items'][1]['text'] == 'com-pound'
