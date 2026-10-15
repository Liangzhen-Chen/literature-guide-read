"""Shared helpers for the reading-guide scripts."""
import difflib
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
LANGS = ("zh", "en")
TIERS = ("close", "skim", "skip")
TIER_ALIASES = {"精读": "close", "略读": "skim", "可跳过": "skip"}
# Upper bound on the share of close-read paragraphs. Starting values; tune with use.
DENSITY = {"low": 0.15, "medium": 0.25, "high": 0.40}
DENSITY_ALIASES = {"低": "low", "中": "medium", "高": "high"}

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}
QUOTES = {"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
          "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
          "\u00ab": '"', "\u00bb": '"'}
DASHES = {c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"}
DROP = set("\u00ad\u200b\u200c\u200d\u2060\ufeff")


def clean_text(s):
    """Basic cleanup of extracted text: split ligatures, drop soft hyphens and zero-width marks."""
    s = "".join(LIGATURES.get(c, c) for c in s if c not in DROP)
    s = s.replace("\u00a0", " ").replace("\t", " ")
    return re.sub(r" {2,}", " ", s).strip()


def is_cjk(ch):
    return bool(ch) and ("\u3000" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff"
                         or "\uff00" <= ch <= "\uffef")


def _norm_with_map(s, drop_spaces=False):
    """Loose form of a string for matching, with a map back to original positions."""
    out, idx = [], []
    prev_space = True
    for i, ch in enumerate(s):
        if ch in DROP:
            continue
        rep = LIGATURES.get(ch) or QUOTES.get(ch) or DASHES.get(ch)
        if rep is None:
            if ch == "\u2026":
                rep = "..."
            elif ch.isspace():
                rep = " "
            else:
                rep = ch.casefold()
        for r in rep:
            if r == " ":
                if drop_spaces or prev_space:
                    continue
                prev_space = True
            else:
                prev_space = False
            out.append(r)
            idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def find_anchor(text, anchor):
    """Locate a verbatim anchor in a paragraph; returns (start, end) or None."""
    anchor = (anchor or "").strip().strip("\"'“”‘’")
    if not anchor:
        return None
    for drop in (False, True):
        nt, mt = _norm_with_map(text, drop)
        na, _ = _norm_with_map(anchor, drop)
        if not na:
            return None
        k = nt.find(na)
        if k >= 0:
            return mt[k], mt[k + len(na) - 1] + 1
    return None


def suggest_anchor(text, anchor, limit=160):
    parts = re.split(r"(?<=[.!?。！？])\s*", text)
    best, score = "", 0.0
    for p in parts:
        r = difflib.SequenceMatcher(None, p.lower(), (anchor or "").lower()).ratio()
        if r > score:
            best, score = p, r
    return best[:limit]


RANGE_RE = re.compile(r"^\s*P(\d+)\s*(?:[-–—~～至到]\s*P?(\d+))?\s*$", re.I)


def parse_range(r):
    m = RANGE_RE.match(str(r))
    if not m:
        raise ValueError(f"bad range {r!r}; write P3-P9 or P3")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if b < a:
        raise ValueError(f"range starts after it ends: {r!r}")
    return a, b


def fmt_range(a, b):
    return f"P{a}" if a == b else f"P{a}-P{b}"


def compress(nums):
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(fmt_range(nums[i], nums[j]))
        i = j + 1
    return ", ".join(out)


def pnum(pid):
    m = re.match(r"^P(\d+)$", str(pid))
    return int(m.group(1)) if m else None


# Numbers that are references rather than data: paragraph ids, figure/table/note numbers, page numbers.
REF_SKIP_RE = re.compile(r"\b[PN]\d+\b|注\s?\d+|\b(?:figures?|figs?\.|tables?|notes?|footnotes?|experiments?|studies|study|"
                         r"questions?|problems?|sections?|chapters?|parts?|hypothes[ie]s|propositions?|equations?|eqs?\.|"
                         r"inequalit(?:y|ies)|expressions?|definitions?|lemmas?|theorems?|corollar(?:y|ies)|conditions?)\s?\(?\d+[a-z]?\)?\b|"
                         r"(?:实验|研究|问题|题|假说|命题|公式|不等式|定义|引理|定理|推论|条件)\s?\(?\d+[a-z]?\)?|式\s?\(\d+[a-z]?\)|"
                         r"[图表]\s?\d+(?!\d|[.,]\d)|第\s?\d+\s?[页节章部分条]|\bpp?\.\s?\d+(?:\s?[–-]\s?\d+)?", re.I)
NUM_TOKEN_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)")


