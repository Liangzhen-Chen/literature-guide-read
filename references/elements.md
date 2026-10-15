# Element types

Elements are what a reader most needs to see in a paragraph: definitions, claims, evidence, figures, formulas, qualifications. Each one is anchored to a verbatim span of the original and highlighted there.

`check.py` and the page read every line of the form `### code | English name | 中文名 | level | colour family`, and the line after it is the description shown on hover. Keep that format when you add or rename types.

Levels: 3 = highlighted with a type tag, may appear on the argument map when it has a short label `s`, needs an anchor; 2 = highlighted with a type tag, needs an anchor; 1 = a tag in the paragraph header only, anchor optional.

## Claims

### thesis | Thesis | 核心论点 | 3 | claim
The reading's main claim. Usually one or two in a whole text.

### claim | Claim | 分论点 | 3 | claim
A part-level claim or an intermediate conclusion the argument builds on.

### other | Others' view | 他人观点 | 1 | plain
A claim reported from other work that the author does not endorse.

## Concepts

### def | Definition | 定义 | 3 | def
Defines, distinguishes or classifies a term the text relies on later. Put the term in `term`.

### assumption | Assumption | 前提假设 | 2 | def
A premise or modelling assumption the argument depends on.

## Evidence

### exp | Experiment | 实验 | 3 | ev
An experimental result, with its key numbers.

### survey | Survey | 调查 | 3 | ev
A survey or questionnaire result.

### field | Field data | 现场数据 | 3 | ev
Observational, administrative or field data, including natural experiments.

### case | Case | 案例 | 2 | ev
A case, anecdote or historical episode used as support.

### quote | Quotation | 引文 | 2 | ev
A quotation from an authority used as support.

## Figures, tables and formulas

### fig | Figure | 图 | 3 | fig
A figure, or the sentence that tells the reader what a figure shows.

### table | Table | 表 | 3 | fig
A table, or the sentence that introduces it.

### formula | Formula | 公式 | 3 | math
An equation, model or quantitative relation the argument relies on. Give `tex` (LaTeX, no `$`), `syms` (each symbol and what it stands for), `x` (what the equation says in words) and, when it matters, `why` (its job in the argument). The page shows the PDF crop beside the rendered `tex`, so the reader can check the transcription.

## Reasoning

### mech | Mechanism | 机制 | 2 | mech
A causal mechanism, a derivation step, or an explanation of why something happens.

### pred | Prediction | 理论预测 | 2 | mech
What a theory predicts, usually set against what was observed.

## Qualifications

### limit | Qualification | 限定 | 2 | limit
A scope condition, exception, limitation or caveat the author states.

### objection | Objection | 质疑 | 2 | limit
An objection to the argument, raised by the author or by others.

## Material

### method | Design | 设计 | 1 | plain
How a study or an argument is set up.

### example | Example | 例子 | 1 | plain
An illustration of a point already made, not needed for the argument to stand.

## Choosing a type

- Example or evidence: an example helps the reader understand a point, evidence makes them believe it. If the argument stands on the case, tag it `case`, not `example`.
- Thought experiments in theory papers usually carry the argument: tag the step `mech` or the case `case`.
- Prediction and result: tag the prediction `pred` and the observed result `exp`, `survey` or `field`. The contrast is usually the point.
- A paragraph can hold several elements. Tag what a reader skimming the highlights must not miss; two to four in a close-read paragraph is typical.

## Sources of this scheme

The set combines three research schemes: CoreSC (Liakata et al.) for the objective, method and outcome concepts of scientific papers; the argument annotation of Lauscher, Glavaš and Ponzetto (2018) for own claims, background claims and data; and DoCO, the Document Components Ontology, for figures, tables and formulas.
