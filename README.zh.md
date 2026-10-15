[English](README.md) | 中文

# reading-guide

**把一篇课程读物变成一张教你怎么读它的页面。** 给 AI agent 一份 PDF，得到一个离线 HTML：论证画成图，每一段分成精读、略读、可跳过，关键句在原文上标出，公式和表格从 PDF 上裁下来并加解释，每部分末尾有回想题。笔记可以是中文或英文。

![页面顶部：核心论点、读者的阅读目的和问题、论证地图](assets/readme/page-top.png)

![一个精读段：公式从 PDF 裁出，用 KaTeX 渲染并解释](assets/readme/page-formula.png)

上面的演示页来自 OpenStax 统计教材的一章（CC BY）。这个 skill 遵循开放的 [Agent Skills](https://agentskills.io) 格式，任何支持 skill 的 agent 都能用；脚本是普通 Python，页面是单个文件，离线可用。

## 安装（30 秒）

<details open>
<summary><b>Claude Code</b></summary>

```bash
git clone https://github.com/Liangzhen-Chen/literature-guide-read ~/.claude/skills/reading-guide
pip install -r ~/.claude/skills/reading-guide/requirements.txt
```

然后在任意项目里附上或指明一份 PDF，说"帮我做这篇的导读"。
</details>

<details>
<summary><b>Codex</b></summary>

```bash
git clone https://github.com/Liangzhen-Chen/literature-guide-read ~/.codex/skills/reading-guide
pip install -r ~/.codex/skills/reading-guide/requirements.txt
```
</details>

<details>
<summary><b>其他支持 Agent Skills 的工具（Cursor、Copilot、Gemini CLI 等）</b></summary>

```bash
npx skills@latest add Liangzhen-Chen/literature-guide-read
pip install pdfplumber
```

安装器会问装到哪些 agent；加 `-g` 装到用户级而不是当前项目。
</details>

<details>
<summary><b>claude.ai</b></summary>

把文件夹打成 ZIP，从 Skills 入口上传（如果你的方案有）。那里只能跑默认提取档（沙箱下不了模型）；扫描件和公式多的读物在本地 agent 里效果更好。
</details>

<details>
<summary><b>手动，配合任意聊天模型</b></summary>

脚本自己跑，模型只负责写导读数据。

```bash
pip install -r requirements.txt
python scripts/segment.py reading.pdf --out work
```

把 `references/` 里的文件和 `work/paragraphs_part*.txt` 给模型，配这段提示词：

> 为这篇读物写导读数据。规则在 method.md、elements.md、genres.md，格式在 schema.md。正文已经切成编号段落：用这些编号，不要重新切。先读完每一段，再按 method.md 写。笔记用[中文/英文]。只输出两个 JSON 块，分别存为 guide.json 和 paras_01.json。每条锚句逐字从原文复制。

把两个 JSON 存进 `work/`，然后：

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
python scripts/render.py work/paragraphs.json work/guide.json work/paras_01.json --out work/guide.html
```

`check.py` 报错就把错误贴回给模型让它改。
</details>

**可选，用于扫描件和公式密集的读物：** Tesseract（`eng`、`chi_sim`）和 Poppler 做 OCR；[MinerU](https://github.com/opendatalab/MinerU) 做版面分析（`pip install "mineru>=4,<5" && mineru-kit models download --tier basic`，约 0.8 GB，CPU 即可）。装了 MinerU 后 `segment.py` 自动使用，见[两档提取](#两档提取)。

## 用法

1. 给 agent 一份 PDF，让它做导读。
2. 它先问一轮：笔记语言；阅读目的（整体理解、只要核心论点、只看方法设计、找证据引用、备考）；对这个领域的熟悉程度；有没有想弄清的问题。说"你定"就按默认来。
3. 它切段、通读、写导读、校验，然后把页面给你。

页面上有：

- **你的简报**在顶部：目的、熟悉程度，以及你的每个问题从原文作答并链接到段落。
- **论证地图**：结论在最上方，各部分用带类型的关系（支持、解释、限定、推广……）连到结论；点一个部分看它内部的推理步骤。"先猜关系"把关系藏起来让你先自己判断。
- **按原文顺序排的正文**。精读段上方有一行"读时注意"；略读和可跳过段先显示复述笔记，原文一键可见。**粗读**视图只留笔记。
- 原文里的**高亮**：定义、论点、证据、图表、公式、限定；每个定义过的术语和符号在后文出现时悬停显示定义。
- **公式和表格**从 PDF 裁出，挂在引用它们的段落下；公式另用 KaTeX 渲染，配符号表和一句话解释，默认折叠。
- 每部分末尾的**回想题**，答案折叠。
- 左侧栏列出每段的作用、术语表、证据清单；中文、英文或双语切换。

阅读过程中可以问 agent 任何一段（"P23 在说什么？"），改某段的档位或笔记，或者说"带我过一遍"让它逐部分讲。

## 原理

1. `segment.py` 把 PDF 切成固定编号的段落（P1、P2……），识别标题、图注、脚注，去掉页眉，记下印刷页码，把脚注挂到引用它的段落上，并把每条行间公式和表格区域裁成图。支持双栏、扫描件 OCR、中文标题和脚注。
2. `sources.py`（可选）抓取 arXiv 的 HTML 或 TeX 版本，取干净的图、表、公式。
3. Agent 读完每一段，写导读数据：分部分和分论点、部分之间的关系、每段的档位和笔记或"读时注意"、逐字锚定的要素、对照裁剪图核对过的公式转写、回想题。
4. `check.py` 拒绝一切它核实不了的东西：每段都有条目、各部分按顺序覆盖全文、锚句逐字存在、导读里每个数字都在原文里、LaTeX 括号配平、精读比例不超上限、笔记是复述而不是描述。
5. `render.py` 生成单文件页面。

Agent 遵守的规则在 `references/method.md`、`elements.md`、`genres.md`、`schema.md`，都是纯文本，可以随着你的读物调整。

## 两档提取

| | 默认 | 装 MinerU |
| --- | --- | --- |
| 安装 | `pip install pdfplumber` | 再装 MinerU 和基础模型（约 0.8 GB） |
| 页眉、标题、表格 | 文字层上的启发式规则 | 版面分析；表格成结构 |
| 行间公式 | 启发式定位后裁图 | 版面模型定位后裁图；装了公式模型还会转成 LaTeX |
| CPU 上的速度 | 每篇几秒 | 每篇 1 到 3 分钟 |

11 篇读物（七篇真实文献、扫描件和一章教材）的实测：在人工核对页上 MinerU 在 8 篇里 7 篇持平或更好，JSTOR 扫描件里默认档误判成标题的 30 处页眉全部去掉，约 800 行散落的表格行变成 111 张表。四篇公式密集的论文（机器学习、计量经济学、量子计算、纯数学）上 MinerU 找到的行间公式约是默认档的两倍。不装 MinerU 的 577 MB 公式模型时，公式以裁剪图输出、由 agent 转写，速度快 40% 到 75%。

## 为什么这样读

设计依据是已发表的阅读界面和学习研究：

- 分面高亮让读者更快找到信息且不降低准确率，但错误或过密的高亮会损害信任（[Scim, Allen AI](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)）。所以高亮稀疏、经过校验，并提供粗读视图。
- 在用到的位置给定义对读密集论文有帮助（[ScholarPhi](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648)）。所以有悬停释义。
- 论证图能提升批判性思维，收益来自自己把图做出来，而不是看现成的（[van Gelder](https://www.reasoninglab.com/wp-content/uploads/2013/10/TvG-Using-argument-mapping-to-improve-critical-thinking-skills-2015.pdf)）。所以有"先猜关系"。
- 前置问题对它指向的内容有效（[prequestion 元分析](https://link.springer.com/article/10.3758/s13423-023-02353-8)），提取练习是证据最强的学习方法（[Dunlosky 等 2013](https://doi.org/10.1177/1529100612453266)）。所以"读时注意"写得具体，每部分有回想题。
- 自己解释工作示例比读解释有效（[self-explanation](https://link.aps.org/doi/10.1103/PhysRevPhysEducRes.18.010136)）。所以公式解释默认折叠。

## 文件

| 文件 | 内容 | 什么时候改 |
| --- | --- | --- |
| `SKILL.md` | 流程和 agent 必须遵守的规则 | 流程变化时 |
| `references/method.md` | 方法：分部分、档位、笔记、要素、数字、回想题 | 调整方法时（大多数修改在这里） |
| `references/elements.md` | 要素类型；`check.py` 和页面从这里读 | 增删类型时 |
| `references/genres.md` | 按体裁的调整 | 遇到新体裁时 |
| `references/schema.md` | 导读数据格式和示例 | 很少 |
| `scripts/segment.py` | 切段 | 切段出错时 |
| `scripts/mineru_backend.py` | 可选的 MinerU 引擎及其输出的处理规则 | MinerU 输出需要新规则时 |
| `scripts/crops.py` | 公式和表格区域的裁剪 | 裁剪尺寸变化时 |
| `scripts/sources.py` | 开放版本 | 开放版本处理变化时 |
| `scripts/check.py` | 校验 | 加检查项时 |
| `scripts/render.py` | 页面组装；`--dump` 从页面恢复数据 | 很少 |
| `assets/template.html` | 页面 | 改页面时 |
| `CHANGELOG.md` | 每次修改和起因 | 每次修改 |

测试：`python -m pytest tests/unit`（Python 3.9 和 3.12）。脚本的每处修改都有一条先失败后通过的回归测试。

## 已知限制

- 默认档的切段是启发式的：公式、表格、元数据和特殊版式仍可能切错或合并段落。写导读前先抽查 part 文件，之后段落编号固定。
- 正文里的行内公式按 PDF 文字层原样保留，除非装了 MinerU 的公式模型。原文一字不改；行间公式以裁剪图配转写显示。
- 开放版本只对 arXiv 论文抓取，且需要网络允许。
- 页面里嵌有生成它的 PDF 的全文。用受版权保护的读物生成的页面只留给自己看；公开演示请用开放许可的论文。

## 许可

MIT。KaTeX（MIT）内置在 `assets/katex/`，详见 `THIRD_PARTY_NOTICES.md`。
