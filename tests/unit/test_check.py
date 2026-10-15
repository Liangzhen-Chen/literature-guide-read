import copy
import pytest
from check import run_checks, report

def test_clean(clean):
    errors,warnings,_=run_checks(*clean)
    assert errors==[] and warnings==[]

@pytest.mark.parametrize('path,value,message',[
 (('meta','title'),'','meta.title is missing'),
 (('meta','notes_lang'),['de'],'meta.notes_lang'),
 (('thesis',),None,'thesis is missing'),
 (('overview',),None,'overview is missing'),
 (('parts',),[],'parts is missing'),
 (('parts',0,'range'),'bad','bad range'),
 (('parts',0,'range'),'P2-P4','should start at P1'),
 (('parts',0,'range'),'P1-P3','must end at P4'),
 (('parts',0,'claim_p'),'P5','claim_p must name'),
 (('parts',0,'rel',0,'type'),'invalid','type must be one of'),
 (('parts',0,'rel',0,'to'),'missing',"'to' must be T"),
 (('parts',0,'rel',0,'to'),'A','cannot point to itself'),
 (('parts',0,'rel',0,'to'),'A','do not lead to the conclusion T'),
 (('parts',0,'flow',0,'p'),'P5',"'p' must be a paragraph"),
 (('parts',0,'flow',1,'rel'),'invalid',"'rel' must be one of"),
 (('parts',0,'flow',0,'x'),'99 buyers','numbers not in the source'),
 (('parts',0,'rel',0,'label'),'99 buyers','numbers not in the source'),
 (('paras','P1','tier'),'bad','tier must be'),
 (('paras','P1','role'),None,'role is missing'),
 (('paras','P1','read'),None,'read is missing'),
 (('paras','P2','note'),None,'note is missing'),
 (('paras','P1','els',0,'t'),'bad','unknown type'),
 (('paras','P1','els',0,'a'),'','needs an anchor'),
 (('paras','P1','els',0,'a'),'Never appeared','anchor not found'),
 (('paras','P1','els',0,'s'),{},'s is missing'),
])
def test_errors(clean,path,value,message):
    doc,g=clean
    target=g
    for k in path[:-1]: target=target[k]
    target[path[-1]]=value
    errors,_,_=run_checks(doc,g)
    assert any(message in e for e in errors), errors

@pytest.mark.parametrize('path,value,message',[
 (('meta','density'),'invalid','meta.density should be'),
 (('meta','density'),'low','above the low cap'),
 (('thesis',),'x'*281,'thesis is 281 characters'),
 (('parts',0,'claim'),'x'*221,'claim is 221 characters'),
 (('parts',0,'flow'),[],'no \'flow\''),
 (('parts',0,'flow'),[{'p':'P1','x':'Buyers choose.'}],'flow has 1 steps'),
 (('paras','P1','role'),'x'*61,'role is 61 characters'),
 (('paras','P1','read'),'x'*241,'read is 241 characters'),
 (('paras','P2','note'),'This paragraph explains choices.','instead of restating'),
 (('paras','P2','note'),'Importantly, buyers choose.','filler phrase'),
 (('paras','P2','note'),'A brilliant result.','evaluative adjective'),
 (('paras','P1','els',0,'t'),'def','definition should name'),
 (('paras','P1','els'),[],'no element has a map label'),
 (('paras','P1','tier'),'skim','no close-read'),
])
def test_warnings(clean,path,value,message):
    doc,g=clean
    target=g
    for k in path[:-1]: target=target[k]
    target[path[-1]]=value
    _,warns,_=run_checks(doc,g)
    assert any(message in w for w in warns), warns

def test_missing_unknown_skip_overlap(clean):
    d,g=clean
    del g['paras']['P2']
    g['paras']['P99']={'tier':'skim'}
    g['paras']['P3'].update(tier='skip',why=None)
    g['paras']['P1']['els']*=2
    es,ws,comp=run_checks(d,g)
    assert any('no guide entry for P2' in e for e in es)
    assert any('not paragraphs or footnotes' in e for e in es)
    assert any('why is missing' in e for e in es)
    assert any('overlap' in w for w in ws)
    report(es,ws,comp)

@pytest.mark.parametrize('source,note,valid',[
 ('The share was 60.2%.','about 60%',False),
 ('It increased by an order of magnitude.','10 times',False),
 ('There were three buyers.','3 buyers',True),
 ('共有二十三名买家。','23 buyers',True)])
