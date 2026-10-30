English | [中文](README.zh.md)

# literature-guide-read

**It reads the whole paper first, then tells you which paragraphs to read closely, which to skim and which you can skip.**

An agent skill for papers and course readings. Give the agent a PDF and you get one offline web page built around the original text, with notes in English, Chinese or both. It works in Claude Code, Codex, claude.ai and other agents that support [Agent Skills](https://agentskills.io).

The page holds the full original text, and you read it yourself. The guide points out where your time is best spent and what to look for, and afterwards the summaries and recall questions show you how much you took in.

Open a finished page: [Ioannidis (2005), notes in English and Chinese](https://liangzhen-chen.github.io/literature-guide-read/), or [the DPO paper (2023), notes in Chinese](https://liangzhen-chen.github.io/literature-guide-read/dpo.html). Both papers are openly licensed: [Ioannidis](https://doi.org/10.1371/journal.pmed.0020124) (CC BY) and [Rafailov et al.](https://arxiv.org/abs/2305.18290) (CC BY 4.0).

![A reading page in use: the conclusion and argument map, a jump to one part, a close read with its formula and opened summary, a step in the margin, the summaries-only view and the notes switched to Chinese](assets/readme/demo.gif)

## What's on the page

- Every paragraph marked **close read, skim or skip**. A close read keeps its full text with a line on what to look for; a skim opens with a short restatement; a skip folds to one line. When time is short, switch to summaries only.
- The paper's **conclusion in one sentence** at the top, with a mind map of how the parts lead to it.
- A **left margin that follows you**, showing the current part's claim, its reasoning in numbered steps and the terms it introduces. Click a step to jump to that paragraph.
- The **original text, unchanged**. Everything the guide wrote sits in its own tinted box.
- **Key formulas** rendered and explained, with a table of symbols and the crop from the PDF.
- A **summary to open** after each close read, to check what you took from it, and **recall questions** at the end of each part.
- **Answers to the questions** you gave the agent at the start, taken from the text and linked to the paragraphs.
- Notes **checked against the paper** before the page is built. Numbers and highlights are checked first. A separate agent then reads the guide against the paper and its tables, looking for dropped hedges, overstated results and wrong signs; where the environment cannot start another agent, the writer rereads field by field. The writer fixes the findings before rendering. This adds to the usage of each paper.
- The agent **looks at the pages** before writing: it draws each paragraph's box on the page image and corrects front matter, captions, table notes and broken paragraphs that the text extraction got wrong.

![A part of the DPO paper with Chinese notes: the margin holds the part's claim, steps and terms; on the right a close-read paragraph with its read-for prompt, the rendered formula and the opened after-reading summary](assets/readme/page-formula.png)

## Install

<details open>
<summary><b>Claude Code</b></summary>

```bash
git clone https://github.com/Liangzhen-Chen/literature-guide-read ~/.claude/skills/literature-guide-read
pip install -r ~/.claude/skills/literature-guide-read/requirements.txt
```
</details>

<details>
<summary><b>Codex</b></summary>

```bash
git clone https://github.com/Liangzhen-Chen/literature-guide-read ~/.codex/skills/literature-guide-read
pip install -r ~/.codex/skills/literature-guide-read/requirements.txt
```
</details>

<details>
<summary><b>Any agent that supports Agent Skills (Cursor, Copilot, Gemini CLI, …)</b></summary>

```bash
npx skills@latest add Liangzhen-Chen/literature-guide-read
pip install pdfplumber fonttools pillow beautifulsoup4
```

The installer asks which agents to install to; add `-g` to install for your user instead of the current project.
</details>

<details>
<summary><b>claude.ai</b></summary>

Download `literature-guide-read.zip` from the [latest release](https://github.com/Liangzhen-Chen/literature-guide-read/releases/latest) and upload it under Settings, Capabilities, Skills. Scanned PDFs cannot be read on claude.ai; they need a local agent with MinerU. Formula-heavy papers also come out better locally.
</details>

<details>
<summary><b>By hand, with any chat model</b></summary>

Run the scripts yourself; the model only writes the guide data.

```bash
pip install -r requirements.txt
python scripts/segment.py reading.pdf --out work
```

Before writing, inspect page 1, the last body page and any pages named by the self-check or with odd part text. Render their boxes and IDs (this example starts with page 1):

```bash
python scripts/fix.py overlay work/paragraphs.json --pages 1
```

Give the model the PDF, these page images, `work/paragraphs.json`, the part files and SKILL.md step 1b. Ask for `work/fixes.json`, an array of explicit corrections (use `[]` when none are needed). Apply it and list the IDs:

```bash
python scripts/fix.py apply work/fixes.json --paras work/paragraphs.json
python scripts/fix.py ids work/paragraphs.json
```

Fixes always use first-segmentation IDs; after an apply, find them with `fix.py overlay work/paragraphs.json --orig` or `paragraphs.orig.json`. Guide data uses the new IDs in paragraphs.json and the rewritten part files.

Give the model the files in `references/` and `work/paragraphs_part*.txt`, with this prompt:

> Write guide data for this reading. The rules are in method.md, elements.md and genres.md; the format is in schema.md. The text is already split into numbered paragraphs: use those ids and do not re-split. Read every paragraph first, then follow method.md. Write the notes in [Chinese/English]. Output only two JSON blocks, saved as guide.json and paras_01.json. Copy every anchor verbatim from the original.

Save the two blocks into `work/`, then check:

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
```

Fix the errors. Open a fresh chat with `references/review.md`, paragraphs.json, the part files, guide files, crops and page images (plus the PDF when a page is missing). Include fixes.json, paragraphs.orig.json and fixes_log.json when present. Ask for the second read, pass its findings to the writer and fix every misleading finding and every minor finding with a clear fix. Then check again and render:

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
python scripts/render.py work/paragraphs.json work/guide.json work/paras_01.json --out work/guide.html
```
</details>

To update, run `git pull` in the skill folder, run the `npx` line again, or upload the new zip on claude.ai.

### Two tiers for reading the PDF

The install above gives you the basic tier. Adding [MinerU](https://github.com/opendatalab/MinerU) gives you the full tier; once it is installed the skill uses it on its own, with nothing to switch. If it is not installed, the agent asks at the start whether you want it, tells you what you gain and what it costs, and installs it for you if you say yes. Only MinerU can read a scanned PDF, so for a scan the agent recommends it.

| | Basic | With MinerU |
| --- | --- | --- |
| Install | included above | `pip install "mineru>=4,<5" && mineru-kit models download --tier basic` (about 0.8 GB, a CPU is enough) |
| Layouts | one, two or three columns | also side columns, wide tables and unusual layouts; tables kept as tables |
| Formulas | cropped from the PDF; the agent transcribes the ones that matter | found more reliably and turned into LaTeX for you |
| Scanned PDFs | cannot read them | reads them (OCR built in) |
| Time to read the PDF | a few seconds | 1 to 3 minutes |
| claude.ai | yes | no (the sandbox cannot download the models) |

In both tiers figures can be shown through page images; when the paper has a web version on arXiv, the authors' own figures are used instead. Rotated-text tables are kept as upright crops in the basic tier.

### Dependencies

| Package | Purpose | What you gain | Cost |
| --- | --- | --- | --- |
| pdfplumber | PDF text and page images | Words, positions and PDF crops | Required for PDF input; reads text layers |
| fonttools | Embedded font metadata and glyphs | Better font styles, case and symbol repairs | Small local Python dependency |
| Pillow | Page overlays and crop editing | Box labels, upright crops and smaller embedded images | Local Python dependency |
| beautifulsoup4 | Open-version HTML | Figures, tables and formulas from arXiv | Used by sources.py; fetching needs network access |
| MinerU (optional) | Layout analysis and OCR | Scans, unusual layouts and formula LaTeX | About 0.8 GB of models; 1 to 3 minutes per paper on CPU in earlier trials |

### Scripts

- `segment.py`: extract and number the text; `crops.py`: write formula and table crops; `mineru_backend.py`: optional MinerU extraction.
- `fix.py overlay/apply/ids`: inspect and correct segmentation; `fix_crops.py`: preserve and rename crops when fixes are applied.
- `sources.py`: fetch and parse open versions; `check.py`: validate guide data; `render.py`: build the offline page or recover its data with `--dump`.

## Use it

1. Give the agent a PDF and say "make me a reading guide for this".
2. It asks a few questions first: notes in English or Chinese, what you are reading for (the whole argument, core claims, method, evidence to cite, exam revision), how well you know the field, and anything you want answered. Say "you decide" to skip them.
3. The agent returns the page after inspection and the second read. Before steps 1b and 5b were added, Claude Sonnet took about 7 minutes and 134,000 tokens for a 6-page paper, and about 10 minutes and 172,000 tokens for a 10-page paper with 11 equations. In trials, the second read used roughly half to three quarters as many tokens again as writing the guide; this is an estimate from trials, and page inspection adds work too.

While you read, ask the agent about any paragraph ("what is P23 saying?"), correct a note, or say "walk me through it" to go part by part. If something keeps going wrong for your kind of reading, tell the agent: the rules it follows are plain text in `references/`, and it can change them.

## Built on reading research

- One sparse highlight style and a summaries-only view, because dense or wrong highlights cost readers' trust ([Scim](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)).
- Definitions on hover, where the term is used ([ScholarPhi](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648)).
- A "guess the relations" switch on the mind map, because argument maps help most when you work them out yourself ([van Gelder](https://www.reasoninglab.com/wp-content/uploads/2013/10/TvG-Using-argument-mapping-to-improve-critical-thinking-skills-2015.pdf)).
- Specific "read for" prompts, recall questions and summaries you open after trying to recall, following the evidence on pre-questions ([meta-analysis](https://link.springer.com/article/10.3758/s13423-023-02353-8)) and retrieval practice ([Dunlosky et al. 2013](https://doi.org/10.1177/1529100612453266)).
- Formula explanations folded, so you try to explain the step yourself first ([self-explanation](https://link.aps.org/doi/10.1103/PhysRevPhysEducRes.18.010136)).

## Known limits

The skill was developed mostly on economics, statistics and machine learning papers. Papers from other fields have been tried less. If something comes out wrong, tell the agent, and please [open an issue](https://github.com/Liangzhen-Chen/literature-guide-read/issues).

Segmentation still makes mistakes; step 1b relies on the agent to spot and correct them. Some PDFs swap or drop math symbols in their text layer, so read symbols from the crops or page images. Figures embedded as images are cropped when a figure or table label sits next to them; vector-drawn figures get a crop only when the agent draws one in step 1b, and otherwise need the full page.

## License

MIT. KaTeX (MIT) is vendored under `assets/katex/`; see `THIRD_PARTY_NOTICES.md`.
