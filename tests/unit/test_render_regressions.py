"""Section 6: Python/JavaScript boundary and safe payload regressions."""
import json
from types import SimpleNamespace
import render as r
from check import run_checks

def test_highlight_offsets_use_javascript_utf16(clean):
    doc, guide = clean
    doc['items'][0]['text'] = '😀 Three buyers choose.'
    _, _, comp = run_checks(doc, guide)
    d = r.build_data(doc, guide, comp, None, {}, None)
    assert d['guide']['P1']['els'][0]['hl'] == [3, 15]

def test_security_payload_remains_literal(clean, tmp_path):
    doc, guide = clean
    attack = '<script>alert(1)</script> </script> &amp; &lt;b&gt;'
    doc['items'][0]['text'] += attack
    guide['paras']['P2']['note'] = '<img src=x onerror=alert(1)>'
    out = tmp_path/'security.html'
    args = SimpleNamespace(density=None,force=True,sources=None,no_page_images=True,pdf=None,lang=None)
    r.render(doc, guide, out, args)
    d = json.loads(r.DATA_RE.search(out.read_text()).group(1))
    assert d['items']['P1']['text'].endswith(attack)
    assert out.read_text().count('</script>') == 2
    assert 'innerHTML' not in (r.SKILL_DIR/'assets/template.html').read_text()
