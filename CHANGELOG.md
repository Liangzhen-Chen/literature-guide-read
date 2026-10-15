# Changelog

Add an entry at the top for every change to the rules or the workflow: version, date, what changed, and what prompted it (which reading, what went wrong).

## 0.6.0 (2026-10-15)

Prompted by Kőszegi and Rabin (2006), a JSTOR scan read with the brief "core claims only, bilingual": notes full of $c_1$, $p_{\max}$ and $\mu(x) = \eta x$ written as plain text looked wrong, and the MinerU converter mis-handled three things on the scan.

- Inline mathematics: any text field (notes, read lines, claims, explanations, recall) may hold LaTeX between single dollar signs, rendered inline by KaTeX; a span starting with a digit is money unless it holds LaTeX, operators or no spaces. check.py treats sub- and superscripts inside such spans as notation. Rule in method.md section 5 and schema.md.
- mineru_backend.py: a doc_title at the top of a page followed by a volume line is the journal masthead, not the title; the title then comes from the running head that is not the journal name. A numbered text block at the foot of a page is a footnote. A page's first text block that starts in lower case continues the previous page's open paragraph.
- render.py: captions and mentions numbered in Roman (TABLE II, Figure IV) resolve like Arabic ones, so a table crop reaches the paragraph that first cites it; a paragraph that is only an equation label, "(2a)", is not a crop host. mineru_backend.py turns such a label into a fragment.
- segment.py: superscript digits ("given by²") count as footnote markers; the period after a footnote number is stripped.

## 0.5.1 (2026-10-15)

Five small findings from the 0.4.0 code review, each with a regression test that failed first.

- check.py: `\\` before a brace is a line break, not an escaped brace, so `\\{` no longer trips the brace check; numbers inside `tex` must appear in the source text (warning, with sub- and superscripts treated as notation).
- mineru_backend.py: a heading block with `level: null` no longer crashes the converter.
- render.py: crops are re-encoded as optimised grayscale PNG before embedding (20 to 30% smaller pages).
- check.py: "inequality (8)", "expression (15)", "Definition 1", "Lemma 2", "Theorem 3", "Corollary 4" and their Chinese forms are references, not data (Kőszegi and Rabin 2006 cites its inequalities by number).
- mineru_backend.py: footnote blocks that are empty or hold a stray symbol are dropped (a JSTOR scan produced twelve such notes).
- segment.py: on ranges of three pages or fewer, a head-like line at the same height as a repeated running head on a neighbouring page is removed too (odd/even heads each appear only once or twice there). Longer ranges, first pages and sentence-like lines are untouched; the 11 corpus readings segment identically.

## 0.5.0 (2026-10-15)

Prompted by the question of what evidence the reading method rests on. The changes follow published studies of reading interfaces and learning: skimming highlights (Scim), on-demand definitions (ScholarPhi), argument mapping, prequestions and retrieval practice, self-explanation of worked examples.

