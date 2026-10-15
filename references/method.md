# Method

The page helps a reader read the original; the notes support that reading and do not replace it. It serves three uses:

1. Short on time: the argument map at the top shows the whole argument on one screen.
2. Reading the text: the original runs in order. Close-read paragraphs are open with a "read for" prompt; skim and skip paragraphs show a note first, with the original one click away.
3. Looking something up: the sidebar lists what each paragraph does, the terms and the evidence.

## 1 Read everything first

Read every part file in full before writing anything. Decide the genre with genres.md. Try to state the author's question and answer in one sentence; if you cannot, reread the opening and closing paragraphs.

## 2 Parts and claims

- Split the reading into parts that follow the argument rather than only the author's headings. A part may split a section (for example "mechanism" and "its limits") or join two.
- Parts cover all paragraphs in order. Front matter such as a column preface can be a part with `"skip": true`.
- Each part has a short title, a role (what it does for the whole, such as "Evidence: markets do not remove it"), and a claim: the part's conclusion as a full sentence, with its key number if it has one. `claim_p` names the paragraph where the claim is stated best.
- Test: reading the part claims in order should reproduce the argument.

## 3 Tiers

`close`: the reader should read the original. Use it when the paragraph holds at least one of:

1. the main claim, or a part's claim stated in full for the first time;
2. a definition or distinction used later;
3. a step of the argument that cannot be skipped: a mechanism, a derivation, a model set-up;
4. the key evidence for a central claim;
5. a scope condition, limitation or concession, which summaries lose first;
6. the author's reply to the strongest objection;
7. a formula, model or estimating equation the argument relies on; the formula element carries its transcription and symbol table.

`skim`: the note restates the paragraph well enough to move on.

`skip`: repetition, roadmaps, transitions, asides. Give a reason.

The share of close reads is capped by `meta.density`: low 15%, medium 25%, high 40%. These are starting values.

## 3a The reader's purpose changes the tiers

`meta.purpose` is what the reader said they read for. Apply the profile, then the criteria above within it:

- **whole argument** (default): the criteria above as written.
- **core claims only**: close reads are the thesis, each part's claim and the qualifications; design, data and robustness paragraphs are skim with full restating notes, so the reader can trust the claim without reading the evidence. Density low.
- **method and design only**: close reads are the design, assumptions, identification and measurement paragraphs; results paragraphs are skim with their key numbers in the note. Density medium.
- **evidence to cite**: close reads are the paragraphs with the main numbers, tables and figures and the limitations; mark every `exp`, `field`, `survey` element with a label `s` so the evidence list is complete.
- **exam revision**: close reads as for whole argument, plus three or four recall questions per part instead of two.

`meta.familiarity` changes the notes, not the tiers: a reader new to the field gets a `def` element for every technical term at first use and notes that spell terms out; a reader who knows the field gets fewer definitions and shorter notes. Each question in `questions` is answered in `a` from the text only, with `p` naming the paragraphs that answer it; the page shows the questions at the top with links. If the text does not answer a question, say so in `a`.

## 4 What to write for each tier

- close, `read`: one line on what to watch for in the original, such as "How reversibility is stated, and how the offers trace each curve". Do not summarise; the reader is about to read it.
- skim, `note`: restate the content: the claim or result, the specific numbers, the definition itself, the conclusion. A reader who skips the original must still know what it said and on what basis. Never describe what the paragraph does ("introduces", "discusses", "这段介绍了"). Length follows content: one sentence for a transition, three or four for a paragraph of data.
- skip, `note` in one line, plus `why`.
- every paragraph, `role`: what it does, in a few words ("Experiment 2 results"). The sidebar shows these.

## 5 Elements

- Tag what a reader must not miss (see elements.md): definitions, claims, evidence with numbers, figures, tables, formulas, mechanisms, qualifications.
- Every element of level 2 or 3 needs an anchor `a`, a span copied verbatim from the paragraph, usually a clause or a sentence. The page highlights it in the original.
- `x` explains the element in the notes language ("Median reservation prices: sellers $7.12, choosers $3.12, buyers $2.87"). `s` is a short label for the argument map ("SFU mugs: sellers $7.12, buyers $2.87"). Give `s` only to elements that belong on the map, usually two to six per part.
- A definition names its term in `term`; Chinese notes keep the original term in brackets.
- Anchors in one paragraph must not overlap.
- A formula element needs `tex`, `syms` and `x` (schema.md). Check the LaTeX against the crop in `WORK/crops/` before you write the symbol table.

