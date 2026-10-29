# Changelog

Add an entry at the top for every change to the rules or the workflow: version, date, what changed, and what prompted it (which reading, what went wrong).

## 0.7.1 (2026-10-28)

- Every new batch of papers still showed segmentation errors that misled the reader, and each fix added another rule to segment.py. The agent now looks at the pages before writing: `fix.py overlay` draws each item's box and id on the page image, and the agent writes `fixes.json` (retype, join, split, move, or rebuild an item from a box on the page with the PDF's own words), which `fix.py apply` replays from the original split. SKILL.md has a new step 1b for this. The basic tier no longer crashes on a page where a column cut leaves every line on one side.
- More unseen papers exposed overprinted letters and metadata, table notes and equations mixed with prose. Titles, abstracts, quotations and paragraph continuations now stay together more reliably; unrecoverable Symbol-font characters remain visible as placeholders. A full trial with MinerU installed showed the MinerU tier splitting a citation at a page break and keeping first-page metadata as paragraphs; both now follow the basic tier, and a paragraph that ends inside a bracket continues only when the next block closes it. SKILL.md says MinerU prints no self-check line, and schema.md states the thesis and claim length limits.
- A full guide trial on a monetary-theory paper found roles copied from another guide, a model result stated without its model, and a reply to a named critic left as skim. method.md now says to write every entry from the paragraph in hand, to keep a result's model conditions and mark what the authors only assert, and to close-read paragraphs that correct another author or state a result derived from a formula.

- Further unseen papers exposed page-edge citations mistaken for headers, reference entries released by contact footers, and duplicated text layers. Covers, titles, bylines, inset quotations and OCR word breaks and equations now keep their place more reliably.

- A full guide run exposed split ligature words and a paragraph stranded after a figure. Touching fallback-font ligatures now stay inside their words; plot titles no longer block the paragraph join. Missing-symbol warnings keep their source positions and exclude covered display ink and proven nonprinting marks.

The skill is now named `literature-guide-read`, the same as the repository, and the basic tier reads three-column pages. Prompted by a first-time-user trial of 0.7.0 on Ioannidis (2005): the basic tier mixed its three columns, put the references into the body and said nothing, and the agent had to extract the text by hand. Two economics readings the author tried next, an AEJ: Applied paper and a QJE paper, failed in the basic tier for other reasons, before and after the three-column work.

