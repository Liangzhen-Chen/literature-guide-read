# Changelog

Add an entry at the top for every change to the rules or the workflow: version, date, what changed, and what prompted it (which reading, what went wrong).

## 0.8.0 (2026-10-30)

Full guide trials on unseen papers prompted two new workflow steps. Page inspection catches extraction errors before the guide uses its IDs; a second read catches claims that pass the script checks and still mislead a reader.

### Workflow

- Crop regions can list original IDs in `replaces` to retire partial crops while keeping their text and replayable originals.
- Step 1b, look and fix: `fix.py overlay` draws item boxes and IDs on PDF pages, with a coordinate grid and heading levels. The agent writes `fixes.json` to type, join, split, move or rebuild an item from a page region using PDF words. Split tails have stable names such as `P9#2`. Fixes replay from paragraphs.orig.json; `overlay --orig`, `fix.py ids`, target echoes and fixes_log.json help distinguish original IDs from the current numbering. Crops follow new IDs, with originals kept for replay, including on Windows. Lists, definitions and captions stay visible; running heads inside paragraphs can be split out, hidden and the remaining text joined.
- A region op can also make a crop: `to` table, figure or display covers a whole table, a vector diagram, a code listing or a display equation that the basic tier cropped partly or not at all, and the page shows it under the paragraph named in `after`.
- Step 5b, second read: a separate reader follows `references/review.md` after check.py passes, then the writer fixes its findings and checks again before rendering. Where a separate agent cannot be started, the writer rereads field by field. The reader then confirms the changed fields, because a correction once moved a quotation to the wrong speaker. Trials found dropped hedges, overstated results, wrong signs and hidden argument text even in guides that passed check.py. The chat reply reports findings and fixes; the READMEs explain the extra usage.
- The skill is now named literature-guide-read, matching the repository and page footer. Users of 0.7.0 should remove the reading-guide skill folder and install again. The maintenance instructions identify the correction and review files. Release packages include the encoding tables, scripts, references and assets.

### Segmentation and symbols

- The basic tier crops embedded raster images with a nearby figure/table or other exhibit label, merges touching panels and places them beside their captions; existing table and rotated-page crops take precedence.
- Rotated-text pages that earlier trials silently lost are reported and kept as table crops, turned upright from the glyph direction. Ordinary crops retain their orientation.
- The basic tier decodes unresolved glyphs in TeX math-symbol fonts through the standard OMS table and TeX math italic through OML. Adobe's Symbol table recovers bullets and symbols in that encoding. These repairs restore lost minus signs and Greek letters; already decoded text stays unchanged. A warning names pages where custom Greek or math fonts return plain letters or a misleading symbol, so the agent reads them from crops or page images. Other unrecovered glyphs keep their codes and source positions; warnings exclude covered display ink and proven nonprinting marks.
- A column cut that leaves all lines on one side no longer crashes. Blank pages remain in the run; image-only pages are named and skipped, and scan-only input directs the agent to MinerU. The basic tier finds page columns, including three-column text and full-width regions, and retries column settings when its self-check finds problems. The first-time trial on the licensed Ioannidis (2005) demo exposed mixed columns and references among the body paragraphs.
- Further trials prompted repairs for covers, bylines, abstracts, metadata columns, quotations, lists, run-in headings, table notes, captions and paragraph continuations. Titles after covers and mastheads are handled more reliably; step 1b still checks them. Table detection includes horizontal-rule tables and tables without rules, and reference sections can end before later exhibits and appendices.
- Font metadata from fonttools improves style and case handling. Baseline alignment, spacing accents, overprinted or duplicated text, OCR word breaks and touching fallback-font ligatures are repaired; words outside the page are ignored and stretched text layers are scaled back. Document evidence guides line-end hyphens. Plot titles and floats allow body paragraphs to continue around them. Roman numbering is preserved when the document uses it.
- MinerU and the basic tier share paragraph continuation rules, including bracketed citations split at a page break. MinerU avoids repeated captions and continuation sentences typed as headings, and handles first-page metadata more reliably. SKILL.md states that MinerU prints no self-check line.

### Reading rules

