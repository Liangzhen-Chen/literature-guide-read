# reading-guide

A reading companion for course readings in English or Chinese. Give it a PDF and it builds one HTML page in which you read the original:

- a **logic map** at the top: the conclusion, each part of the argument linked to it by a typed relation (supports, explains, qualifies, extends, ...), and, for any part you click, the reasoning steps inside it;
- the **original text** in order: close-read paragraphs open under a one-line "read for" prompt; skim and skip paragraphs led by a note that restates them, with the original one click away;
- **highlights inside the original** for definitions, claims, evidence, figures, formulas and qualifications;
- a **sidebar** with what each paragraph does, the terms, and the evidence;
- **figures and tables** on the paragraph that first cites them, with the whole PDF page one click away;
- a **brief** before writing: language, purpose, familiarity and the reader's own questions, answered from the text with links;
- **recall questions** at the end of each part, a **gist** view, hover definitions for terms and symbols, and a "guess the relations" mode on the map;
- notes in Chinese, English, or both with a switch.

The folder follows the open Agent Skills format (`SKILL.md` plus scripts and references), so it is not tied to one AI tool. The scripts are ordinary Python command-line programs; the page is a single offline HTML file.

## Three ways to use it

**1. In a tool that supports Agent Skills.** Put the whole `reading-guide` folder in the tool's skills folder, then upload a PDF and ask for a reading guide.

- claude.ai: upload the folder through the Skills control if your account has one; otherwise use the manual workflow below.
- Claude Code: place the folder at `~/.claude/skills/reading-guide/`.
- Other tools that support Agent Skills: use the tool's skills folder; locations differ, see its documentation.

**2. In an agent that can run commands but has no skill support.** Ask it to read `SKILL.md` and follow it.

**3. By hand, with any chat model.** Run the scripts yourself; the model only writes the guide data.

```
pip install -r requirements.txt
python scripts/segment.py reading.pdf --out work
```

Give the model the files in `references/` and `work/paragraphs_part*.txt`, with this prompt:

> Write guide data for this reading. The rules are in method.md, elements.md and genres.md; the format is in schema.md. The text is already split into numbered paragraphs: use those ids and do not re-split. Read every paragraph first, then follow method.md. Write the notes in [Chinese/English]. Output only two JSON blocks, saved as guide.json and paras_01.json. Copy every anchor verbatim from the original.

Save the two blocks into `work/`, then:

```
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
python scripts/render.py work/paragraphs.json work/guide.json work/paras_01.json --out work/guide.html
```

If check.py reports errors, paste them back to the model and ask it to fix them.

## Pipeline

1. `segment.py` splits the PDF into fixed paragraph ids (P1, P2, ...), recognises headings, captions and footnotes, removes running heads and download watermarks, records printed page numbers, and links each footnote to the paragraph that cites it. It handles two-column layouts and scans (OCR), and Chinese headings and footnotes.
2. `sources.py` (optional) looks for an arXiv id or DOI, fetches the arXiv HTML version (falling back to the TeX source), and extracts figures, tables and display formulas. It also reports words that the PDF's text layer dropped. The PDF stays the source of the text and the page numbers.
3. The model reads everything and writes the guide data: parts and claims; per paragraph a tier, a role, a note or a "read for" line, and elements anchored to verbatim spans.
4. `check.py` checks that every paragraph has an entry, parts cover the text in order, anchors exist verbatim, every number in the guide appears in the source, close reads stay within the density cap, and notes restate rather than describe.
5. `render.py` builds the page, attaches figures to the paragraphs that cite them, and embeds whole-page images for pages with figures or tables.

## Extraction tiers

The default needs only pdfplumber. Installing MinerU (`pip install "mineru>=4,<5"`, then `mineru-kit models download --tier basic`, about 0.8 GB; CPU is fine) makes `segment.py` use its layout analysis automatically: running heads removed, tables as structure, display formulas located and, when its formula model is installed, transcribed to LaTeX. Without the formula model (delete or skip `models/MinerU-4_models_onnx/MFR`, saving 577 MB) formulas come out as cropped images that the reading model transcribes; that run is 40% to 75% faster on CPU. Set `MINERU_PYTHON` if MinerU lives in another interpreter.

