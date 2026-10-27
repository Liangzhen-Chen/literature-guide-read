English | [中文](README.zh.md)

# literature-guide-read

**It reads the whole paper first, then tells you which paragraphs to read closely, which to skim and which you can skip.**

An agent skill for papers and course readings. Give the agent a PDF and you get one offline web page built around the original text, with notes in English, Chinese or both. It works in Claude Code, Codex, claude.ai and other agents that support [Agent Skills](https://agentskills.io).

Open a finished page: [Ioannidis (2005), notes in English and Chinese](https://liangzhen-chen.github.io/literature-guide-read/), or [the DPO paper (2023), notes in Chinese](https://liangzhen-chen.github.io/literature-guide-read/dpo.html).

![The top of a reading page: title, conclusion and the mind map](assets/readme/page-top.png)

## What's on the page

- Every paragraph marked **close read, skim or skip**. A close read keeps its full text with a line on what to look for; a skim opens with a short restatement; a skip folds to one line. When time is short, switch to summaries only.
- The paper's **conclusion in one sentence** at the top, with a mind map of how the parts lead to it.
- A **left margin that follows you**, showing the current part's claim, its reasoning in numbered steps and the terms it introduces. Click a step to jump to that paragraph.
- The **original text, unchanged**. Everything the guide wrote sits in its own tinted box.
- **Key formulas** rendered and explained, with a table of symbols and the crop from the PDF.
- A **summary to open** after each close read, to check what you took from it, and **recall questions** at the end of each part.
- **Answers to the questions** you gave the agent at the start, taken from the text and linked to the paragraphs.
- Notes **checked against the paper** before the page is built. A number the paper doesn't contain, or a highlight that doesn't match the original word for word, has to be fixed first.

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
pip install pdfplumber beautifulsoup4
```

The installer asks which agents to install to; add `-g` to install for your user instead of the current project.
</details>

<details>
<summary><b>claude.ai</b></summary>

Download `literature-guide-read.zip` from the [latest release](https://github.com/Liangzhen-Chen/literature-guide-read/releases/latest) and upload it under Settings, Capabilities, Skills. Scans and formula-heavy papers come out better in a local agent.
</details>

<details>
<summary><b>By hand, with any chat model</b></summary>

Run the scripts yourself; the model only writes the guide data.

```bash
pip install -r requirements.txt
python scripts/segment.py reading.pdf --out work
```

Give the model the files in `references/` and `work/paragraphs_part*.txt`, with this prompt:

> Write guide data for this reading. The rules are in method.md, elements.md and genres.md; the format is in schema.md. The text is already split into numbered paragraphs: use those ids and do not re-split. Read every paragraph first, then follow method.md. Write the notes in [Chinese/English]. Output only two JSON blocks, saved as guide.json and paras_01.json. Copy every anchor verbatim from the original.

Save the two blocks into `work/`, then:

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
python scripts/render.py work/paragraphs.json work/guide.json work/paras_01.json --out work/guide.html
```

If `check.py` reports errors, paste them back to the model and ask it to fix them.
</details>

<details>
<summary><b>Optional: scanned PDFs, three-column layouts, many formulas</b></summary>

Scans need Tesseract (`eng`, `chi_sim`) and Poppler. Three-column layouts and formula-heavy papers do better with [MinerU](https://github.com/opendatalab/MinerU), which the skill uses automatically once installed (about 0.8 GB, a CPU is enough):

```bash
pip install "mineru>=4,<5" && mineru-kit models download --tier basic
```
</details>

To update, run `git pull` in the skill folder, run the `npx` line again, or upload the new zip on claude.ai.

## Use it

1. Give the agent a PDF and say "make me a reading guide for this".
2. It asks a few questions first: notes in English or Chinese, what you are reading for (the whole argument, core claims, method, evidence to cite, exam revision), how well you know the field, and anything you want answered. Say "you decide" to skip them.
3. A few minutes later you get the page. With Claude Sonnet, a 6-page paper took about 7 minutes and 134,000 tokens; a 10-page paper with 11 equations took about 10 minutes and 172,000 tokens.

While you read, ask the agent about any paragraph ("what is P23 saying?"), correct a note, or say "walk me through it" to go part by part.

## Built on reading research

- One sparse highlight style and a summaries-only view, because dense or wrong highlights cost readers' trust ([Scim](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)).
- Definitions on hover, where the term is used ([ScholarPhi](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648)).
- A "guess the relations" switch on the mind map, because argument maps help most when you work them out yourself ([van Gelder](https://www.reasoninglab.com/wp-content/uploads/2013/10/TvG-Using-argument-mapping-to-improve-critical-thinking-skills-2015.pdf)).
- Specific "read for" prompts, recall questions and summaries you open after trying to recall, following the evidence on pre-questions ([meta-analysis](https://link.springer.com/article/10.3758/s13423-023-02353-8)) and retrieval practice ([Dunlosky et al. 2013](https://doi.org/10.1177/1529100612453266)).
- Formula explanations folded, so you try to explain the step yourself first ([self-explanation](https://link.aps.org/doi/10.1103/PhysRevPhysEducRes.18.010136)).

## Known limits

- Works best on PDFs with a text layer in one or two columns. On unusual layouts a paragraph can come out split in two or merged with the next; the agent checks the split before it writes.
- Inline formulas read by MinerU can carry small recognition errors. Display formulas come with the PDF crop so you can check them.
- The page contains the full text of the PDF it was built from. Keep pages made from copyrighted readings to yourself.

The rules the agent follows are plain text in `references/`; edit them, or tell the agent what went wrong, as you learn what your readings need. The demos use two openly licensed papers: Ioannidis (2005), [Why Most Published Research Findings Are False](https://doi.org/10.1371/journal.pmed.0020124) (CC BY), and Rafailov et al. (2023), [Direct Preference Optimization](https://arxiv.org/abs/2305.18290) (CC BY 4.0).

## License

MIT. KaTeX (MIT) is vendored under `assets/katex/`; see `THIRD_PARTY_NOTICES.md`.
