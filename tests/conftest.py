import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

@pytest.fixture
def clean():
    doc = {'items': [{'id': f'P{i}', 'type': 'para', 'page': 1,
                     'text': 'Three buyers chose the smaller reward. The measured share was 60.2%.'}
                    for i in range(1, 5)], 'page_count': 1}
    guide = {'meta': {'title': 'Reward choices', 'notes_lang': ['en'], 'purpose': 'understand the argument'},
             'thesis': 'Buyers choose the smaller reward.', 'overview': 'Choices vary with rewards.',
             'parts': [{'id': 'A', 'range': 'P1-P4', 'title': 'Choices', 'role': 'Evidence',
                        'claim': 'Buyers choose the smaller reward.', 'claim_p': 'P1',
                        'rel': [{'type': 'supports', 'to': 'T'}],
                        'recall': [{'q': 'What did buyers choose?', 'a': 'The smaller reward.'}],
                        'flow': [{'p': 'P1', 'x': 'Buyers choose.'},
                                 {'p': 'P2', 'x': 'Rewards vary.', 'rel': 'explains'}]}],
             'paras': {f'P{i}': {'tier': 'close' if i == 1 else 'skim', 'role': f'Choice {i}',
                        'read': 'Track the choices.', 'note': 'Buyers choose the smaller reward.',
                        'els': []} for i in range(1, 5)}}
    guide['paras']['P1']['els'] = [{'t': 'claim', 'a': 'Three buyers', 's': 'Buyers choose'}]
    return doc, guide


def _pdf_bytes(pages):
    """A small born-digital PDF: each page is a list of (x, y, text) in PDF points on a 612x792 page, Helvetica 12."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        content = b"".join(f"BT /F1 12 Tf {x} {y} Td ({t}) Tj ET\n".encode() for x, y, t in lines) + b"0 0 0 rg 60 300 480 20 re f\n"
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents " + str(len(objs)).encode() + b" 0 R >>")
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(f"{k} 0 R".encode() for k in kids) + b"] /Count " + str(len(kids)).encode() + b" >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


@pytest.fixture
def sample_pdf(tmp_path):
    """Three text pages with a running head, body sentences, an equation line and a black bar (for crop tests)."""
    body = ["The normal distribution has two parameters, the mean and the standard deviation.",
            "If X is a quantity with a normal distribution we write X ~ N(mu, sigma).",
            "The z-score counts standard deviations from the mean of the distribution."]
    pages = []
    for n in range(1, 4):
        lines = [(60, 760, f"JOURNAL OF EXAMPLES {n}")]
        lines += [(60, 700 - 20 * k, body[k]) for k in range(3)]
        lines += [(200, 600, "z = (x - mu) / sigma (1)"), (60, 560, "Values of x above the mean have positive z-scores.")]
        pages.append(lines)
    path = tmp_path / "sample.pdf"
    path.write_bytes(_pdf_bytes(pages))
    return path
