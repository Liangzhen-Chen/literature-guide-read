# Guide data format

Write the guide into the working folder as `guide.json` (meta, thesis, overview, parts) plus `paras_01.json`, `paras_02.json`, ... with about 40 paragraph entries each under a single key `paras`. check.py and render.py merge them.

Text fields take either a plain string, meaning the first language in `meta.notes_lang`, or an object such as `{"zh": "...", "en": "..."}` when the notes are bilingual.

## guide.json

```json
{
  "meta": {
    "title": "Anomalies: The Endowment Effect, Loss Aversion, and Status Quo Bias",
    "author": "Kahneman, Knetsch & Thaler",
    "source": "Journal of Economic Perspectives 5(1), 1991",
    "genre": "Review",
    "notes_lang": ["en"],
    "density": "medium",
    "language": "en",
    "purpose": "core claims only",
    "familiarity": "knows the field, has not read this paper"
  },
  "questions": [
    {"q": "Does market experience remove the effect entirely?", "a": "For dealers and experienced nondealers the trading rate is close to one half and the test cannot reject no effect; in the lab a significant effect remains after four rounds.", "p": ["P22", "P55", "P58"]}
  ],
  "thesis": "The endowment effect and status quo bias are robust anomalies that loss aversion relative to a reference point explains.",
  "overview": "Two to four sentences: the question, the route of the argument, the conclusion.",
  "parts": [
    {"id": "S0", "title": "Column note", "range": "P1-P2", "role": "Column housekeeping", "skip": true},
    {"id": "S1", "title": "Introduction", "range": "P3-P4", "role": "The phenomenon and three concepts",
     "claim": "The endowment effect and status quo bias are manifestations of loss aversion", "claim_p": "P4"}
  ]
}
```

Parts also carry recall questions (method.md section 11) and the logic map (section 10):

```json
{"id": "S4", "title": "Experiment I results", "range": "P18-P26", "role": "Evidence", "claim": "...", "claim_p": "P22",
 "recall": [{"q": "What share of the pooled sample traded?", "a": "32.8 and 34.6 percent, below the half expected without an endowment effect."},
            {"q": "Which nondealers traded like dealers?", "a": "Those trading 6 or more times a month: 46.7 percent traded."}]}
```


```json
{"id": "S2", "title": "Endowment effect", "range": "P5-P15", "role": "Evidence: markets do not remove it",
 "claim": "Owners ask about twice what buyers offer, even with market experience", "claim_p": "P13",
 "rel": [{"to": "T", "type": "supports", "label": "the endowment effect survives market experience"}],
 "flow": [
   {"p": "P6", "x": "Critics: a bargaining habit that market experience removes"},
   {"p": "P11", "rel": "answers", "x": "Cornell mugs: 11 trades predicted, 1–5 observed, no learning trend"},
   {"p": "P13", "rel": "rules out", "x": "Sellers $7.12 vs Buyers $2.87: owners' reluctance, not buyers'"}
 ]}
```

`meta.purpose` and `meta.familiarity` are the reader's answers from the brief (SKILL.md step 0); `questions` are the reader's own questions, each answered from the text with the paragraph ids `p` that answer it. Numbers in `a` must appear in those paragraphs.

Rules: `parts` cover P1 to the last paragraph in order; ranges are written `P3-P9` or `P3`; `claim_p` lies inside its part; parts marked `"skip": true` need no claim. Once any part has `rel`, every part that is not skipped needs one, and each part's first relation must lead to `T` without a cycle. Flow steps name paragraphs or footnotes inside the part. `meta.density` is low, medium or high; `meta.language` is the language of the original.

## paras_01.json

```json
{
  "paras": {
    "P4": {
      "tier": "close",
      "role": "Three core concepts",
      "read": "The exact wording of the three definitions, and the claim that the first two are manifestations of loss aversion.",
      "els": [
        {"t": "def", "term": "endowment effect", "a": "people often demand much more to give up an object than they would be willing to pay to acquire it",
         "x": "Demanding much more to give up an object than one would pay to acquire it", "s": "Endowment effect"},
        {"t": "claim", "a": "These anomalies are a manifestation of an asymmetry of value",
         "x": "Both anomalies are manifestations of loss aversion"}
      ]
    },
    "P12": {
      "tier": "skim",
      "role": "Experiment 2 design",
      "note": "77 Simon Fraser students were split into Sellers, Buyers and Choosers, each answering at prices from $0.25 to $9.25.",
      "els": [{"t": "method", "x": "Sellers, Buyers and Choosers facing the same price list"}]
    },
    "P30": {
      "tier": "close",
      "role": "The estimating equation",
      "read": "What enters X, and that g is a probit link.",
      "els": [
        {"t": "formula", "a": "trade = g(α + β′X)", "tex": "\\mathrm{trade} = g(\\alpha + \\beta' X)",
         "syms": [{"s": "trade", "m": "1 if the subject traded"}, {"s": "X", "m": "subject characteristics: experience, income, age"}, {"s": "g", "m": "the probit link"}],
         "x": "The chance of trading is a probit function of the subject's characteristics",
         "why": "Lets experience be tested while holding the other characteristics fixed",
         "s": "Probit model of trading"}
      ]
    },
    "P35": {"tier": "skip", "role": "Transition", "note": "Leads into the two wage questions.", "why": "the next two questions carry the data"},
    "N4": {"tier": "close", "role": "Footnote 3: scope", "read": "A scope condition that is easy to miss when citing the paper.",
           "els": [{"t": "limit", "a": "Loss aversion is expected to primarily affect owners of goods that had been bought for use", "s": "Note 3: ordinary trade unaffected"}]}
  }
}
```

Field rules:
- `tier`: close, skim or skip. close needs `read`; skim needs `note`; skip needs `note` and `why`. Every entry needs `role`.
- `els[].t` comes from elements.md. Types of level 2 or 3 need `a`, copied verbatim from the paragraph; check.py reports the closest sentence when an anchor is not found.
- `els[].s` is the argument-map label; `els[].x` the longer explanation; `els[].term` the term a definition defines.
- `formula` elements: `tex` is the LaTeX (copied from the open version, from MinerU, or transcribed by you from `WORK/crops/<id>.png`); `syms` lists every symbol; `x` says the equation in words; `why` is optional. A formula element without `tex` gets a warning.
- Footnote entries use the footnote's id (N1, N2, ...) from paragraphs.json and are optional.
- Numbers in any text field must appear in the source text (method.md section 6).