- Brief first: the workflow starts with one round of questions (language and purpose required; familiarity and the reader's own questions optional). `meta.purpose` selects a tier profile (method.md section 3a); `questions` are answered from the text with paragraph links and shown at the top of the page.
- Recall: every part carries two or three `recall` questions, folded at the end of the part with the answers hidden. check.py validates them and warns when they are missing.
- Page: a Gist view (notes only, originals and crops folded); hover definitions for every defined term and symbol wherever it recurs; a "guess the relations" mode on the argument map; formula explanations folded under the formula and its crop; a reading progress bar; reading column narrowed to about 70 characters.
- check.py warns when a paragraph carries more than four highlights.
- check.py warns when four or more paragraphs carry the same role: a role says what that paragraph does, not its kind.
- README in English and Chinese with the same structure as other published skills, with screenshots from an openly licensed demo.

## 0.4.0 (2026-10-14)

Prompted by List (2003), a JSTOR scan of the QJE: its MediaBox starts at y=40, pdfplumber reports every coordinate in that offset frame, so the running heads fell outside the margin band and became headings; the display equation was lost as a fragment, "Experiment I" was rewritten to "Experiment 1", and the previous run had to rebuild the text by hand and lost the page images.

- Segment: text-layer coordinates are now page-relative whatever the MediaBox origin; running heads are detected by repetition anywhere in the top or bottom 15% of the page, captions and equation labels excluded; in `auto` mode a failing MinerU run falls back to pdfplumber; OCR size noise no longer turns continuation lines into headings; the Roman-numeral OCR repair is suppressed in documents that use Roman numerals and its count is reported; every item records its page box; display equations and table regions are cropped to `WORK/crops/`.
- Optional MinerU engine (`--engine mineru`, automatic when installed): layout analysis with the skill's own sidebar, front-matter, heading-level and footnote rules; formulas get LaTeX when the formula model is installed, crops otherwise. Measured against the default on 11 readings; see README.
- Guide data: `formula` elements carry `tex`, `syms` and `why`; check.py validates them, warns when `tex` is missing and rejects unbalanced braces. The number checker treats `equation (3)` and `公式 (3)` as references and no longer splits a decimal after 表. Method: a formula the argument relies on is a close read.
- Page: PDF crops under paragraphs with formulas or tables (a table's crop goes to the paragraph that first cites it), KaTeX-rendered formulas with symbol tables; `--dump` restores the crops; KaTeX 0.16.11 (MIT) is vendored and inlined only in pages that contain formulas.
- SKILL.md: a recovery path when segmentation looks wrong, before falling back to `--text`.

## 0.3.2 (2026-10-07)

Prompted by the real-paper, browser, OCR and live-source tests in sections 4, 6 and 8. Every production fix has a preceding failing regression commit.

- Checker: distinguish normal-distribution parameters such as `N(496,114)` from comma-grouped thousands; prompted by a false numeric error on the real textbook guide.
- Segment: preserve numbered ACM headings, printed page fractions, mixed-page OCR routing, Chinese abstract starts and long bold prose; separate small-font publisher sidebars from body text.
- Sources: recognize reversed arXiv margin text; reject conversion-error HTML and safely extract regular TeX files on Python 3.9; resolve relative assets, nested captions and SVG objects; parse bracket equations and wrapped tables; normalize inline notes, math alternatives and joined OCR words when comparing prose.
- Reader: preserve expanded originals in print, name and contain focus in the page viewer, return focus when it closes, preserve reading position on language changes, and use UTF-16 highlight offsets after non-BMP characters. Make scrollable page images and wide tables keyboard-accessible, handle WebKit arrow scrolling, and clear desktop graph transforms on mobile resize.
- Switch crowded graph labels to a complete relation list when they overlap or clip; retain the graph for sparse maps.
- Add repeatable corpus, unit, browser, live-source, model and performance evidence. Keep unmet segmentation, image-render speed and service-compatibility targets visible in the report.
- Choose MIT for original project code under delegated review; add dependency and source-licence notices. Refresh English and Chinese installation/known-issue documentation.

## 0.3.1 (2026-10-07)

Prompted by section 3 of the pre-publication test plan. Both fixes have regression tests that failed before implementation.

- check.py: a relation without a `to` target now reports validation errors instead of crashing while formatting the path to the conclusion.
- common.py: skip malformed element definitions with nonnumeric levels, as already done for malformed field counts.

## 0.3.0 (2026-10-07)

Prompted by the English KKT page: the argument map was sectioned well but did not show how the parts connect.

- Logic map: the conclusion at the top; parts linked by typed relations (supports, explains, qualifies, extends, frames, challenges, answers); clicking a part shows its reasoning steps, each linked to its paragraph. Narrow screens get a list with each relation written out. Guides without relations still get the part grid.
- Guide data: parts gain `rel` and `flow` (method.md section 10, schema.md).
- check.py: relation and step types are checked, every part must lead to the conclusion without cycles, steps must lie inside their part, and numbers in labels and steps must appear in the source.
- render.py `--dump` keeps relations and steps.

## 0.2.1 (2026-10-07)

- Author headings now render by level, so a level-1 heading such as "Introduction" outranks the guide's part headers beneath it. Prompted by an English KKT page where "Introduction" looked smaller than the part title under it: the template had drawn every author heading in one small grey style.
- Segmentation: heading sizes that differ by less than 8% count as one level, so OCR size noise cannot split same-rank headings into different levels.

## 0.2.0 (2026-10-06)

Prompted by KKT (1991), guided once with Claude and once with GPT. Neither model's notes were full enough to let the reader skip a paragraph; the structure mirrored the author's headings; and the two runs numbered paragraphs differently, because both rewrote the segmentation by hand after the script failed on a JSTOR scan.

- The page is built around the original text: close reads open with a "read for" line; skim and skip paragraphs lead with a note that restates them, with the original collapsed underneath.
- Elements (definitions, claims, evidence, figures, tables, formulas, mechanisms, qualifications) replace the single function label and the nested outline with cores. Each is anchored to a verbatim span and highlighted in the original. Types live in `references/elements.md`.
- An argument map of parts and claims replaces the tree; a sidebar lists each paragraph's role, the terms and the evidence.
- Notes in Chinese, English or both, with a language switch. The documentation is now English-first, with a Chinese README.
- Figures and tables attach to the paragraph that first cites them, with whole-page images instead of cropping.
- `sources.py`: optional open versions (arXiv HTML, TeX source as a fallback) for figures, tables and formulas, and a report of words the PDF text layer dropped. The PDF stays the source of the text and page numbers.
- `check.py`: every number in the guide must appear in the source; anchors must be verbatim; warnings when skim notes describe instead of restate.
- `segment.py`: handles JSTOR scans (watermarks, alternating running heads, unmapped glyphs, OCR'd footnote markers, captions such as "Figure 1 Title", table rows, survey result lines, printed page numbers), links footnotes to the paragraphs that cite them, and recognises Chinese headings (第一章, 一、, （一）) and circled footnote markers.
- Close-read caps keep their starting values: low 15%, medium 25%, high 40%.

## 0.1.0 (2026-10-05)

- First version: segmentation of PDF text layers, scans (OCR) and plain text; validation of per-paragraph notes, a contiguous outline with cores, tier density and anchors; an HTML guide page with an outline, a paragraph strip and a reading route.
- Method based on descriptive outlines (what each paragraph says and does) and the nucleus/satellite distinction of Rhetorical Structure Theory.
- Works outside Claude: Agent Skills format, plain Python scripts, and a manual mode for any chat model.
