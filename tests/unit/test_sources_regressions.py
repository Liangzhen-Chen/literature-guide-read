"""Section 8: fallback and minimum-version archive safety regressions."""
import io
import tarfile
import urllib.error

import pytest
import sources as s


def archive(name='main.tex', kind=None, linkname=''):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tf:
        info = tarfile.TarInfo(name)
        if kind:
            info.type, info.linkname = kind, linkname
            tf.addfile(info)
        else:
            body = b'\\documentclass{article}\\begin{document}Hello\\end{document}'
            info.size = len(body)
            tf.addfile(info, io.BytesIO(body))
    return stream.getvalue()


def test_conversion_error_falls_back_to_tex(tmp_path, monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        body = archive() if '/src/' in url else b'<html><title>Conversion failed</title><body>Sorry, HTML conversion failed.' + b' ' * 6000 + b'</body></html>'
        return body, url, 'text/html'
    monkeypatch.setattr(s, 'get', get)
    s.fetch('2401.04088', tmp_path)
    assert (tmp_path / 'tex/main.tex').exists()
    assert not (tmp_path / 'open.html').exists()
    assert len(calls) == 3


def test_fetch_supports_python39_extractall_signature(tmp_path, monkeypatch):
    original = tarfile.TarFile.extractall
    def old_extractall(self, path='.', members=None, *, numeric_owner=False):
        return original(self, path, members, numeric_owner=numeric_owner)
    monkeypatch.setattr(tarfile.TarFile, 'extractall', old_extractall)
    monkeypatch.setattr(s, 'get', lambda url, **kw: (archive(), url, 'application/gzip'))
    s.fetch('2401.04088', tmp_path, tex=True)
    assert (tmp_path / 'tex/main.tex').exists()


@pytest.mark.parametrize('name,kind,link', [('../escape.tex', None, ''), ('/tmp/reading-guide-escape.tex', None, ''), ('link', tarfile.SYMTYPE, '../../escape'), ('link', tarfile.LNKTYPE, '../../escape'), ('device', tarfile.CHRTYPE, '')])
def test_unsafe_tar_is_rejected(tmp_path, monkeypatch, name, kind, link):
    monkeypatch.setattr(s, 'get', lambda url, **kw: (archive(name, kind, link), url, 'application/gzip'))
    with pytest.raises(SystemExit) as exc:
        s.fetch('2401.04088', tmp_path, tex=True)
    assert exc.value.code == 2
    assert not (tmp_path.parent / 'escape.tex').exists()


@pytest.mark.parametrize('status', [403, 404, None])
def test_unavailable_fetch_exits_two(tmp_path, monkeypatch, capsys, status):
    def get(url, **kw):
        if status:
            raise urllib.error.HTTPError(url, status, 'failure', {}, None)
        raise urllib.error.URLError('network unavailable')
    monkeypatch.setattr(s, 'get', get)
    with pytest.raises(SystemExit) as exc:
        s.fetch('2401.04088', tmp_path)
    assert exc.value.code == 2
    output = capsys.readouterr().out
    assert 'Continuing without the open version is fine.' in output
    assert str(status) in output if status else 'network unavailable' in output


def test_relative_image_url_uses_document_directory(tmp_path, monkeypatch):
    urls = []
    def get(url):
        urls.append(url)
        return b'image', url, 'image/png'
    monkeypatch.setattr(s, 'get', get)
    assert s.load_image('2401.04088v1/x.png', 'https://arxiv.org/html/2401.04088', tmp_path)
    assert urls == ['https://arxiv.org/html/2401.04088v1/x.png']


def test_outer_caption_and_svg_object(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(s, 'get', lambda url: (b'<svg/>', url, 'image/svg+xml'))
    p = tmp_path/'open.html'
    p.write_text('<figure><figure><figcaption>(a) Child</figcaption><object type="image/svg+xml" data="x.svg"></object></figure><figcaption>Figure 3. Parent</figcaption></figure>')
    s.parse_html(p, tmp_path, 'https://arxiv.org/html/2401.04088', None)
    f = json.loads((tmp_path/'sources.json').read_text())['figures'][0]
    assert f['num'] == 3
    assert f['img'].startswith('data:image/svg+xml;base64,')


def test_tex_bracket_display_equations(tmp_path):
    import json
    (tmp_path/'main.tex').write_text(r'\documentclass{article}\[x=1\]\begin{equation}y=2\end{equation}\[z=3\]')
    s.parse_tex(tmp_path, tmp_path, None)
    assert json.loads((tmp_path/'sources.json').read_text())['equations'] == [{'tex':'x=1'}, {'tex':'y=2'}, {'tex':'z=3'}]


def test_detect_rotated_arxiv_margin(tmp_path, monkeypatch, capsys):
    import json
    import pdfplumber
    from types import SimpleNamespace
    pdfpath = tmp_path/'paper.pdf'
    pdfpath.touch()
    class PDF:
        metadata = {}
        pages = [SimpleNamespace(extract_text=lambda: 'Title\n1v88040.1042:viXra')]
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(pdfplumber, 'open', lambda p: PDF())
    paras = tmp_path/'paragraphs.json'
    paras.write_text(json.dumps({'items': [], 'source_path': str(pdfpath)}))
    s.detect(paras)
    assert json.loads(capsys.readouterr().out)['arxiv'] == ['2401.04088']


def test_tex_wrapped_table_preserves_caption_numbering(tmp_path):
    import json
    (tmp_path/'main.tex').write_text(r'\documentclass{article}\begin{wrapfigure}{r}{3cm}\begin{tabular}{cc}A & B\end{tabular}\captionof{table}{Architecture}\end{wrapfigure}\begin{table}\caption{Results}\end{table}')
    s.parse_tex(tmp_path, tmp_path, None)
    figs = json.loads((tmp_path/'sources.json').read_text())['figures']
    assert [(f['kind'], f['num'], f['caption']) for f in figs] == [('table',1,'Architecture'),('table',2,'Results')]
    assert figs[0]['rows'] == [['A','B']]


@pytest.mark.parametrize('ocr,html', [('finetuned','fine tuned'), ('Mixtureof-Experts','Mixture-of-Experts'), ('state-of-theart','state-of-the-art')])
def test_compare_joined_words_are_not_missing_prose(tmp_path, ocr, html):
    import json
    text = 'The researchers explain that this model is a ' + ocr + ' model with several layers and carefully evaluated experimental results.'
    p=tmp_path/'p.json';p.write_text(json.dumps({'items':[{'id':'P1','type':'para','text':text}]}))
    assert s.compare_text(p,[text.replace(ocr,html)]) == []


def test_html_comparison_excludes_note_and_math_alternatives(tmp_path):
    import json
    text = 'The researchers release this model under the Apache license for academic and commercial usage and set K = 2 for every token.'
    p=tmp_path/'p.json';p.write_text(json.dumps({'items':[{'id':'P1','type':'para','text':text}]}))
    html=text.replace('license','license<span class="ltx_note">1 https://example.org/the-footnote</span>').replace('K = 2','<math><semantics><mrow><mi>K</mi><mo>=</mo><mn>2</mn></mrow><annotation encoding="application/x-tex">K = 2</annotation></semantics></math>')
    h=tmp_path/'open.html';h.write_text('<p>'+html+'</p>')
    s.parse_html(h,tmp_path,None,p)
    assert json.loads((tmp_path/'sources.json').read_text())['text_check'] == []


def test_normalized_html_still_reports_real_removed_phrase(tmp_path):
    import json
    text = 'The researchers carefully evaluated this model with several experimental methods before publishing their results in the scientific journal.'
    p=tmp_path/'p.json';p.write_text(json.dumps({'items':[{'id':'P1','type':'para','text':text}]}))
    h=tmp_path/'open.html';h.write_text('<p>'+text.replace('experimental methods','experimental independent validation methods')+'<span class="ltx_note">an unrelated footnote</span></p>')
    s.parse_html(h,tmp_path,None,p)
    assert json.loads((tmp_path/'sources.json').read_text())['text_check'][0]['missing'] == ['independent validation']