- Trials on empirical and argument papers prompted closer checks of direction, strength and setting in every short field and result note. Keep model assumptions, hedges, sample, period, specification, shock, denominator and group limits wherever a result is repeated. State lack of significance precisely; comparisons across methods and robustness ranges keep their context. Results the authors assert or read from point estimates without a shown test are attributed to them.
- Notes keep each criticism's object, the authors' points of agreement, terms at the source's strength, and exceptions in the text's own evidence. Paragraphs that correct another author's reading or state a result derived from a key formula are close reads. Read each table or figure before repeating a sentence describing it; when the sentence and exhibit differ, report both. A translated description becoming a stronger technical claim and summaries overlooking an exception prompted these rules.
- Write entries from the paragraph in hand. Newcomers get definitions at first use, including brief glosses in the thesis and part claims. Identification, main results and relevant robustness checks are close reads; notes state identification assumptions and the evidence offered for them. Flow steps explain the move and its reason without repeating notes; each part has a why/how recall question. Replies to reader questions answer the reason asked. Role and read limits are stated alongside their fields.

### Number checks

- Source-number checks also accept decimals and thousands counts whose text layer inserts a space after the separator; existing accepted values remain available.
- A text layer that sets a decimal with a space before the point ("62 .8") still supplies 62.8.
- Source-number extraction accepts spelled-out numbers, ordinal words, split digits, space/comma-grouped thousands, English month names and abbreviated year-range endpoints, including century rollover. Dates can use month numbers in Chinese notes; centuries and decades are accepted when the source has a corresponding year. Numeric ranges keep both endpoints; Chinese equation labels and page/figure/table ranges are treated as references. These changes address false errors from otherwise faithful notes.
- Part claims, flow steps and recall questions/answers can use fragments and captions within the part's item range and the run after its last paragraph. Thesis and overview can use all document fragments and captions. Paragraph fields retain their local scope. The checker also warns when flow steps copy paragraph notes, and handles money beside inline maths without a spurious line-break warning. The schema and method state these scopes and the thesis/claim length limits.

## 0.7.0 (2026-10-27)

Close reads get an after-reading summary, and the reading page is redesigned. Two real readings prompted it, Ioannidis (2005) and the DPO paper (Rafailov et al. 2023, arXiv 2305.18290), and so did the author's verdict on the old page: too cluttered. Both readings were run end to end with the skill, and the page showed far more than a reader could use.

Page (assets/template.html), laid out after the Hallmark design skill's long-document rules (MIT, see THIRD_PARTY_NOTICES.md). The test for every element was whether it helps the reader remember the paper.

- Removed: the sidebar with its evidence table, the overview paragraph under the conclusion, the purpose and familiarity lines, the map legend and its explanatory text, the four view buttons, the role label, element sub-labels and tier text on each paragraph, the category badges before highlights, and the seven highlight colours. The data stays in the JSON; only the page no longer shows it.
- Merged: the vertical argument map and the "whole argument" block became one SVG mind map (no library) with one row per part, a dashed line for `qualifies` and a plain line for every other relation (the name is in the tooltip). The map stops at the conclusion and the parts; the steps live in the left margin (see the second round below). The four views became two, full text and summaries only. The seven highlight colours became one faint highlight, with the category in the tooltip.
- Folded: the reader's questions (one line, "your N questions"), the "guess the relations" switch, skip paragraphs (one line, original folded), and the PDF crop, explanation and symbol table of a display formula ("check the original"). Terms moved into a lookup button (the index of all terms); hover definitions stay.
- Reading: a thin bar with back to the map, full text or summaries, terms and a progress line. Simple inline formulas are set as text in the body font; complex ones go to KaTeX. Dark mode, the language switch and the single offline file stay.
- Inline LaTeX is rendered in the original text, mind map nodes, claims, flow steps, recall questions and element fields. A highlight never splits a formula, and terms are not matched inside one.
- Close-read paragraphs show `note` as the folded after-reading summary, below the original and its formulas.

Second round of the page, after the author looked at the demo pages. The feedback: notes and original were hard to tell apart, the page used too small a share of the screen, the term pop-ups were not intuitive, Chinese notes translated terms by force, and the second paragraph lost its first letter.

- Fonts: the paper's text (original paragraphs, captions, the paper's own section headings) is in a serif. What the guide writes (reading prompts, after-reading summaries, skim restatements, part claims, conclusion, recall answers) is in a sans, slightly smaller and lighter.
- Left margin: the page margin is the navigation for the current section. It holds the part title and claim, the reasoning steps (click to jump, a dark bar marks the current step) and the terms first defined in the section (four shown, the rest folded). The Terms button stays as the index of all terms. On a narrow screen the margin folds into a "This part's structure" toggle.
- Width: the page width follows the screen and the type size grows with the viewport within a range; on very wide screens the side margins grow to keep the line length.
- Hyphenation is off. The "words the open version adds" notice is not shown when it only contains citation numbers.
- segment.py, mineru_backend.py: a drop cap that MinerU drops is restored (the second paragraph of Ioannidis began "ublished"), and in the pdfplumber path a drop cap no longer scrambles the lines of a row.
- method.md: Chinese notes keep English terms, model and method names (PPV, reward model, policy); a term appears once as 中文（English） at first mention if it has a common Chinese rendering, then in one form.

