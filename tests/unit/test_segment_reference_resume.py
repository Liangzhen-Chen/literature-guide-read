"""Reference-mode boundaries independently observed in OpenStax C12, pp. 54–61."""
import pytest
import segment as s


def heading(text, level=1):
    return {'type': 'heading', 'text': text, 'level': level}


def para(text):
    return {'type': 'para', 'text': text}


def test_textbook_solutions_resume_after_sectioned_bibliography():
    blocks = [heading('REFERENCES'),
              heading('1.1 Definitions of Statistics, Probability, and Key Terms', 2),
              para('A real chapter reference.'),
              heading('1.4 Experimental Design and Ethics', 2),
              para('A second real chapter reference.'),
              heading('SOLUTIONS'), para('1 AIDS patients.'),
              heading('2 | DESCRIPTIVE STATISTICS'), para('The next chapter begins here.')]
    assert s.mark_sections(blocks) == 4
    assert [b['type'] for b in blocks] == ['ref'] * 5 + ['heading', 'para', 'heading', 'para']


@pytest.mark.parametrize('title', ['Chapter 2 Descriptive Statistics',
                                   '2 | DESCRIPTIVE STATISTICS',
                                   '第二章 描述统计'])
def test_explicit_new_chapter_resumes_without_solutions(title):
    blocks = [heading('References'), para('Smith (2020). A reference.'),
              heading(title), para('Independent chapter body.')]
    assert s.mark_sections(blocks) == 1
    assert blocks[2]['type'] == 'heading'
    assert blocks[3]['type'] == 'para'


@pytest.mark.parametrize('title,level', [('Primary sources', 1), ('1.4 Experimental Design and Ethics', 2),
                                       ('Solutions', 2), ('Bibliographic notes', 1)])
def test_bibliography_subsections_remain_excluded(title, level):
    blocks = [heading('References'), heading(title, level), para('Smith (2020). A reference.')]
    assert s.mark_sections(blocks) == 2
    assert all(b['type'] == 'ref' for b in blocks)


def test_resumed_body_can_enter_second_bibliography_and_preserves_notes():
    blocks = [heading('References'), para('First reference.'), heading('SOLUTIONS'),
              para('Worked answer.'), heading('References'), para('Second reference.'),
              {'type': 'note', 'text': '2Differences remain.'}]
    assert s.mark_sections(blocks) == 2
    assert blocks[3]['type'] == 'para'
    assert blocks[5]['type'] == 'ref'
    assert blocks[6]['type'] == 'note'
