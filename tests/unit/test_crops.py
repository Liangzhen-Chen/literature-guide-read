import crops


def test_crop_regions_writes_png_for_equation_and_table(tmp_path, sample_pdf):
    items = [{'id': 'F1', 'type': 'frag', 'text': 'z = (x - m) / s', 'page': 3, 'equation': True, 'bbox': [0.1, 0.2, 0.6, 0.26]},
             {'id': 'F2', 'type': 'frag', 'text': '10 20', 'page': 3, 'table': True, 'bbox': [0.1, 0.4, 0.9, 0.5]},
             {'id': 'P1', 'type': 'para', 'text': 'prose', 'page': 3, 'bbox': [0.1, 0.6, 0.9, 0.7]}]
    out = crops.crop_regions(sample_pdf, items, tmp_path)
    assert set(out) == {'F1', 'F2'}
    assert (tmp_path / 'F1.png').stat().st_size > 500 and (tmp_path / 'F2.png').exists()


def test_crop_regions_skips_items_without_bbox(tmp_path, sample_pdf):
    assert crops.crop_regions(sample_pdf, [{'id': 'F1', 'type': 'frag', 'text': 'x = 1', 'page': 1, 'equation': True}], tmp_path) == {}


def test_table_runs_merge_into_one_crop(tmp_path, sample_pdf):
    items = [{'id': 'F1', 'type': 'frag', 'text': 'a b', 'page': 3, 'table': True, 'bbox': [0.1, 0.40, 0.9, 0.42]},
             {'id': 'F2', 'type': 'frag', 'text': 'c d', 'page': 3, 'table': True, 'bbox': [0.1, 0.42, 0.9, 0.44]},
             {'id': 'P1', 'type': 'para', 'text': 'prose', 'page': 3, 'bbox': [0.1, 0.6, 0.9, 0.7]},
             {'id': 'F3', 'type': 'frag', 'text': 'e f', 'page': 3, 'table': True, 'bbox': [0.1, 0.72, 0.9, 0.74]}]
    out = crops.crop_regions(sample_pdf, items, tmp_path)
    assert set(out) == {'F1', 'F3'}
    assert items[0]['bbox'] == [0.1, 0.40, 0.9, 0.44] and items[1]['table_part'] is True


def _offset_pdf(path):
    """A one-page PDF whose MediaBox starts at y=40 (JSTOR scans do this), with a black bar in a known place."""
    content = b"0 0 0 rg 20 100 160 20 re f"  # x 20..180, y 100..120 in PDF space
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 40 200 340] /Contents 4 0 R >>",
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def test_crop_regions_respects_mediabox_offset(tmp_path, sample_pdf):
    from PIL import Image
    pdf = tmp_path / 'offset.pdf'; _offset_pdf(pdf)
    # page is 200 x 300 pt, top at y=340: the bar's top edge is 340-120=220 from the top -> 0.733, bottom 240 -> 0.8
    items = [{'id': 'F1', 'type': 'frag', 'text': 'x = 1', 'page': 1, 'equation': True, 'bbox': [0.1, 0.7333, 0.9, 0.8]}]
    out = crops.crop_regions(pdf, items, tmp_path, pad=0)
    im = Image.open(out['F1']).convert('L')
    dark = sum(1 for v in im.tobytes() if v < 128) / (im.width * im.height)
    assert dark > 0.5, f'crop missed the bar: only {dark:.0%} dark'


def test_equation_crops_are_widened_to_the_column(tmp_path, sample_pdf):
    # a text-layer box for an equation is often narrower than the typeset equation (missing glyphs); widen it
    items = [{'id': 'F1', 'type': 'frag', 'text': 'y = a', 'page': 3, 'equation': True, 'bbox': [0.3, 0.2, 0.5, 0.26]},
             {'id': 'F2', 'type': 'frag', 'text': '1 2', 'page': 3, 'table': True, 'bbox': [0.3, 0.4, 0.5, 0.5]}]
    crops.crop_regions(sample_pdf, items, tmp_path)
    assert items[0]['bbox'][0] <= 0.1 and items[0]['bbox'][2] >= 0.9
    assert items[1]['bbox'] == [0.3, 0.4, 0.5, 0.5]


def test_consecutive_equation_fragments_merge_into_one_crop(tmp_path, sample_pdf):
    items = [{'id': 'F1', 'type': 'frag', 'text': 'QK T', 'page': 3, 'equation': True, 'bbox': [0.3, 0.20, 0.5, 0.22]},
             {'id': 'F2', 'type': 'frag', 'text': 'A = softmax(...) V (1)', 'page': 3, 'equation': True, 'bbox': [0.2, 0.22, 0.7, 0.25]},
             {'id': 'F3', 'type': 'frag', 'text': 'd k', 'page': 3, 'equation': True, 'bbox': [0.3, 0.25, 0.5, 0.27]},
             {'id': 'P1', 'type': 'para', 'text': 'prose', 'page': 3, 'bbox': [0.1, 0.3, 0.9, 0.4]},
             {'id': 'F4', 'type': 'frag', 'text': 'x = 1', 'page': 3, 'equation': True, 'bbox': [0.3, 0.5, 0.5, 0.52]}]
    out = crops.crop_regions(sample_pdf, items, tmp_path)
    assert set(out) == {'F1', 'F4'}
    assert items[0]['bbox'][1] == 0.20 and items[0]['bbox'][3] == 0.27 and items[1]['eq_part'] is True


def test_equation_crop_absorbs_adjacent_fraction_parts(tmp_path, sample_pdf):
    # the denominator "d k" has no operator, so it is not an equation fragment itself, but it belongs to the region
    items = [{'id': 'F1', 'type': 'frag', 'text': 'QK T', 'page': 3, 'bbox': [0.45, 0.20, 0.55, 0.22]},
             {'id': 'F2', 'type': 'frag', 'text': 'Attention(Q, K, V) = softmax( ) V (1)', 'page': 3, 'equation': True, 'bbox': [0.2, 0.22, 0.8, 0.25]},
             {'id': 'F3', 'type': 'frag', 'text': 'd k', 'page': 3, 'bbox': [0.45, 0.25, 0.55, 0.27]},
             {'id': 'P1', 'type': 'para', 'text': 'prose', 'page': 3, 'bbox': [0.1, 0.3, 0.9, 0.4]}]
    out = crops.crop_regions(sample_pdf, items, tmp_path)
    assert set(out) == {'F1'} or set(out) == {'F2'}
    region = items[0] if 'F1' in out else items[1]
    assert region['bbox'][1] == 0.20 and region['bbox'][3] == 0.27
