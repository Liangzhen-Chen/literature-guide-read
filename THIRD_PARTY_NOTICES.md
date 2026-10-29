# Third-party notices

The repository's MIT licence covers its original code and documentation. It does not replace the licences on source readings, dependencies, or generated pages containing source text.

## Python packages

Installed separately with `pip install -r requirements.txt`; none is bundled.

| Package | Licence | Project |
| --- | --- | --- |
| pdfplumber | MIT | https://github.com/jsvine/pdfplumber |
| pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| beautifulsoup4 | MIT | https://www.crummy.com/software/BeautifulSoup/ |

Their distributions contain their full copyright and licence notices. Transitive dependencies retain their own notices. The optional page-image fallback uses separately installed Poppler (pdftoppm), which is not included here or required for segmentation.

## KaTeX

KaTeX 0.16.11 (MIT licence, Khan Academy and contributors) is vendored under `assets/katex/`. Its licence text is in `assets/katex/LICENSE`. It is inlined, with its fonts, only into pages that contain formulas.

## MinerU

MinerU is an optional dependency that the user installs separately. `scripts/mineru_backend.py` calls it through a subprocess. This repository does not distribute MinerU; its licence is at https://github.com/opendatalab/MinerU/blob/master/LICENSE.md.

## Adobe Symbol encoding table

`scripts/adobe_symbol.txt` is the Adobe Symbol to Unicode mapping published by Unicode, Inc. (https://www.unicode.org/Public/MAPPINGS/VENDORS/ADOBE/symbol.txt). It is copied unchanged with its notice, which permits redistribution as long as the notice stays attached. `segment.py` uses it to read list bullets and symbols set in the Symbol font.

## TeX OMS encoding table

`scripts/tex_oms.txt` lists the 128 slots of TeX's OMS encoding (the Computer Modern math-symbol fonts) with their Unicode characters. The slot assignments follow the encoding as LaTeX defines it in `omsenc.def` (LaTeX Project Public License); the file is a table of those facts written for this repository, with no LaTeX code copied. `segment.py` uses it to read minus signs and other symbols in PDFs typeset with TeX.

## Hallmark

The layout of the reading page follows the rules of the Hallmark design skill (MIT, Copyright (c) 2026 Hallmark contributors, https://github.com/Nutlope/hallmark). None of its code is bundled; the first line of the template's CSS names the source.

## Writing rules

The wording rules in `references/method.md` (section 9a) draw on blader/humanizer (MIT, https://github.com/blader/humanizer) and Wikipedia's "Signs of AI writing". No text from either was copied.

## Test data

The text in `tests/fixtures/mineru_structured_small.json` comes from Ioannidis JPA (2005), Why Most Published Research Findings Are False. PLoS Med 2(8): e124. https://doi.org/10.1371/journal.pmed.0020124. The article is published under the Creative Commons Attribution License (CC BY).
