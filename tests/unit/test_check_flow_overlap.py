"""Character containment is a language-independent warning, never an error."""
import pytest
from check import note_containment, run_checks


@pytest.mark.parametrize('step,note', [
    ('The neutral sample supports the proposed mechanism.', 'The neutral sample supports the proposed mechanism. A separate qualification follows.'),
    ('这个中性例子支持所提出的解释机制。', '这个中性例子支持所提出的解释机制。另外还有一个独立的限定条件。'),
    ('THE NEUTRAL SAMPLE supports the proposed mechanism!', 'The neutral sample supports the proposed mechanism.'),
])
def test_contained_or_punctuation_edited_copy_warns(step, note):
    assert note_containment(step, note) >= .9


@pytest.mark.parametrize('step,note', [
    ('The proposed mechanism', 'A proposed mechanism is rejected by independent observations.'),
    ('A counterexample limits the interpretation of the preceding estimate.', 'The neutral sample supports the proposed mechanism.'),
    ('不同样本之间的对照限定了前面结论的适用范围。', '这个中性例子支持所提出的解释机制。另外还有一个独立的限定条件。'),
    ('Buyers choose.', 'Buyers choose the smaller reward.'),
])
def test_shared_terms_and_different_reasoning_moves_do_not_warn(step, note):
    assert note_containment(step, note) < .9


def test_overlap_warning_does_not_add_errors(clean):
    doc, guide = clean
    guide['parts'][0]['flow'][0]['x'] = guide['paras']['P1']['note']
    errors, warnings, _ = run_checks(doc, guide)
    assert not errors and any('largely repeats P1' in w for w in warnings)
