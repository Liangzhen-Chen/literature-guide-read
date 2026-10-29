# Method

The page helps a reader read the original and gives an after-reading summary of every paragraph, so a reader without time still gets the whole argument. It serves three uses:

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
7. a formula, model or estimating equation the argument relies on; the formula element carries its transcription and symbol table. The paragraph that states a result derived from such a formula is close too.

`skim`: the note restates the paragraph well enough to move on.

`skip`: repetition, roadmaps, transitions, asides. Give a reason.

The share of close reads is capped by `meta.density`: low 15%, medium 25%, high 40%. These are starting values.

## 3a The reader's purpose changes the tiers

`meta.purpose` is what the reader said they read for. Apply the profile, then the criteria above within it:

- **whole argument** (default): the criteria above as written. In an empirical paper the identification (what lets the authors read an estimate as the effect they claim: an ordering of variables, an instrument, a control group, a restriction), the main results and the robustness checks that bear on the reader's questions are close reads; if the density cap forces a choice, these come before background and literature. The notes on the identification say what assumption it rests on (for an instrument, that it moves the outcome only through the treated variable) and what the authors offer for it, so the reader can judge how strong it is.
- **core claims only**: close reads are the thesis, each part's claim and the qualifications; design, data and robustness paragraphs are skim with full restating notes, so the reader can trust the claim without reading the evidence. Density low.
- **method and design only**: close reads are the design, assumptions, identification and measurement paragraphs; results paragraphs are skim with their key numbers in the note. Density medium.
- **evidence to cite**: close reads are the paragraphs with the main numbers, tables and figures and the limitations; mark every `exp`, `field`, `survey` element with a label `s` so the evidence list is complete.
- **exam revision**: close reads as for whole argument, plus three or four recall questions per part instead of two.

`meta.familiarity` changes the notes, not the tiers: a reader new to the field gets a `def` element at first use for every technical term the argument relies on (each method, model, test, measure and data series a step or claim needs) and notes that spell terms out; a reader who knows the field gets fewer definitions and shorter notes. Before writing, list the terms a newcomer would stop at, starting with the terms the paper's question and the reader's own questions turn on (often a distinction, such as two kinds of protection an asset can give), then the terms the method and results use, and check each has its `def`. When familiarity was not given, write for a reader who knows the field in general but not this paper's methods. Each question in `questions` is answered in `a` from the text only, with `p` naming the paragraphs that answer it; the page shows the questions at the top with links. If the text does not answer a question, say so in `a`.

## 4 What to write for each tier

- close, `read` and `note`. `read` is one line on what to watch for in the original, such as "How reversibility is stated, and how the offers trace each curve"; it must not give away the content, because the reader is about to read it. `note` is the after-reading summary: restate the paragraph under the same rules as a skim note (the claim or result, the specific numbers, the definition itself, the qualification). The page shows it below the original, folded, so the reader reads the original first. A close entry without `note` is a warning.
- skim, `note`: restate the content: the claim or result, the specific numbers, the definition itself, the conclusion. A reader who skips the original must still know what it said and on what basis. Never describe what the paragraph does ("introduces", "discusses", "这段介绍了"). Length follows content: one sentence for a transition, three or four for a paragraph of data.
- skip, `note` in one line, plus `why`.
- every paragraph, `role`: what it does, in a few words ("Experiment 2 results"; at most 16 Chinese characters or 60 English characters, since the sidebar shows these). A role names the move; the content goes in `read` or `note`. Write every entry from the paragraph in hand: never start from another guide's files, whose roles and notes belong to a different text. `read` fits in 90 Chinese or 240 English characters.

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
- Chinese notes keep English terms. Terms, model and method names, metric names and abbreviations (PPV, RLHF, reward model, Bradley-Terry, KL divergence, policy, power, Type I error) stay in English, or appear once as 中文（English） at first mention and then in one form only, the same throughout the note. A term with no common Chinese rendering stays in English. Bad: "奖励模型用布拉德利-特里模型拟合偏好" / Better: "reward model 用 Bradley-Terry 模型拟合偏好".
- Never translate or edit the original. Anchors are verbatim.
- Chinese notes: written Chinese with direct verbs; no "对……进行……", no "起到……作用", no long stacked modifiers; keep a key term's original form at first mention, such as 禀赋效应（endowment effect）.
- English notes: plain declarative sentences; no "this paragraph", no filler such as "importantly".
- In both: do not grade the authors, and add nothing the text does not say.

## 9a Plain wording

The wording rules below are drawn from lists of common AI writing habits. They apply to every field you write, in zh and en. check.py warns on the first four patterns; the rest are on you.

- No denial before the statement. Bad: "这不是偏好，而是禀赋效应" / "It is not a preference but the endowment effect". Better: "卖家要价高出买家一倍多，这是禀赋效应" / "Sellers ask about twice what buyers offer: the endowment effect". Also avoid "not just", "not only", "而不是", "不仅仅是". This includes answering an objection nobody raised ("很多人以为…其实…").
- No dash as a connector (— or ——). Bad: "Sellers asked more — buyers offered less". Better: "Sellers asked more, and buyers offered less". Use a comma, colon, full stop or brackets.
- Say "is", not "serves as" or "stands as". Bad: "The mug serves as the test good". Better: "The test good is a mug".
- No closing line that only sums up or points at importance. Bad: "这才是关键。" / "This is what matters." Better: end on the last fact the paragraph gives, or stop one sentence earlier.
- Do not pad lists to three. Bad: "reliable, robust and replicable" when the text says two things. Better: name the two.
- Cut inflating words: crucial, pivotal, key (as praise), 关键性, 至关重要, 深刻, 全面. Bad: "a pivotal result that fundamentally changes the field". Better: "the result: 45% of dealers traded". Say what the number or claim is.

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

