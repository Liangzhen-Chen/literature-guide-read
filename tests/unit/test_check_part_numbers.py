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
