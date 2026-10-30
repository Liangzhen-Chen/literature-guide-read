# Second read

A guide that passes check.py can still overstate the text. In trials the errors gathered in the shortest fields: a part claim that drops "may", a flow step that calls a result ruled out when the text says it is not supported, a recall answer that reports two table columns as significant when only one is. The writer rereads its own sentences and sees what it meant. A second reader who did not write the guide finds these reliably, so step 5b hands the finished guide to one.

## Who reads

A fresh agent that took no part in writing the guide: start a subagent when the environment offers one, and give it the brief below with the paths filled in. Where no subagent can be started (claude.ai), do the pass yourself, after check.py passes and before rendering: take the fields one at a time, open the paragraph each one cites, and read the paragraph before the guide's sentence.

## Brief for the second reader

> You are checking a reading guide against the text it guides. Find what would leave a reader believing something the text does not say.
>
> - The text: `WORK/paragraphs.json` (paragraph ids, text, pages), the crops in `WORK/crops/` for tables, figures and formulas, and the PDF at `<pdf>` for anything else (render a page to check a table).
> - The guide: `WORK/guide.json` and `WORK/paras_*.json`; the rules it was written to are in `SKILL_DIR/references/method.md` (section 12) and `schema.md`.
> - Segmentation fixes, if any: `WORK/fixes.json`, with ids from `WORK/paragraphs.orig.json`.
>
> Check, in this order:
> 1. The thesis, overview, part claims, flow steps, recall answers and answers to the reader's questions, each against the paragraphs it cites or the part it sums up, and the tables those paragraphs report. These short fields lose hedges first.
> 2. Every close-read note and every skim note that reports a result.
> 3. Each `frag` op in fixes.json: is the hidden text really outside the argument (masthead, chart labels, table cells), or did a list item, definition or caption disappear?
>
> For each, look for: a hedge, condition, sample, period, specification or scenario dropped; a result stated as ruled out, proved or caused when the text says less; significance or sign that differs between the text and its own table (name the column); a number that differs from the text or table; the authors' reading or assertion given as a finding; a view the authors report or reject given as theirs; the wrong object (who criticises whom, which group); a term translated at a different strength; an exception in the text that a summary sentence leaves out.
>
> Reply with one line per finding: `field` (e.g. `S4 claim`, `S2 flow P14`, `P23 note`, `S5 recall 2`), `misleading` or `minor`, what the guide says against what the text says (quote at most ten words), and the change that fixes it. Use `misleading` only when a reader would come away believing something the text does not say. Do not list style preferences. End with one line: how many misleading and minor findings.

## After the second read

Fix every misleading finding and every minor one whose fix is clear, in the guide data only; the original text is never edited. When a finding is wrong (the reader missed a sentence), leave the field and say why in one line. When a fixes.json op hid real text, do not apply fixes again now (it renumbers the paragraphs the guide already uses): give the hidden content in the note of the paragraph it belongs to and say so in the chat reply. Run check.py again before rendering. In the chat reply, say in one line how many findings the second read made and how many were fixed.