- Name: `SKILL.md` `name`, the install paths in both READMEs, the release zip (`literature-guide-read.zip`, top-level folder `literature-guide-read`), the page footer and the licence holder use the new name. If you installed 0.7.0, remove the `reading-guide` folder and install again.
- Columns: the basic tier finds the columns of every page (`--columns auto|1|2|3`) and reads three-column pages column by column, with full-width titles, boxes and tables in place.
- Self-check: after segmenting, `segment.py` scores the split (lower-case starts, open endings, lines that jump between columns, references among the paragraphs, notes in the upper half of a page). In `auto` a bad split is retried with 1, 2 and 3 columns and the best is kept; if all are bad, it prints the next step for the agent. SKILL.md step 1 lists the recovery steps the agent runs itself, never the user, and documents the `--text` format and that `--pdf` belongs to render.py.
- Joins: a paragraph cut at a column or page break is joined again, in both tiers.
- Basic-tier fixes found on the three papers: text placed outside the page is ignored; glyph boxes set off their baseline are levelled, so brackets in a math font no longer split sentences; words that touch across a font change are joined (small-caps headings, bracketed words) and spacing accents are composed; the title is the largest type on page 1 and never a masthead or a label above it; tables drawn only with horizontal rules are found and their cells kept out of paragraphs and footnotes; table notes, pull quotes and small annotations become fragments; a small-type "References" heading still ends the body.
- Found in a full guide run on an AEJ: Applied paper: small-caps subheadings whose capitals were lost in extraction ("C. industry comparisons") are headings when they stand centred; a hyphen at a line end is kept or dropped from what the document itself shows (a compound before the break, number words, the hyphenated form elsewhere, or the closed form elsewhere), so "low-cost" and "state-of-the-art" survive and "refer-ence" does not keep its hyphen.
- Tried next on a further set of economics and psychology papers and a book chapter. A blank page no longer stops the run. The basic tier no longer runs OCR: a scanned PDF needs MinerU, and the agent offers it with its gains and costs. Side boxes no longer break the body columns; a joined paragraph no longer swallows the next one or a table; text layers stretched past the page are scaled back; references and captions set in spaced capitals are found; lists keep their items; run-in, question and lower-case headings and multi-line chapter titles are found; text in boxes stays readable; captions stop at the paragraph gap; titles keep their colon and drop the masthead. The self-check now notices pages left in fragments and no longer flags endnote pages or numbered subsections. Tables without rules, contents pages, publisher cover sheets and the metadata column beside an abstract stay out of the text, and the authors stay visible under the title. Font styles are read with fonttools when it is installed.
- A first batch of papers the skill had not seen: minus signs and other symbols drawn with unmapped glyphs are recovered from the embedded font, and any that cannot be recovered stay marked so check.py warns; spacing in old OCR text layers is repaired; small unmarked notes at the page foot stay out of the body; a paragraph ending without a full stop is joined to the next page only when the line widths and indents show it continues; a cover title set as an image is reported so the agent can use MinerU.
- A further batch of unseen papers: figures, tables and their notes are separated before the body is ordered; prose continues around them without taking in chart labels or captions. Reference lists stop before later exhibits and appendices. Spacing, overprinted lines, article titles after cover sheets and short headings are handled more reliably; MinerU no longer repeats figure captions or turns a sentence continued on the next page into a heading.
- More unseen papers and a full guide check: body lines stay out of the outline; bold run-in labels stay with their paragraph; wrapped and centred headings and captions stay together, and captions stop before the table's header row; bylines stay visible after covers; columns and pull quotes keep their reading order, and side-by-side captions read left to right. Footnote marks before punctuation link correctly; displayed equations are cut out as images, including ones whose symbol font decodes wrongly; bullets and symbols in the Symbol font are read through Adobe's published table; repeated logos are not page numbers. The checker warns when a reasoning step copies its paragraph note.
- Reading rules, from a full guide run checked against the paper: before check.py the agent rereads every claim, step and note beside its paragraph for the direction of each result and the author's hedges and sample limits, and marks results the authors report without showing; identification, main results and the relevant robustness checks are close reads; a reader new to the field gets a definition for every term the argument needs, starting with the terms the question turns on; each part has at least one why or how recall question; a flow step gives the move without restating the note. After a second run: every number names its table, sample and specification; comparisons across samples or methods say so; when robustness checks shrink an estimate the range is given; a result that is not significant is called that; the notes say what the identification assumes and what the authors offer for it; a fact reads the same in every field. After a third run: a comparison also says when the shock or denominator changes, ranges from several methods are compared within one method, a number names the group it covers when the authors' label is broader, and the role and read length limits are stated where the fields are described. After a fourth run, on a paper that argues with another school: the overview and flow steps are checked for hedges with the other short fields, and a criticism keeps its object; the thesis says where the authors agree with the other side as well as where they disagree; a recall answer gives the reason for the question asked; a technical term in the thesis or a part claim gets a few-word gloss there. check.py accepts "20 世纪 60 年代" and "20th century" when the source has a year from that decade or century.
- check.py: numbers a text layer sets apart ("1 0" for 10) and numbers the source spells out ("forty-eight", "twenty-fifth") are accepted in digits, still rejecting any number the source lacks; check.py accepts dates written with month numbers when the source spells the month; the "tab/newline inside maths" warning no longer fires on money next to inline maths.
- Step 0 offers MinerU when it is not installed, with what it gains and costs, and the agent installs it on a yes. `questions` may be an empty list.
- README in English and Chinese rewritten around what the page does for the reader, with the two extraction tiers in a table and the fields the skill was developed on.

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
- License the original project code under MIT; add dependency and source-licence notices. Refresh English and Chinese installation/known-issue documentation.

## 0.3.1 (2026-10-07)

Prompted by testing before the first release. Both fixes have regression tests that failed before implementation.

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