WORD_NUMS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
WORD_NUMS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                  "hundred": 100, "thousand": 1000, "million": 1e6, "billion": 1e9, "dozen": 12, "half": 0.5,
                  "twice": 2, "double": 2, "triple": 3})
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _cn_value(s):
    total, num, section = 0, 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if unit == 10000:
                section = (section + num) * unit
                total += section
                section = 0
            else:
                section += (num or 1) * unit
            num = 0
    return total + section + num


def source_numbers(text):
    """Numbers a source text states, including spelled-out ones ("three", "三")."""
    out = numbers_in(text)
    for w in re.findall(r"[A-Za-z]+", text or ""):
        if w.lower() in WORD_NUMS:
            out.add(float(WORD_NUMS[w.lower()]))
    for m in re.findall(r"[零〇一二两三四五六七八九十百千万]+", text or ""):
        out.add(float(_cn_value(m)))
    return out


def numbers_in(text):
    t = REF_SKIP_RE.sub(" ", text or "")
    # In explicit normal-distribution notation the comma separates parameters.
    # Leave ordinary grouped counts (including parenthesized counts) unchanged.
    t = re.sub(r"\bN\(\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*,\s*"
               r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*\)",
               lambda m: "N(" + m.group(1) + ", " + m.group(2) + ")", t)
    out = set()
    for m in NUM_TOKEN_RE.finditer(t):
        try:
            out.add(round(float(m.group(1).replace(",", "")), 6))
        except ValueError:
            pass
    return out


def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def as_lang(v, primary):
    """Text fields may be a plain string (the primary notes language) or {"zh": ..., "en": ...}."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return {k: str(x) for k, x in v.items() if k in LANGS and x is not None}
    return {primary: str(v)}


def load_elements():
    """Element types from references/elements.md: '### code | English | 中文 | level | family'."""
    path = SKILL_DIR / "references" / "elements.md"
    types, cur = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            parts = [p.strip() for p in line[4:].split("|")]
            if len(parts) == 5:
                code, en, zh, level, family = parts
                try:
                    level = int(level)
                except ValueError:
                    cur = None
                    continue
                cur = code
                types[code] = {"en": en, "zh": zh, "level": level, "family": family, "desc": ""}
            else:
                cur = None
        elif cur and line.strip() and not types[cur]["desc"]:
            types[cur]["desc"] = line.strip()
    return types


def skill_version():
    path = SKILL_DIR / "CHANGELOG.md"
    if path.exists():
        m = re.search(r"^##\s*([0-9][0-9.]*)", path.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return "?"


def load_json(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        lines = text.splitlines()
        ctx = lines[e.lineno - 1] if 0 < e.lineno <= len(lines) else ""
        sys.exit(f"JSON error in {path}, line {e.lineno} column {e.colno}: {e.msg}\n  {ctx[:200]}")


def load_guide(paths):
    """Merge guide.json with any number of paras_*.json files."""
    guide = {"paras": {}}
    for p in paths:
        d = load_json(p)
        if not isinstance(d, dict):
            sys.exit(f"{p}: the top level must be an object")
        for k, v in d.items():
            if k == "paras":
                if not isinstance(v, dict):
                    sys.exit(f"{p}: 'paras' must be an object keyed by paragraph id")
                for pid, note in v.items():
                    if pid in guide["paras"] and guide["paras"][pid] != note:
                        sys.exit(f"{pid} appears in more than one file with different content ({p})")
                    guide["paras"][pid] = note
            elif k in guide and guide[k] != v:
                sys.exit(f"field {k} appears in more than one file with different content ({p})")
            else:
                guide[k] = v
    return guide