Inline mathematics in any note, read line, claim or explanation goes between single dollar signs, `$c_1 \in \{0,1\}$`, and the page renders it with KaTeX; write symbols that way rather than `c_1` or `p_max` in plain text. A span that starts with a digit is read as money (`$50,000 against $60,000`) unless it holds LaTeX or operators (`$1 + \eta$`) or no spaces (`$0$`). Sub- and superscripts inside such spans are notation, not numbers.

## 6 Numbers

Every number in a note, a read line, an element or a claim must appear in the source: the paragraph itself, its footnotes or its neighbours (for a part claim, anything in the part). check.py stops on numbers it cannot find. Keep the author's form: "more than an order of magnitude" stays that, not "10 times".

## 7 Footnotes

Footnotes appear under the paragraph that cites them. Give one an entry when it matters, such as a limitation or an alternative explanation. Author notes and acknowledgements need none.

## 8 Figures, tables and formulas

Figures and tables are shown on the paragraph that first mentions them, with the whole PDF page one click away. If sources.py found an open version, its clean figure, table or formula is shown as well. Tag the sentence that states what a figure shows as `fig`, so the map can point to it.

Display equations and table rows are cropped from the PDF by segment.py; the page shows the crop under the paragraph, beside the rendered `tex` and the symbol table. Transcribe table rows into the note only when the table carries the argument.

## 9 Language

- Notes follow the user's language, zh or en. Write both only when asked; `meta.notes_lang` lists them and the first is the default.
- Never translate or edit the original. Anchors are verbatim.
- Chinese notes: written Chinese with direct verbs; no "对……进行……", no "起到……作用", no long stacked modifiers; keep a key term's original form at first mention, such as 禀赋效应（endowment effect）.
- English notes: plain declarative sentences; no "this paragraph", no filler such as "importantly".
- In both: do not grade the authors, and add nothing the text does not say.

## 10 The logic map: relations and steps

The argument map at the top of the page is drawn from two fields on each part.

`rel` says what the part does for the argument. The first entry is the part's main job and must lead, directly or through other parts, to the conclusion `T`:

- `supports`: evidence or reasons for the conclusion or for another part's claim;
- `explains`: a mechanism that accounts for what another part shows;
- `qualifies`: limits, exceptions or cases where the explanation fails;
- `extends`: carries the result to new domains;
- `frames`: sets up the question or the terms;
- `challenges` and `answers`: an objection, and the reply to one;
- `concludes`: the part where the main conclusion is stated; the map merges it into the conclusion box.

Add secondary entries only for links a reader must see (Part 4 `explains` Parts 2 and 3). Give each a short `label` saying what the link is about: "the endowment effect survives market experience", not "supports the thesis".

`flow` lists three to six steps inside the part, in reading order. Each step names a paragraph (or one of its footnotes) and says in one line what it adds, and every step after the first has a `rel` describing how it relates to the step before it: supports, challenges, answers, rules out, implies, explains, qualifies, extends, names, raises or concludes. The flow is the part's reasoning ("objection, answered by the mug results, which rule out buyers' reluctance, which implies..."), not a list of every paragraph.

Test: reading the flows in order should tell the argument with its turns: where an objection comes in, what answers it, where the explanation stops working.

## 11 Recall questions

Each part that is not skipped carries two or three `recall` questions: short questions a reader should be able to answer after the part, each with its answer taken from the text ("What share of dealers traded? About 45%, against 20 to 25% of nondealers."). Retrieval practice is the best-supported study method; the page folds the questions at the end of the part with the answers hidden. Numbers in questions and answers must appear in the part.

## 12 Before running check.py

- Does each part claim read as the part's conclusion?
- Does each skim note let the reader move on?
- Does each read line point at something specific?
- Are the highlights what a skimming reader must not miss? More than four in a paragraph stops being a signal.
- Can the recall questions be answered from the part alone?
