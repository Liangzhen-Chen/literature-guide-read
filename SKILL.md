---
name: reading-guide
description: Guided reading for course PDFs in English or Chinese. Maps the argument, sorts paragraphs into close/skim/skip, highlights key elements, and builds an HTML reading page. 导读、精读。
---

# Reading guide

Builds a reading page for one reading (a PDF or plain text). The page helps the reader read the original; it does not replace it:

- a logic map at the top, for readers short on time: the conclusion, each part linked to it by a typed relation, and the reasoning steps inside each part;
- the original text in order, with close-read paragraphs open under a one-line "read for" prompt;
- skim and skip paragraphs led by a note that restates them, with the original one click away;
- definitions, claims, evidence, figures, formulas and qualifications highlighted inside the original;
- a sidebar with what each paragraph does, a list of terms and a list of evidence;
- figures and tables shown on the paragraph that first cites them, with the whole PDF page one click away.

Read `references/method.md` and `references/elements.md` before writing any guide data.

`SKILL_DIR` is the folder holding this file. `WORK` is any writable folder, such as `./guide-<slug>/`. `OUT` is where the user collects files: `/mnt/user-data/outputs/` on claude.ai, otherwise `WORK`. Requirements are in `requirements.txt`: Python 3.9+ and pdfplumber; scanned PDFs also need tesseract (eng, chi_sim for Chinese) and poppler; open versions need network access and beautifulsoup4.

## Language

- Write the notes in the user's language, Chinese or English. Write both only when the user asks, and list them in `meta.notes_lang` (the first one is the default; the page then offers a language switch).
- Never translate or edit the original text. Anchors are copied from it verbatim.

## Workflow

0. **Brief the reader first.** Before writing anything, ask one round of questions in the user's language, numbered, each with a recommended answer so that "yes" accepts it (the grill-me format). Required: the language of the notes; what they are reading for (whole argument / core claims only / method and design only / evidence to cite / exam revision / something else). Optional: how familiar they are with the field and this text; questions they want answered or things they are curious about. Segmentation can run while you wait; do not write guide data before the answers. If the user says "you decide", use whole argument, medium density, and say so. Record the answers in `meta.purpose`, `meta.familiarity` and `questions` (schema.md); the purpose changes which paragraphs are close reads (method.md section 3a).
1. **Segment.** `python SKILL_DIR/scripts/segment.py <file> --out WORK`
   Read the printed counts, then spot-check the first and last `WORK/paragraphs_partNN.txt` for merged columns, running heads in the text, or paragraphs cut in two. Options: `--pages 3-28` to skip a cover or contents; `--columns 1` or `2`; `--ocr on --lang eng+chi_sim` for scans; `--engine mineru` to force the optional MinerU layout engine (used automatically when it is installed; see requirements.txt); `--text` for plain text (blank lines between paragraphs, `#` headings, a line `[[p.12]]` marks page 12). Do not re-segment once you have started writing: it renumbers everything.
   **If the counts look wrong** (more than two headings per page, more fragments than paragraphs, running heads inside paragraphs): re-run with `--columns 1` or `--pages`, or install MinerU and re-run. Fall back to `--text` only as a last resort, and then pass `--pdf <file>` to render.py so page images survive.
   `WORK/crops/` holds a PNG for every display equation and table region. Open the ones for formulas you will tag and transcribe them into `tex` (LaTeX, no `$`); when the engine already supplied `tex` (MinerU with its formula model, or an open version), check it against the crop.
2. **Open version (optional).** `python SKILL_DIR/scripts/sources.py detect WORK/paragraphs.json`. If it finds an arXiv id, run `sources.py fetch <id> --out WORK`, then the `parse` or `parse-tex` command it prints. If the network is blocked, say so in one line and carry on without it. The PDF stays the source of the text and the page numbers; the open version only adds figures, tables, formulas and a report of words the PDF's text layer dropped.
3. **Read.** Read every part file in full. Use `references/genres.md` to set the genre.
4. **Write the guide.** Format in `references/schema.md`: `WORK/guide.json` with meta, thesis, overview and parts (each part with its claim, its relations `rel` and its reasoning steps `flow`, see method.md section 10), and `WORK/paras_01.json`, `paras_02.json`, ... with about 40 paragraph entries each.
5. **Check.** `python SKILL_DIR/scripts/check.py WORK/paragraphs.json WORK/guide.json WORK/paras_*.json`
   Fix every error. Judge each warning: change it or have a reason. When an anchor is not found, copy from the closest sentence the checker prints. When a number is not in the source, use the author's figure or wording.
6. **Render.** `python SKILL_DIR/scripts/render.py WORK/paragraphs.json WORK/guide.json WORK/paras_*.json --out OUT/<slug>-guide.html` (add `--sources WORK/sources.json` if step 2 produced it). Deliver the page the way the environment delivers web pages: publish it as a link if you can, otherwise give the file. The page is a single offline HTML file.

In the chat reply, give the thesis in one sentence, the answers to the reader's questions with their paragraph ids, the close-read paragraphs grouped by part (with ranges and pages), and the page. Do not repeat the whole map.

## Rules that must hold

- Every paragraph has an entry; parts cover all paragraphs in order.
- Skim notes restate the content, with its numbers, definitions and conclusion; they never just say what the paragraph does.
- Close-read paragraphs get a "read for" line, not a summary.
- Anchors are verbatim. Every number in the guide appears in the source.
- Keep close reads within `meta.density` (low, medium, high: 15%, 25%, 40%).
- Do not grade the authors or add information the text does not contain.
- A paragraph that introduces a formula the argument relies on is a close read; its formula element carries `tex`, `syms` and `x`, checked against the crop.
- Every part that is not skipped carries two or three `recall` questions answerable from the part; every reader question in `questions` names the paragraphs that answer it.

## While the user reads

- Questions about a paragraph ("what is P23 saying?"): point to the original first, then explain, and keep what the author says apart from your explanation.
- Corrections to a tier, a note or a highlight: edit the data, run check and render again, and update the same page.
- "Walk me through it": go part by part. State what the part must establish and what to watch for in its close reads, then wait until the user has read it.
- The working folder may not survive. To recover the data from a page: `python SKILL_DIR/scripts/render.py --dump OUT/<slug>-guide.html --out WORK`; afterwards pass only `paragraphs.json` and `guide.json`.

## Improving this skill

The rules are expected to change with use.

- Separate two kinds of feedback. About one reading ("P12 should be a close read"): fix that reading's data. About the method ("thought experiments should be close reads"): note it as a candidate rule and list it in the reply.
- When the user says they have finished a reading, ask once which close reads were wrong or missing.
- When the user asks to update the skill:
  1. Restate the rule change and wait for confirmation.
  2. `SKILL_DIR` may be read-only: copy it to a writable folder. Put method changes in `references/method.md`, genre rules in `genres.md`, element types in `elements.md`, workflow changes in this file, segmentation fixes in `scripts/segment.py`, extraction engines in `scripts/mineru_backend.py`.
  3. Add an entry at the top of `CHANGELOG.md`: version, date, what changed, and what prompted it (which reading, what went wrong). Rule changes bump the second number.
  4. Zip the folder (`zip -r reading-guide.zip reading-guide -x '*/__pycache__/*'`) and hand it over; README.md explains how each tool replaces the old version.
- Do not change the method halfway through a reading.
