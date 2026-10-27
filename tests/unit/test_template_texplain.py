import json, re, shutil, subprocess
import pytest
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / 'assets' / 'template.html'
node = shutil.which('node')


def run_tex_plain(tex_list):
    src = TEMPLATE.read_text(encoding='utf-8')
    a, b = src.index('var GREEK ='), src.index('function mathInto')
    js = ("function mk(t){return {t:t,kids:[],appendChild(k){this.kids.push(k)},set textContent(v){this.kids.push({text:v})}}}\n"
          "var document={createDocumentFragment:()=>mk('frag'),createTextNode:s=>({text:s})};\n"
          "function el(t){return mk(t)}\n" + src[a:b] +
          "\nvar ser=n=>n.text!==undefined?n.text:'<'+n.t+'>'+n.kids.map(ser).join('')+'</'+n.t+'>';\n"
          "console.log(JSON.stringify(" + json.dumps(tex_list) + ".map(t=>{var f=texPlain(t);return f?ser(f):null})));")
    out = subprocess.run([node, '-e', js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(node is None, reason='node not available')
def test_texplain_text_wrappers_defer_scripts_to_katex():
    res = run_tex_plain([r'\mathrm{x^2}', r'\mathrm{a_i}', r'\mathrm{a$b}', r'\mathrm{log}'])
    assert res[:3] == [None, None, None]
    assert res[3] is not None