Third round, after the author compared four layouts side by side. The feedback: the margin mixed title, steps and terms together; the reading column was too narrow; with everything open the notes and the original still looked alike; and the steps only named what happens ("Eq. 3 has a closed-form solution Eq. 4") without saying why.

- Left margin: three light boxes, "Part n" with the title and claim, "This part's structure" with numbered steps (the current step's number turns the accent colour), and "Terms". Steps and terms wrap in full instead of being cut off with an ellipsis.
- Width: the reading column takes the rest of the row next to the margin.
- Everything the guide writes ("read for" prompts, summaries, skim restatements, opened formula explanations, recall answers, skip lines) sits on a pale tinted block with a 3px accent bar and a small label. The paper's text stays plain.
- method.md section 10: a flow step is one sentence (about 45 Chinese characters or 25 English words) that says what the step claims, why it follows and how it leads on; it defines its symbols where they first appear, never leans on a bare equation number, gives numbers their setting, and covers every item when the paper enumerates them.

Rules and checks.

- method.md section 9a, plain wording: no denial before the statement, no dash as connector, "is" instead of "serves as", no closing line that only sums up, no lists padded to three, no inflating words. check.py warns on the first four patterns in every field the agent writes (anchors excluded).
- check.py: decimal section numbers ("Section 3.2", "3.2.1", "第3.2节") are not data in the number check.
- render.py: a bilingual `meta` title, author or source follows the language switch; the HTML title uses the default language. A bilingual `def` term gives one glossary entry per spelling, so hover definitions work in both languages.
- render.py: open-version images must be embedded (`data:` URIs or local files); any other URL is dropped, so the page never fetches anything.
- check.py: a backspace or form feed in any text is still an error. A tab, newline or return before a lowercase letter is now only a warning, and only inside a `tex` field or a `$...$` span, so ordinary line breaks in formulas and notes no longer stop the render.
- SKILL.md asks for schema.md to be read before any guide data is written.
- Inline maths set as text falls back to KaTeX when a `\mathrm{...}` argument holds `^`, `_` or braces.

Close reads and segmentation.

- Close-read paragraphs now carry `note` next to `read`. `read` stays a one-line prompt with no spoilers; `note` restates the paragraph under the same rules as a skim note (the claim, the numbers, the qualification). It is meant to be shown below the original, folded, so the original is still read first and a reader who only has the page still gets the argument.
- check.py: a close entry without `note` is a warning (old guides still pass); a close `note` gets the same checks as a skim note (numbers must be in the source text, warning for notes that describe instead of restate).
- method.md, schema.md, SKILL.md describe the new field. render.py already passed `note` through for every tier.
- segment.py: old PDFs whose text layer leaves a space after a ligature ("signifi cant", "fi eld", "confl icts") are rejoined before paragraphs.json is written, in both engines. It only acts when the document shows at least two bare ligature fragments ("fi nding", "fl ow"), leaves a split alone when the tail is a word used elsewhere in the text, and never joins a capitalised word in mid-sentence, so "Sufi music" stays as written. Prompted by the Ioannidis (2005) sample, about 200 splits.
- A restored drop cap goes after any opening quote or bracket: "ublished becomes "Published.

## 0.6.1 (2026-10-26)

Fixes before the first public release.

- render.py: the page no longer embeds the absolute path of the PDF (it showed the local folder structure to anyone the page was shared with). Pass `--pdf` when re-rendering a page recovered with `--dump`, to get page images again.
- All scripts print UTF-8 whatever the console encoding; segment.py no longer stops with UnicodeEncodeError on an English Windows console (cp1252).
- assets/katex/LICENSE holds the KaTeX MIT licence text, and inlined KaTeX carries a one-line version and licence comment.
- mineru_backend.py: MinerU's output is read as UTF-8 (the child process is told to write UTF-8), so a Chinese Windows console (GBK) no longer raises UnicodeDecodeError in the reader thread.
- SKILL.md description is under 200 characters and says when to use the skill (a reading plus a request for a guide, close reading or study help).
- requirements.txt lists Pillow; the README install line adds beautifulsoup4, needed only for open versions (arXiv). THIRD_PARTY_NOTICES.md covers MinerU and the test data, and no longer mentions files that are not in the repository.
- README: check.py's errors and warnings are listed as they are; the MinerU measurements say the reading set is not distributed.
- Tests: file reads and writes name their encoding; the MinerU fixture text is from a CC BY paper (Ioannidis 2005).
- check.py: a backspace or form feed in any guide text, or a tab, newline or return followed by a lowercase letter in a `tex` field or a text with `$`, is an error. It means JSON ate a LaTeX backslash (`\beta` written with one backslash becomes a backspace and `eta`); write `\\beta` in the JSON.

## 0.6.0 (2026-10-15)

Prompted by a JSTOR scan of an economics article read for its core claims in two languages: mathematical notation written as plain text looked wrong, and the MinerU converter mishandled three things on the scan.

- Inline mathematics: any text field (notes, read lines, claims, explanations, recall) may hold LaTeX between single dollar signs, rendered inline by KaTeX; a span starting with a digit is money unless it holds LaTeX, operators or no spaces. check.py treats sub- and superscripts inside such spans as notation. Rule in method.md section 5 and schema.md.
- mineru_backend.py: a doc_title at the top of a page followed by a volume line is the journal masthead, not the title; the title then comes from the running head that is not the journal name. A numbered text block at the foot of a page is a footnote. A page's first text block that starts in lower case continues the previous page's open paragraph.
- render.py: captions and mentions numbered in Roman (TABLE II, Figure IV) resolve like Arabic ones, so a table crop reaches the paragraph that first cites it; a paragraph that is only an equation label, "(2a)", is not a crop host. mineru_backend.py turns such a label into a fragment.
- segment.py: superscript digits ("given by²") count as footnote markers; the period after a footnote number is stripped.

## 0.5.1 (2026-10-15)

Five small findings from the 0.4.0 code review, each with a regression test that failed first.

- check.py: `\\` before a brace is a line break, not an escaped brace, so `\\{` no longer trips the brace check; numbers inside `tex` must appear in the source text (warning, with sub- and superscripts treated as notation).
- mineru_backend.py: a heading block with `level: null` no longer crashes the converter.
- render.py: crops are re-encoded as optimised grayscale PNG before embedding (20 to 30% smaller pages).
- check.py: "inequality (8)", "expression (15)", "Definition 1", "Lemma 2", "Theorem 3", "Corollary 4" and their Chinese forms are references, not data (an economics article cited its inequalities by number).
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

Prompted by a JSTOR scan of an economics article: its MediaBox starts at y=40, pdfplumber reports every coordinate in that offset frame, so the running heads fell outside the margin band and became headings; the display equation was lost as a fragment, a Roman-numbered experiment label was changed to Arabic numbering, and the previous run had to rebuild the text by hand and lost the page images.

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
- License the original project code under MIT; add dependency and source-licence notices. Refresh English and Chinese installation/known-issue documentation.

## 0.3.1 (2026-10-07)

Prompted by testing before the first release. Both fixes have regression tests that failed before implementation.

- check.py: a relation without a `to` target now reports validation errors instead of crashing while formatting the path to the conclusion.
- common.py: skip malformed element definitions with nonnumeric levels, as already done for malformed field counts.

## 0.3.0 (2026-10-07)

Prompted by a guide to a behavioural-economics review article: the argument map was sectioned well but did not show how the parts connect.

- Logic map: the conclusion at the top; parts linked by typed relations (supports, explains, qualifies, extends, frames, challenges, answers); clicking a part shows its reasoning steps, each linked to its paragraph. Narrow screens get a list with each relation written out. Guides without relations still get the part grid.
- Guide data: parts gain `rel` and `flow` (method.md section 10, schema.md).
- check.py: relation and step types are checked, every part must lead to the conclusion without cycles, steps must lie inside their part, and numbers in labels and steps must appear in the source.
- render.py `--dump` keeps relations and steps.

## 0.2.1 (2026-10-07)

- Author headings now render by level, so a level-1 heading such as an introduction outranks the guide's part headers beneath it. Prompted by a guide to a behavioural-economics review article where an introduction heading looked smaller than the part title under it: the template had drawn every author heading in one small grey style.
- Segmentation: heading sizes that differ by less than 8% count as one level, so OCR size noise cannot split same-rank headings into different levels.

## 0.2.0 (2026-10-06)

Prompted by a behavioural-economics review article, guided once with Claude and once with GPT. Neither model's notes were full enough to let the reader skip a paragraph; the structure mirrored the author's headings; and the two runs numbered paragraphs differently, because both rewrote the segmentation by hand after the script failed on a JSTOR scan.

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
