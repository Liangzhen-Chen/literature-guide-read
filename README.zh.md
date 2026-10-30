[English](README.md) | 中文

# literature-guide-read

**它先通读全文，再告诉你哪些段落要细读、哪些略读、哪些可以跳过。**

一个读论文和课程读物用的 agent skill。把 PDF 交给 agent，你会拿到一张围绕原文做的离线网页，笔记可以用中文、英文或双语。Claude Code、Codex、claude.ai 以及其他支持 [Agent Skills](https://agentskills.io) 的工具都能用。

页面上是完整的原文，由你自己读。导读告诉你哪里值得多花时间、读的时候留意什么，读完可以用小结和回想题看看自己读懂了多少。

直接打开做好的页面：[Ioannidis（2005），中英双语笔记](https://liangzhen-chen.github.io/literature-guide-read/)，或 [DPO 论文（2023），中文笔记](https://liangzhen-chen.github.io/literature-guide-read/dpo.html)。两篇论文都是开放许可：[Ioannidis](https://doi.org/10.1371/journal.pmed.0020124)（CC BY），[Rafailov 等](https://arxiv.org/abs/2305.18290)（CC BY 4.0）。

![导读页面的用法：结论和论证结构图，跳到一个部分，精读段的公式和展开的读后小结，点左栏的一步，只看小结](assets/readme/demo.zh.gif)

## 页面上有什么

- 每段都标好**精读、略读或跳过**。精读段保留全文，先提示读的时候注意什么；略读段先给一两句复述；跳过的段收成一行。时间不够时可以只看小结。
- 顶部是**一句话结论**，下面一张思维导图，画出各部分怎么推出它。
- **左栏跟着你走**，显示当前部分的论点、编号的推理步骤和这一部分引入的术语，点某一步就跳到对应段落。
- **原文一字不改**，导读写的内容都单独放在浅色底的框里。
- **重要公式**渲染出来并加解释，附符号表和 PDF 原图。
- 精读段读完可以**展开小结**，对照自己读到了什么；每部分末尾有**回想题**。
- 开始前你问的问题，页面会**从原文里作答**，并链接到相关段落。
- 生成页面前，先**拿笔记和原文核对**数字和标注句，再由独立 agent 对照原文和表格复读，找出丢掉的限定词、说重的结论和弄反的正负号；环境无法启动另一个 agent 时，由写导读的 agent 逐字段复读。写导读的 agent 改好问题后再生成页面。每篇会多用一些额度。
- 写导读之前，agent 会**先看页面**：在页面图上画出每段的框，改正文字提取弄错的首页信息、图表说明、表注和被拆断的段落。

![DPO 论文的一个部分，中文笔记：左栏是这部分的论点、推理步骤和术语；右侧是一个精读段，有读时注意、渲染好的公式和展开的读后小结](assets/readme/page-formula.png)

## 安装

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
<summary><b>其他支持 Agent Skills 的工具（Cursor、Copilot、Gemini CLI 等）</b></summary>

```bash
npx skills@latest add Liangzhen-Chen/literature-guide-read
pip install pdfplumber fonttools pillow beautifulsoup4
```

安装器会问装到哪些 agent；加 `-g` 装到用户级，不加则装到当前项目。
</details>

<details>
<summary><b>claude.ai</b></summary>

从 [最新 Release](https://github.com/Liangzhen-Chen/literature-guide-read/releases/latest) 下载 `literature-guide-read.zip`，在 Settings → Capabilities → Skills 上传。扫描件在 claude.ai 上读不了，要在本地 agent 里装上 MinerU；公式多的论文也是在本地效果更好。
</details>

<details>
<summary><b>手动，配合任意聊天模型</b></summary>

脚本自己跑，模型只负责写导读数据。

```bash
pip install -r requirements.txt
python scripts/segment.py reading.pdf --out work
```

写导读前，查看第 1 页、正文最后一页、自检点名的页和分段文字读起来不对的页。先画出框和编号（这里从第 1 页开始）：

```bash
python scripts/fix.py overlay work/paragraphs.json --pages 1
```

把 PDF、这些页面图、`work/paragraphs.json`、分段文件和 SKILL.md 第 1b 步交给模型，让它写 `work/fixes.json`，用数组列出明确的改正操作（无需改正时写 `[]`）。应用后列出编号：

```bash
python scripts/fix.py apply work/fixes.json --paras work/paragraphs.json
python scripts/fix.py ids work/paragraphs.json
```

改正操作始终用首次分段的编号；应用后可用 `fix.py overlay work/paragraphs.json --orig` 或 `paragraphs.orig.json` 查找。导读数据用 paragraphs.json 和重写后的分段文件中的新编号。

把 `references/` 里的文件和 `work/paragraphs_part*.txt` 给模型，配这段提示词：

> 为这篇读物写导读数据。规则在 method.md、elements.md、genres.md，格式在 schema.md。正文已经切成编号段落：用这些编号，不要重新切。先读完每一段，再按 method.md 写。笔记用[中文/英文]。只输出两个 JSON 块，分别存为 guide.json 和 paras_01.json。每条锚句逐字从原文复制。

把两个 JSON 存进 `work/`，然后检查：

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
```

改好错误后，另开新对话，交给它 `references/review.md`、paragraphs.json、分段文件、导读文件、裁图和页面图（缺页图时附上 PDF）。有 fixes.json、paragraphs.orig.json 和 fixes_log.json 时也一并给它。让它复读，把发现的问题交回写导读的模型，改好所有误导性问题和改法明确的次要问题，然后再检查、生成页面：

```bash
python scripts/check.py work/paragraphs.json work/guide.json work/paras_01.json
python scripts/render.py work/paragraphs.json work/guide.json work/paras_01.json --out work/guide.html
```
</details>

更新：在 skill 文件夹里运行 `git pull`，或重新运行一次 `npx` 那行，claude.ai 上则重新上传新的 zip。

### 两档提取

按上面的方法装好就是基础档。再装上 [MinerU](https://github.com/opendatalab/MinerU) 就是完整档，装好后 skill 会自动使用，不用切换。没装的话，agent 会在开始时问你要不要装，说清楚能多得到什么、要付出什么；你说要，它就自己装。扫描版 PDF 只有 MinerU 能读，遇到扫描件 agent 会建议你装。

| | 基础档 | 装 MinerU |
| --- | --- | --- |
| 安装 | 上面已经装好 | `pip install "mineru>=4,<5" && mineru-kit models download --tier basic`（约 0.8 GB，CPU 即可） |
| 版式 | 单栏、双栏、三栏 | 另外更稳地处理侧栏、跨栏表格和特殊版式；表格保留成表格 |
| 公式 | 从 PDF 上裁图，重要的由 agent 转写 | 识别更全，自动转成 LaTeX |
| 扫描件 | 读不了 | 能读（自带 OCR） |
| 读 PDF 用时 | 几秒 | 1 到 3 分钟 |
| claude.ai | 能用 | 不能用（沙箱下载不了模型） |

两档都可以通过页面图查看插图；论文在 arXiv 上有网页版时，换成作者的原图。基础档把旋转文字的表格保留为转正的裁图。

### 依赖

| 包 | 用途 | 能多得到什么 | 成本 |
| --- | --- | --- | --- |
| pdfplumber | PDF 文字和页面图 | 词、位置和 PDF 裁图 | PDF 输入必需；读取文字层 |
| fonttools | 嵌入字体的元数据和字形 | 更准的字重、大小写和符号修复 | 小型本地 Python 依赖 |
| Pillow | 页面框图和裁图编辑 | 编号标签、转正裁图和更小的内嵌图片 | 本地 Python 依赖 |
| beautifulsoup4 | 开放版本的 HTML | arXiv 上的图、表和公式 | sources.py 使用；获取文件需要联网 |
| MinerU（可选） | 版式分析和 OCR | 扫描件、特殊版式和公式 LaTeX | 模型约 0.8 GB；早期试用中 CPU 每篇 1 到 3 分钟 |

### 脚本

- `segment.py`：提取文字并编号；`crops.py`：写公式和表格裁图；`mineru_backend.py`：可选的 MinerU 提取。
- `fix.py overlay/apply/ids`：查看并改正分段；`fix_crops.py`：应用改正时保留裁图并按新编号命名。
- `sources.py`：获取并解析开放版本；`check.py`：检查导读数据；`render.py`：生成离线页面，或用 `--dump` 取回页面中的数据。

## 用法

1. 给 agent 一份 PDF，说"帮我做这篇的导读"。
2. 它先问几个问题：笔记用中文还是英文；为什么读（整体理解、只要核心论点、看方法、找证据引用、备考）；对这个领域熟不熟；有没有想弄清的问题。说"你定"就按默认来。
3. agent 看完页面并完成第二遍复读后交付。加入第 1b 和 5b 步之前，Claude Sonnet 实测：6 页论文约 7 分钟、13.4 万 token；10 页、11 条公式的论文约 10 分钟、17.2 万 token。试用中，第二遍复读额外使用的 token 约为写导读用量的一半到四分之三；这是试用估计，看页面也会增加工作量。

读的时候可以问 agent 任何一段（"P23 在说什么？"），让它改某条笔记，或者说"带我过一遍"让它逐部分讲。如果某类读物总是出同样的问题，直接告诉 agent：它遵守的规则是 `references/` 里的纯文本，它可以自己改。

## 依据阅读研究设计

- 只用一种高亮，而且标得少，另有只看小结的视图：过密或标错的高亮会让读者不再信任它（[Scim](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)）。
- 术语在用到的地方悬停显示释义（[ScholarPhi](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648)）。
- 思维导图有"先猜关系"开关：论证图在自己动手推的时候最有用（[van Gelder](https://www.reasoninglab.com/wp-content/uploads/2013/10/TvG-Using-argument-mapping-to-improve-critical-thinking-skills-2015.pdf)）。
- "读时注意"写得具体，每部分有回想题，小结要先回想再展开：依据前置问题（[元分析](https://link.springer.com/article/10.3758/s13423-023-02353-8)）和提取练习（[Dunlosky 等 2013](https://doi.org/10.1177/1529100612453266)）的研究。
- 公式解释默认折叠，让你先自己试着解释这一步（[self-explanation](https://link.aps.org/doi/10.1103/PhysRevPhysEducRes.18.010136)）。

## 已知限制

开发时主要用的是经济学、统计学和机器学习的论文，其他领域试得较少。遇到问题可以直接告诉 agent，也欢迎[提 issue](https://github.com/Liangzhen-Chen/literature-guide-read/issues)。

分段仍会出错，第 1b 步依靠 agent 发现并改正。有些 PDF 的文字层会错换或丢掉数学符号，符号要从裁图或页面图上读。以图片嵌入的图，旁边有图表编号时会自动裁图；矢量绘制的图要 agent 在第 1b 步框出才有裁图，否则要打开整页看。

## 许可

MIT。KaTeX（MIT）内置在 `assets/katex/`，详见 `THIRD_PARTY_NOTICES.md`。