Measured on 11 readings (seven real publications, scans and a textbook chapter): on independently reviewed pages MinerU ties or beats the default on 7 of 8, removes all 30 running heads the default used to turn into headings on a JSTOR scan, and turns about 800 loose table rows into 111 tables. The default remains the only option on claude.ai, where the sandbox cannot download models; scans and formula-heavy readings do better in a local agent.

Either way, `segment.py` crops every display equation and table region to `WORK/crops/`, and the page shows the crop beside the KaTeX-rendered transcription and its symbol table.

## Files

| File | What it holds | Edit it when |
| --- | --- | --- |
| `SKILL.md` | the workflow and the rules the agent must keep | the workflow changes |
| `references/method.md` | the method: parts, tiers, notes, elements, numbers, language | refining the method (most edits go here) |
| `references/elements.md` | element types; check.py and the page read them from here | adding or renaming types |
| `references/genres.md` | adjustments by genre | a new genre comes up |
| `references/schema.md` | the guide data format with examples | rarely |
| `scripts/segment.py` | segmentation | segmentation goes wrong |
| `scripts/mineru_backend.py` | the optional MinerU engine and the rules applied to its output | MinerU output needs a new rule |
| `scripts/crops.py` | crops of formula and table regions | crop sizing changes |
| `scripts/sources.py` | open versions | open-version handling changes |
| `scripts/check.py` | validation | adding a check |
| `scripts/render.py` | page assembly; `--dump` recovers data from a page | rarely |
| `assets/template.html` | the page | changing the page |
| `CHANGELOG.md` | every change and what prompted it | every change |

## Open versions and the network

Open versions help most for arXiv papers, which have HTML versions generated from their LaTeX. Most journal articles and book chapters have no structured open version, so the PDF path has to work on its own. On claude.ai the code sandbox can only reach listed domains and arxiv.org is not among them by default; an organisation owner can add it, or the step can run in a local agent.

## Verified environments

- Python 3.9 and 3.12 (the unit suite runs on both); pdfplumber only for the default tier.
- Scans: Tesseract with `eng` and `chi_sim`, plus Poppler. If Tesseract stalls on some pages, set `OMP_THREAD_LIMIT=1`.
- Optional MinerU 4.x on CPU (see Extraction tiers).
- Pages were checked in Chromium, WebKit and Firefox; they are single offline HTML files.
- claude.ai: the default tier only (the sandbox cannot download models). Local agents such as Claude Code or Codex can use MinerU.

Every change to the scripts is covered by a regression test that failed before the fix; the method rules are tuned on real readings and recorded in CHANGELOG.md.

## Known issues


- Segmentation remains imperfect for equations, tables, metadata and unusual layouts. The independently reviewed scopes do not meet every target in the plan. Spot-check extraction before writing guide data, then freeze the paragraph ids.
- Crowded logic maps automatically use a relation list to keep all labels readable; sparse maps retain their graph.
- Inline formulas inside prose stay as the PDF text layer gives them unless MinerU's formula model is installed; the original paragraph is never edited. Display formulas are shown as a PDF crop beside the transcription, so a garbled text layer no longer hides them.
- Multi-panel open-version figures currently embed only their first graphic. TeX graphics supplied as PDFs are not converted automatically. Existing caption-extraction omissions can prevent a figure card from being created.
- Rendering a 64-page chapter takes a few seconds; `--no-page-images` removes PDF page viewing and reduces file size.
- `--dump` supports current guide pages; legacy v0.1 sample pages use an incompatible data schema.
- Hosted model agreement and English/Chinese NotebookLM comparisons are recorded in the test reports. They are agent assessments, not measurements of student comprehension. Claude CLI authentication and ThesisGlow trial access remained unavailable. Zero OCR gap reports do not prove that no words were missed.

## Sharing pages

A page embeds the full text of the PDF it was built from. Keep pages made from copyrighted readings to yourself, and use openly licensed papers for public demos.