def test_numeric_precision(clean,source,note,valid):
    d,g=clean
    for i in d['items']: i['text']=source
    g['paras']['P1']['els']=[]
    g['paras']['P2']['note']=note
    es,_,_=run_checks(d,g)
    assert (not any('P2 note' in e for e in es)) == valid

def test_table_numbers(clean):
    d,g=clean
    d['items'].insert(2,{'id':'F1','type':'frag','text':'Treatment 87.4','page':1,'table':True})
    g['paras']['P2']['note']='Treatment had 87.4.'
    es,_,_=run_checks(d,g)
    assert not es

def test_duplicate_and_missing_rel(clean):
    d,g=clean
    g['parts'].append(copy.deepcopy(g['parts'][0]))
    g['parts'][1]['rel']=[]
    es,_,_=run_checks(d,g)
    assert any('duplicate part id' in e for e in es)

def test_two_part_cycle(clean):
    d,g=clean
    a=g['parts'][0]; b=copy.deepcopy(a)
    a.update(range='P1-P2',rel=[{'type':'supports','to':'B'}])
    b.update(id='B',range='P3-P4',claim_p='P3',rel=[{'type':'supports','to':'A'}],flow=[])
    g['parts']=[a,b]
    es,_,_=run_checks(d,g)
    assert sum('do not lead' in e for e in es)==2

def test_missing_relation_target_is_validation_error(clean):
    d,g=clean
    del g['parts'][0]['rel'][0]['to']
    errors,_,_=run_checks(d,g)
    assert any("'to' must be T" in e for e in errors)

def test_missing_relation_and_multiple_conclusions(clean):
    d,g=clean
    a=g['parts'][0]; b=copy.deepcopy(a)
    a.update(range='P1-P2',rel=[{'type':'concludes','to':'T'}])
    b.update(id='B',range='P3-P4',claim_p='P3',rel=[],flow=[])
    g['parts']=[a,b]
    es,_,_=run_checks(d,g)
    assert any("needs 'rel'" in e for e in es)
    b['rel']=[{'type':'concludes','to':'T'}]
    _,ws,_=run_checks(d,g)
    assert any('more than one part concludes' in w for w in ws)

@pytest.mark.parametrize('lang,text,message',[
 ('en','Buyers choose.','note is short'),
 ('zh','对奖励进行分析。','use a direct verb'),
 ('zh','值得注意的是，选择不同。','filler opener'),
 ('zh','总而言之，选择不同。','summary filler'),
 ('zh','不仅选择不同，而且奖励不同。','不仅'),
 ('zh','奖励起到激励作用。','say what it does'),
 ('zh','结果深刻。','evaluative adjective')])
def test_remaining_warnings(clean,lang,text,message):
    d,g=clean
    d['items'][1]['text']='Buyers choose rewards. '*40
    g['paras']['P2']['note']={lang:text}
    _,ws,_=run_checks(d,g)
    assert any(message in w for w in ws)


def _formula(clean, **extra):
    doc, g = clean
    doc['items'][0]['text'] = 'The share is s = 3 / 5, so three in five buyers chose it.'
    g['paras']['P1']['els'] = [dict({'t': 'formula', 'a': 's = 3 / 5', 'x': 'Three of five buyers'}, **extra)]
    return doc, g


def test_formula_tex_and_syms_accepted(clean):
    doc, g = _formula(clean, tex='s = \\frac{3}{5}', syms=[{'s': 's', 'm': 'share of buyers'}], why='fixes the baseline')
    errors, warns, _ = run_checks(doc, g)
    assert errors == [] and not [w for w in warns if 'tex' in w]


def test_formula_without_tex_warns(clean):
    errors, warns, _ = run_checks(*_formula(clean))
    assert errors == [] and any('tex' in w for w in warns)


@pytest.mark.parametrize('extra,message', [
    ({'tex': ''}, 'tex'),
    ({'syms': 'beta is the slope'}, 'syms'),
    ({'syms': [{'s': 'n', 'm': '77 students'}]}, 'numbers not in the source'),
])
def test_formula_errors(clean, extra, message):
    errors, _, _ = run_checks(*_formula(clean, **extra))
    assert any(message in e for e in errors)


