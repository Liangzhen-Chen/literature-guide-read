"""Embedded image geometry, ordering and crop replay, using generated PDFs."""
import json
from pathlib import Path
import zlib

import pdfplumber
import pytest

import fix
import segment as s
from crops import crop_regions


def image_pdf(path, images, caption='below', inside_label=None):
    # A single Flate-compressed RGB XObject, placed once per supplied rectangle.
    pixels = zlib.compress(bytes([30, 80, 160] * 64))
    objs = [b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Kids [6 0 R] /Count 1 >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            b'<< /Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceRGB '
            b'/BitsPerComponent 8 /Filter /FlateDecode /Length '+str(len(pixels)).encode()+b' >>\nstream\n'+pixels+b'\nendstream']
    lines = [(60, 720, 'A synthetic example explains how a chart supports the argument.'),
             (60, 680, 'The first paragraph describes the method and its ordinary assumptions.'),
             (60, 340, 'This paragraph below the image explains the result and its limits.')]
    if caption:
        lines.append((60, 380 if caption == 'below' else 580, 'Figure 1. A synthetic chart.'))
    if inside_label:
        lines.append((80, 500, inside_label))
    content = ''.join(f'q {w} 0 0 {h} {x} {y} cm /Im Do Q\n' for x, y, w, h in images).encode()
    content += ''.join(f'BT /F1 12 Tf {x} {y} Td ({t}) Tj ET\n' for x, y, t in lines).encode()
    objs += [b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
             b'/Resources << /Font << /F1 3 0 R >> /XObject << /Im 4 0 R >> >> /Contents 5 0 R >>']
    out, offsets = b'%PDF-1.4\n', []
    for n, obj in enumerate(objs, 1):
        offsets.append(len(out)); out += f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start = len(out)
    out += b'xref\n0 7\n0000000000 65535 f \n'+b''.join(f'{p:010d} 00000 n \n'.encode() for p in offsets)
    path.write_bytes(out+f'trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return path


def items(caption):
    out = [dict(id='P1', type='para', text='Before.', page=1, bbox=[.1, .1, .5, .2])]
    if caption:
        top = 400/792 if caption == 'below' else 200/792
        out.append(dict(id='C1', type='caption', text='Figure 1. A chart.', page=1,
                        bbox=[.1, top, .6, top+.018]))
    out.append(dict(id='P2', type='para', text='After.', page=1, bbox=[.1, .56, .5, .6]))
    return out


@pytest.mark.parametrize('caption,order', [('below', ['P1', 'F1', 'C1', 'P2']),
                                         ('above', ['P1', 'C1', 'F1', 'P2']),
                                         (None, ['P1', 'P2'])])
def test_embedded_image_caption_and_column_order(tmp_path, caption, order):
    path = image_pdf(tmp_path/'image.pdf', [(60, 400, 220, 160)], caption)
    original = items(caption)
    with pdfplumber.open(path) as pdf:
        regions = s.embedded_image_regions(pdf, [1], original)
    if caption is None:
        assert regions == []
        return
    assert len(regions) == 1 and regions[0]['text'] == ''
    assert regions[0]['figure'] and regions[0]['region_crop']
    s.insert_image_regions(original, regions)
    assert [it['id'] for it in original] == order
    made = crop_regions(path, regions, tmp_path/'crops')
    assert Path(made['F1']).is_file()


def test_touching_tiles_merge_before_area_filter(tmp_path):
    path = image_pdf(tmp_path/'tiles.pdf', [(60, 400, 80, 150), (140, 400, 80, 150)])
    with pdfplumber.open(path) as pdf:
        regions = s.embedded_image_regions(pdf, [1], items('below'))
    assert len(regions) == 1
    assert regions[0]['bbox'] == pytest.approx([60/612, 242/792, 220/612, 392/792], abs=.00005)


def test_full_page_image_ignored(tmp_path):
    path = image_pdf(tmp_path/'background.pdf', [(0, 0, 612, 792)])
    with pdfplumber.open(path) as pdf:
        assert s.embedded_image_regions(pdf, [1], []) == []


@pytest.mark.parametrize('rotated', [False, True])
def test_existing_table_or_rotated_crop_prevents_duplicate(tmp_path, rotated):
    path = image_pdf(tmp_path/'table.pdf', [(60, 400, 220, 160)])
    covered = [dict(id='F1', type='frag', table=True, page=1, bbox=[.08, .25, .5, .55], text='Table')]
    if rotated:
        covered[0]['rotated'] = True
    with pdfplumber.open(path) as pdf:
        assert s.embedded_image_regions(pdf, [1], covered+items('below')) == []


def test_segment_image_crop_survives_apply_renumbering(tmp_path, monkeypatch):
    path = image_pdf(tmp_path/'paper.pdf', [(60, 400, 220, 160)])
    work = tmp_path/'work'
    monkeypatch.setattr('sys.argv', ['segment.py', str(path), '--out', str(work), '--engine', 'pdfplumber'])
    s.main()
    doc = json.loads((work/'paragraphs.json').read_text(encoding='utf-8'))
    image = next(it for it in doc['items'] if it.get('embedded_image'))
    raw = (work/doc['crops'][image['id']]).read_bytes()
    before = next(it['id'] for it in doc['items'] if it['type'] == 'para')
    ops = [dict(op='type', ids=[before], to='frag', why='hide a synthetic aside')]
    fixes = work/'fixes.json'; fixes.write_text(json.dumps(ops), encoding='utf-8')
    fixed = fix.apply(fixes, work/'paragraphs.json')
    new = next(it for it in fixed['items'] if it.get('embedded_image'))
    assert new['id'] != image['id']
    assert (work/fixed['crops'][new['id']]).read_bytes() == raw
    first = (work/'paragraphs.json').read_bytes()
    fix.apply(fixes, work/'paragraphs.json')
    assert (work/'paragraphs.json').read_bytes() == first


def test_image_words_do_not_change_prose_repairs(tmp_path):
    original = [dict(id='P1', type='para', page=1, text='A com\u00adpound.')]
    import copy
    baseline = dict(items=copy.deepcopy(original))
    s.write_outputs(baseline, tmp_path/'before', 12000)
    doc = dict(items=copy.deepcopy(original)+[dict(id='F1', type='frag', page=1,
               text='com-pound', embedded_image=True, figure=True, region_crop=True)])
    s.write_outputs(doc, tmp_path/'after', 12000)
    assert doc['items'][0] == baseline['items'][0]


def test_leading_image_is_visible_under_first_paragraph(clean):
    import render
    from check import run_checks
    doc, guide = clean
    doc['items'].insert(0, dict(id='F1', type='frag', text='Figure 1. A labelled opening chart.', page=1,
                              figure=True, region_crop=True, embedded_image=True))
    _, _, comp = run_checks(doc, guide)
    data = render.build_data(doc, guide, comp, None, {}, None, crops={'F1': 'data:image/png;base64,synthetic'})
    assert data['frag_crops']['P1'] == ['F1']


def test_unlabelled_page_one_logo_makes_no_item(tmp_path):
    path = image_pdf(tmp_path/'logo.pdf', [(60, 400, 180, 100)], caption=None)
    with pdfplumber.open(path) as pdf:
        assert s.embedded_image_regions(pdf, [1], items(None)) == []


@pytest.mark.parametrize('kind', ['caption', 'para', 'frag'])
@pytest.mark.parametrize('side', ['above', 'below'])
@pytest.mark.parametrize('gap,expected', [(.08, 1), (.15, 0)])
def test_exhibit_label_distance_and_item_type(tmp_path, kind, side, gap, expected):
    path = image_pdf(tmp_path/'label.pdf', [(60, 400, 220, 160)], caption=None)
    top = 392/792+gap if side == 'below' else 232/792-gap-.018
    label = dict(id='L1', type=kind, page=1, text='Chart 1. A synthetic chart.',
                 bbox=[.1, top, .6, top+.018])
    with pdfplumber.open(path) as pdf:
        assert len(s.embedded_image_regions(pdf, [1], [label])) == expected


def test_label_at_start_of_image_words_counts(tmp_path):
    path = image_pdf(tmp_path/'inside.pdf', [(60, 400, 220, 160)], caption=None,
                     inside_label='Figure 9. A chart')
    with pdfplumber.open(path) as pdf:
        regions = s.embedded_image_regions(pdf, [1], [])
    assert len(regions) == 1 and regions[0]['text'].startswith('Figure 9.')


@pytest.mark.parametrize('label', ['Figure 1', 'Fig. 2', 'Chart 3', 'Graph 4', 'Exhibit 5',
                                   'Map 6', 'Plate 7', 'Panel 8', 'Table 9', '图 1', '表 2'])
def test_supported_exhibit_labels(label):
    assert s.IMAGE_EXHIBIT_RE.match(label)
    assert not s.IMAGE_EXHIBIT_RE.match('Discussion of '+label)