`flow` lists three to six steps inside the part, in reading order. Each step names a paragraph (or one of its footnotes) and says in one sentence (about 45 Chinese characters or 25 English words) what it adds, and every step after the first has a `rel` describing how it relates to the step before it: supports, challenges, answers, rules out, implies, explains, qualifies, extends, names, raises or concludes. A step gives the move in one sentence and does not restate the paragraph's note. The flow is the part's reasoning ("objection, answered by the mug results, which rule out buyers' reluctance, which implies..."), not a list of every paragraph.

A step explains the move, so a reader can follow it without the paper open:

- Say what is claimed and why it follows (the reason, the idea of the derivation, or the evidence), and how it leads to the next step. Bad: "Eq. 3 的 optimal policy 有闭式解 Eq. 4". Better: "带 KL 惩罚（强度 β）的目标有闭式最优解，所以 reward 可写成 β log(π/π_ref) 加只依赖 x 的项". Name the idea of a formula; do not spell it out in words.
- Define each symbol or abbreviation in the step where it first appears in the part: "β（KL 惩罚的强度）". Never lean on a bare equation number; say what the equation states.
- A number carries its setting: which scenario, sample or table it comes from.
- When the paper lists items ("six corollaries"), the steps cover all of them or say which are left out.

Test: reading the flows in order should tell the argument with its turns: where an objection comes in, what answers it, where the explanation stops working.

## 11 Recall questions

Each part that is not skipped carries two or three `recall` questions: short questions a reader should be able to answer after the part, each with its answer taken from the text ("What share of dealers traded? About 45%, against 20 to 25% of nondealers."). At least one per part asks why or how: why the authors chose a design, how a result supports or limits the claim, what would change the conclusion. Its answer gives the reason the text gives. A question answered by finding one number in the text is a look-up; keep those to one per part. Retrieval practice is the best-supported study method; the page folds the questions at the end of the part with the answers hidden. Numbers in questions and answers must appear in the part.

## 12 Before running check.py

First reread each claim, flow step, note and recall answer beside its paragraph and check two things check.py cannot:

- Direction: which variable rises or falls, which group is larger, the sign of each effect, which way a series responds. A reversed result is the worst error a guide can make.
- Strength: keep the author's hedges and limits (may, suggests, in the short run, contemporaneous, in this sample, until a given year) and the sample or period a result comes from. A relation word such as "rules out" or "proves" needs the text to say as much; otherwise use "supports" or "qualifies". "Does not respond" is not "moves the other way".
- The thesis, the overview, the part claims, the flow steps and the answers to the reader's questions are the shortest fields and lose hedges first; check them hardest, against the paragraphs and tables they summarise rather than against your other notes. They also keep each claim's object: when the authors criticise one of several proposals, name only that one, and keep their qualifier on whose view it is ("as MMT defines it").
- Conditions: a result derived in a model or under an assumption ("in a plausible model", "in equilibrium", a parameter range, a policy rule) keeps that condition in every field that repeats it. A result the authors assert without deriving it in this text is written as their assertion.
- Position: when a paper answers other authors, the thesis and the first part say where the authors agree with them as well as where they disagree. A paragraph that corrects another author's reading is a close read, and the flow names that author as the object. A reader who meets the agreement only deep in the text reads the paper as a blanket rejection.
- Setting: every number names where it comes from (table and column, sample, specification). A comparison of two estimates says when they come from different samples, methods, shocks or denominators; when a paper gives ranges from several methods, also compare within one method. Name the group a number covers when the authors' label is broader (an "EU" that is 19 member states), and carry the authors' limits on which members a result holds for. When the robustness checks change the size of a headline estimate, give the range, not only that it stays significant. A result that is not significant in a subgroup or specification is said to be not significant, not that it has no effect or a different effect. A conclusion the authors read off point estimates without a test shown (a coefficient above 1, two estimates "not significantly different") is written as their reading.
- Terms: render each word at the author's strength. A plain description stays plain in translation when the field has a technical term for something stronger: "runaway inflation" is 失控通胀, and 恶性通胀 (hyperinflation) only where the text says hyperinflation.
- Exceptions: when the text's own later evidence makes an exception to a summary claim (one of four cases went the other way), the notes that repeat the summary claim keep the author's words and name the paragraph with the exception.
- Consistency: a fact stated in several fields (what the instrument is, the sample, the period) reads the same in all of them.
- A result the authors report but do not show ("available upon request", an appendix that is not in the PDF) is the authors' claim: say so, and say the reader cannot check it in the text.

Then:


- Does each part claim read as the part's conclusion?
- Does each skim note let the reader move on?
- Does each read line point at something specific?
- Are the highlights what a skimming reader must not miss? More than four in a paragraph stops being a signal.
- Can the recall questions be answered from the part alone, does each answer give the text's reason for the question asked, and does each part have a why or how question?
- Does every term the argument relies on have its definition at first use? The thesis and the part claims are read first, so a technical term they use needs a few-word gloss there.