def test_formula_unbalanced_braces_is_an_error(clean):
    errors, _, _ = run_checks(*_formula(clean, tex='e^{-\\frac{1}{2}\\left(x\\right)^{2}'))
    assert any('braces' in e for e in errors)
    errors, _, _ = run_checks(*_formula(clean, tex='e^{-\\frac{1}{2}\\left(x\\right)^{2}}'))
    assert errors == []


def test_recall_questions_accepted_and_missing_warns(clean):
    doc, g = clean
    errors, warns, _ = run_checks(doc, g)
    assert errors == [] and not any('recall' in w for w in warns)
    del g['parts'][0]['recall']
    errors, warns, _ = run_checks(doc, g)
    assert errors == [] and any('recall' in w for w in warns)


@pytest.mark.parametrize('recall,message', [
    ('What did buyers choose?', 'recall'),
    ([{'q': 'How many?'}], 'recall'),
    ([{'q': 'How many buyers?', 'a': '77 buyers.'}], 'numbers not in the source'),
])
def test_recall_errors(clean, recall, message):
    doc, g = clean
    g['parts'][0]['recall'] = recall
    errors, _, _ = run_checks(doc, g)
    assert any(message in e for e in errors)


def test_too_many_highlights_warns(clean):
    doc, g = clean
    doc['items'][0]['text'] = 'Alpha one. Beta two. Gamma three. Delta four. Epsilon five.'
    g['paras']['P1']['els'] = [{'t': 'claim', 'a': w} for w in ('Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon')]
    _, warns, _ = run_checks(doc, g)
    assert any('highlights' in w for w in warns)


def test_reader_questions_validated(clean):
    doc, g = clean
    g['meta']['purpose'] = 'core claims only'
    g['questions'] = [{'q': 'Do buyers prefer small rewards?', 'a': 'Yes: three buyers chose the smaller reward.', 'p': ['P1']}]
    errors, warns, _ = run_checks(doc, g)
    assert errors == []
    g['questions'] = [{'q': 'How many?', 'a': '99 buyers.', 'p': ['P1']}, {'q': 'Where?', 'a': 'Nowhere.', 'p': ['P9']}]
    errors, _, _ = run_checks(doc, g)
    assert any('numbers not in the source' in e for e in errors) and any('P9' in e for e in errors)


def test_missing_purpose_warns(clean):
    doc, g = clean
    del g['meta']['purpose']
    _, warns, _ = run_checks(doc, g)
    assert any('purpose' in w for w in warns)


def test_repeated_generic_roles_warn(clean):
    doc, g = clean
    for pid in ('P1', 'P2', 'P3', 'P4'):
        g['paras'][pid]['role'] = 'Definition'
    _, warns, _ = run_checks(doc, g)
    assert any('role' in w and 'Definition' in w for w in warns)
    for k, pid in enumerate(('P1', 'P2', 'P3', 'P4')):
        g['paras'][pid]['role'] = f'Evidence item {k}'
    _, warns, _ = run_checks(doc, g)
    assert not any('same role' in w for w in warns)


def test_formula_double_backslash_before_brace_is_not_an_escape(clean):
    # "\\{" is a line break followed by a group, not an escaped brace
    errors, _, _ = run_checks(*_formula(clean, tex='\\begin{cases} 3 \\\\{5} \\end{cases}'))
    assert not any('braces' in e for e in errors)


def test_formula_tex_numbers_must_come_from_the_source(clean):
    # 3 and 5 are in the paragraph; 7 is not. Sub- and superscripts are notation, not data.
    _, warns, _ = run_checks(*_formula(clean, tex='s_1 = \\frac{3}{5} x^{2}'))
    assert not any('tex' in w and 'numbers' in w for w in warns)
    _, warns, _ = run_checks(*_formula(clean, tex='s = \\frac{7}{5}'))
    assert any('tex' in w and 'numbers' in w and '7' in w for w in warns)


def test_inline_math_subscripts_are_notation_not_numbers(clean):
    doc, g = clean
    g['paras']['P2']['note'] = 'Two goods: $c_1 \\in C$, wealth $c_2$, and $m(c) = c_1^2 + c_2$.'
    errors, _, _ = run_checks(doc, g)
    assert not [e for e in errors if 'P2' in e and 'numbers' in e]
    g['paras']['P2']['note'] = 'Two goods: $c_1 = 9$.'
    errors, _, _ = run_checks(doc, g)
    assert [e for e in errors if 'P2' in e and '9' in e]
