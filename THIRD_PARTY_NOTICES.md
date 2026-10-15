# Third-party notices

The repository's MIT licence covers its original code and documentation. It does not replace the licences on source readings, test PDFs, dependencies, or generated pages containing source text.

Dependencies are installed separately and are not bundled in the release ZIP:

| Package | Licence | Project |
| --- | --- | --- |
| pdfplumber | MIT | https://github.com/jsvine/pdfplumber |
| pytesseract | Apache-2.0 | https://github.com/madmaze/pytesseract |
| pdf2image | MIT | https://github.com/Belval/pdf2image |
| beautifulsoup4 | MIT | https://www.crummy.com/software/BeautifulSoup/ |

Their distributions contain their full copyright and licence notices. Transitive dependencies retain their own notices. OCR additionally uses separately installed Tesseract and Poppler; neither binary is included in the ZIP.

Test literature and derivatives have individual attribution, source URLs, licence identifiers, and hashes in `tests/corpus/manifest.json`. The corpus includes CC0, CC BY, CC BY-SA, and CC BY-NC-SA works; none is relicensed under MIT. C09 is excluded from public demos. Private sample readings and all generated guides remain outside Git and the release ZIP.

Browser testing uses separately installed Playwright (Apache-2.0) and axe-core (MPL-2.0). These testing tools are not part of the distributed skill.

## KaTeX

KaTeX 0.16.11 (MIT licence, Khan Academy and contributors) is vendored under `assets/katex/` and inlined, with its fonts, only into pages that contain formulas.
