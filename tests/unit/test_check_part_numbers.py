"""Part number scopes follow item order; paragraph scopes remain local."""
import pytest

from check import run_checks


def field(guide, name, text):
    part = guide['parts'][0]
    if name == 'claim':
        part['claim'] = text
        return 'A claim'
    if name == 'flow':
        part['flow'][0]['x'] = text
        return 'A flow step 1'
    key = 'q' if name == 'recall_q' else 'a'
    part['recall'][0][key] = text
    return f'A recall 1 {key}'


@pytest.mark.parametrize('name', ['claim', 'flow', 'recall_q', 'recall_a'])
@pytest.mark.parametrize('kind', ['frag', 'caption'])
def test_part_field_accepts_internal_table_or_equation(clean, name, kind):
    doc, guide = clean
    doc['items'].insert(3, dict(id='F1', type=kind, text='Estimate 17.25', page=1))
    where = field(guide, name, 'The estimate is 17.25.')
    errors, _, _ = run_checks(doc, guide)
    assert not any(where in error and '17.25' in error for error in errors), errors


@pytest.mark.parametrize('name', ['claim', 'flow', 'recall_q', 'recall_a'])
def test_part_field_accepts_table_after_last_paragraph(clean, name):
    doc, guide = clean
    doc['items'].append(dict(id='F1', type='frag', text='Estimate 17.25', page=1))
    where = field(guide, name, 'The estimate is 17.25.')
    errors, _, _ = run_checks(doc, guide)
    assert not any(where in error and '17.25' in error for error in errors), errors


@pytest.mark.parametrize('name', ['claim', 'flow', 'recall_q', 'recall_a'])
@pytest.mark.parametrize('before', [True, False])
def test_part_field_rejects_fragment_outside_the_part(clean, name, before):
    doc, guide = clean
    if before:
        doc['items'].insert(0, dict(id='F1', type='frag', text='Estimate 17.25', page=1))
    else:  # past the run that follows the last paragraph
        doc['items'] += [dict(id='H1', type='heading', text='Next', page=1),
                         dict(id='F1', type='frag', text='Estimate 17.25', page=1)]
    where = field(guide, name, 'The estimate is 17.25.')
    errors, _, _ = run_checks(doc, guide)
    assert any(where in error and '17.25' in error for error in errors), errors


def test_paragraph_fields_keep_neighbour_scope(clean):
    doc, guide = clean
    doc['items'].insert(3, dict(id='F1', type='frag', text='Estimate 17.25', page=1))
    guide['paras']['P1']['note'] = 'The estimate is 17.25.'
    guide['paras']['P3']['note'] = 'The estimate is 17.25.'
    errors, _, _ = run_checks(doc, guide)
    assert any('P1 note' in error and '17.25' in error for error in errors), errors
    assert not any('P3 note' in error and '17.25' in error for error in errors), errors


def test_part_scope_uses_item_positions_and_retains_linked_notes(clean):
    doc, guide = clean
    doc['items'][1]['page'] = 3
    doc['items'].insert(2, dict(id='F1', type='frag', text='Estimate 17.25', page=99))
    doc['items'].append(dict(id='N1', type='note', text='Note estimate 28.5', page=4))
    doc['items'][0]['notes'] = ['N1']
    guide['parts'][0]['claim'] = 'The estimates are 17.25 and 28.5.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('A claim' in error and 'source text' in error for error in errors), errors


@pytest.mark.parametrize('name', ['thesis', 'overview'])
@pytest.mark.parametrize('kind', ['frag', 'caption'])
@pytest.mark.parametrize('before', [True, False])
def test_document_field_accepts_all_fragment_and_caption_numbers(clean, name, kind, before):
    doc, guide = clean
    item = dict(id='F1' if kind == 'frag' else 'C1', type=kind,
                text='F-test probability 0.037', page=1)
    doc['items'].insert(0 if before else len(doc['items']), item)
    guide[name] = 'The F-test probability is 0.037.'
    guide['paras']['P1']['note'] = 'The F-test probability is 0.037.'
    errors, _, _ = run_checks(doc, guide)
    assert not any(error.startswith(name) and '0.037' in error for error in errors), errors
    assert any('P1 note' in error and '0.037' in error for error in errors), errors


@pytest.mark.parametrize('name', ['thesis', 'overview'])
def test_document_field_still_rejects_absent_number(clean, name):
    doc, guide = clean
    doc['items'].append(dict(id='F1', type='frag', text='F-test probability 0.037', page=1))
    guide[name] = 'The F-test probability is 0.038.'
    errors, _, _ = run_checks(doc, guide)
    assert any(error.startswith(name) and '0.038' in error for error in errors), errors


@pytest.mark.parametrize('label,cite', [('Table 3. Fit indices', 'As Table 3 shows'), ('Fig. 2 Loadings', 'see Figure 2'),
                                        ('表 3 拟合指标', '见表 3')])
def test_paragraph_citing_a_labelled_exhibit_gets_its_rows(clean, label, cite):
    doc, guide = clean
    doc['items'][1:1] = [dict(id='C1', type='caption', text=label, page=1),
                         dict(id='F1', type='frag', text='CFI 0.957', page=1)]
    p3 = next(it for it in doc['items'] if it['id'] == 'P3')
    p3['text'] = p3['text'] + f' {cite}, the fit is good.'
    guide['paras']['P3']['note'] = 'CFI is 0.957.'
    errors, _, _ = run_checks(doc, guide)
    assert not any('P3 note' in error and '0.957' in error for error in errors), errors


def test_citing_another_exhibit_number_does_not_widen_scope(clean):
    doc, guide = clean
    doc['items'][1:1] = [dict(id='C1', type='caption', text='Table 3. Fit indices', page=1),
                         dict(id='F1', type='frag', text='CFI 0.957', page=1)]
    p3 = next(it for it in doc['items'] if it['id'] == 'P3')
    p3['text'] = p3['text'] + ' As Table 4 shows, the fit is good.'
    guide['paras']['P3']['note'] = 'CFI is 0.957.'
    errors, _, _ = run_checks(doc, guide)
    assert any('P3 note' in error and '0.957' in error for error in errors), errors
