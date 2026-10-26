# Third-party notices

The repository's MIT licence covers its original code and documentation. It does not replace the licences on source readings, dependencies, or generated pages containing source text.

## Python packages

Installed separately with `pip install -r requirements.txt`; none is bundled.

| Package | Licence | Project |
| --- | --- | --- |
| pdfplumber | MIT | https://github.com/jsvine/pdfplumber |
| pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| pytesseract | Apache-2.0 | https://github.com/madmaze/pytesseract |
| pdf2image | MIT | https://github.com/Belval/pdf2image |
| beautifulsoup4 | MIT | https://www.crummy.com/software/BeautifulSoup/ |

Their distributions contain their full copyright and licence notices. Transitive dependencies retain their own notices. OCR additionally uses separately installed Tesseract and Poppler, which are not included here.

## KaTeX

KaTeX 0.16.11 (MIT licence, Khan Academy and contributors) is vendored under `assets/katex/`. Its licence text is in `assets/katex/LICENSE`. It is inlined, with its fonts, only into pages that contain formulas.

## MinerU

MinerU is an optional dependency that the user installs separately. `scripts/mineru_backend.py` calls it through a subprocess. This repository does not distribute MinerU; its licence is at https://github.com/opendatalab/MinerU/blob/master/LICENSE.md.

## Hallmark

The layout of the reading page follows the rules of the Hallmark design skill (MIT, Copyright (c) 2026 Hallmark contributors, https://github.com/Nutlope/hallmark). None of its code is bundled; the first line of the template's CSS names the source.

## Writing rules

The wording rules in `references/method.md` (section 9a) draw on blader/humanizer (MIT, https://github.com/blader/humanizer) and Wikipedia's "Signs of AI writing". No text from either was copied.

## Test data

The text in `tests/fixtures/mineru_structured_small.json` comes from Ioannidis JPA (2005), Why Most Published Research Findings Are False. PLoS Med 2(8): e124. https://doi.org/10.1371/journal.pmed.0020124. The article is published under the Creative Commons Attribution License (CC BY).
