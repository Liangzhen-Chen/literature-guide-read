"""Shared helpers for the literature-guide-read scripts."""
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


def use_utf8():
    """Console encodings such as cp1252 cannot print the Chinese messages; replace what they cannot show."""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def clean_text(s):
    """Basic cleanup of extracted text: split ligatures, drop soft hyphens and zero-width marks."""
    s = "".join(LIGATURES.get(c, c) for c in s if c not in DROP)
    s = s.replace("\u00a0", " ").replace("\t", " ")
    return re.sub(r" {2,}", " ", s).strip()


# Old PDFs sometimes put a space after a ligature glyph: "signifi cant", "fi eld", "confl icts".
# The fix runs over the whole document, never one string, so it can ask for proof first.
_LIG_SPLIT = re.compile(r"(?<![A-Za-z])([A-Za-z]*(?:ffi|ffl|fi|fl|ff)) ([a-z]+)(?![A-Za-z])")
_LIG_NOT_SPLIT = {("wi", "fi"), ("hi", "fi"), ("sci", "fi"), ("fl", "oz")}  # Wi Fi, hi fi, sci fi, fl oz


def _is_ff(left):
    return left.endswith("ff")


def fix_split_ligatures(texts, min_hits=3):
    """Rejoin 'fi'/'fl'/'ffi'/'ffl'/'ff' ligatures that a text layer split from the rest of the word.
    texts: list of strings; returns a new list. Nothing changes unless the document shows the defect:
    at least min_hits fi/fl-type candidates in total (a bare 'ff' like "staff only" does not count). A candidate is skipped when its right part also occurs
    elsewhere as a word of its own (so "off ice" stays when "ice" is used), and an 'ff' candidate needs
    the joined word to occur intact elsewhere ("diff erent" is rejoined only if "different" appears)."""
    blob = "\n".join(texts)
    cands = list(_LIG_SPLIT.finditer(blob))
    if sum(not _is_ff(m.group(1)) for m in cands) < min_hits:
        return list(texts)
    # a stray "fi" after a name ("Sufi mystic") is no proof; the defect shows as a bare fragment, twice or more
    if sum(1 for m in cands if m.group(1) in ("fi", "fl", "ffi", "ffl", "ff")
           and (m.group(1).lower(), m.group(2)) not in _LIG_NOT_SPLIT
           and not re.search(r"\b(?:wi|hi|sci)\s$", m.string[max(0, m.start() - 4):m.start()], re.I)) < 2:
        return list(texts)
    rest, last = [], 0
    for m in cands:
        rest.append(blob[last:m.start()])
        last = m.end()
    rest.append(blob[last:])
    words = set(re.findall(r"[A-Za-z]+", "\n".join(rest)))

    def join(m):
        left, right = m.group(1), m.group(2)
        if right in words and len(right) > 1:  # a lone letter such as 'c' is always somewhere in a paper
            return m.group(0)
        prev = re.findall(r"[A-Za-z]+", m.string[max(0, m.start() - 6):m.start()])
        if (left.lower(), right) in _LIG_NOT_SPLIT or (prev and (prev[-1].lower(), left.lower()) in _LIG_NOT_SPLIT):
            return m.group(0)
        if _is_ff(left) and left + right not in words:
            return m.group(0)
        if left[0].isupper() and re.search(r"[^\s.?!]\s*$", m.string[:m.start()]):  # a name inside a sentence
            return m.group(0)
        return left + right

    # candidates inside a longer run are judged one by one, so a fixed list stays aligned with texts
    return [_LIG_SPLIT.sub(join, t) for t in texts]


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
REF_SKIP_RE = re.compile(r"\b(?:sections?|chapters?|parts?)\s?\d+(?:\.\d+)+\b|\b[PN]\d+\b|注\s?\d+|\b(?:figures?|figs?\.|tables?|notes?|footnotes?|experiments?|studies|study|"
                         r"questions?|problems?|sections?|chapters?|parts?|hypothes[ie]s|propositions?|equations?|eqs?\.|"
                         r"inequalit(?:y|ies)|expressions?|definitions?|lemmas?|theorems?|corollar(?:y|ies)|conditions?)\s?(?:\(\d+[a-z]?\)|\d+[a-z]?(?!\d|\s*[-–]\s*\d)\b)|"
                         r"(?:实验|研究|问题|题|假说|命题|公式|方程|不等式|定义|引理|定理|推论|条件)\s?\(?\d+[a-z]?\)?(?:\s*(?:到|至)\s*\(?\d+[a-z]?(?!\d|[.,]\d)\)?)?|式\s?\(\d+[a-z]?\)|"
                         r"[图表]\s?\d+(?!\d|[.,]\d)(?:\s*(?:到|至)\s*\d+(?!\d|[.,]\d))?|第\s?\d+(?:\.\d+)*(?:\(\d+\))?(?:\s*(?:[–-]|到|至)\s*\d+(?:\.\d+)*)?\s?[页节章部分条]|\bpp?\.\s?\d+(?:\s?[–-]\s?\d+)?", re.I)
# A number glued to a Chinese or Japanese character ("约为12.5%") is still a number; one glued to a letter ("x2", "P12") is not.
NUM_TOKEN_RE = re.compile(r"(?<![.]|[^\W　-鿿＀-￯])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)")
# Inline LaTeX in notes: $...$. A span that starts with a digit is money ("$50,000 against $60,000")
# unless it holds LaTeX or operators ("$1 + \eta$") or has no spaces at all ("$0$").
INLINE_MATH_RE = re.compile(r"\$(?![\s$])([^$\n]+?)(?<!\s)\$")
SCRIPT_RE = re.compile(r"[_^]\s*(?:\{[^{}]*\}|\S)")


def is_math_span(inner):
    return not inner[:1].isdigit() or bool(re.search(r"[\\_^=<>()]", inner)) or not re.search(r"\s", inner)


def inline_math_spans(text):
    """Matches of $...$ that are mathematics, left to right, never overlapping."""
    out, pos = [], 0
    while True:
        m = INLINE_MATH_RE.search(text or "", pos)
        if not m:
            return out
        if is_math_span(m.group(1)):
            out.append(m)
            pos = m.end()
        else:
            pos = m.start() + 1


def strip_math_notation(text):
    """Sub- and superscripts inside $...$ spans are notation (x_1, x^2), not data."""
    out, last = [], 0
    for m in inline_math_spans(text):
        out.append((text or "")[last:m.start()]); out.append(" " + SCRIPT_RE.sub(" ", m.group(1)) + " "); last = m.end()
    out.append((text or "")[last:])
    return "".join(out)


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


ORDINAL_NUMS = {"third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
                "eleventh": 11, "twelfth": 12, "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
                "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90}  # not "first"/"second": too common
TENS_RE = re.compile(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ](one|two|three|four|five|six|seven|eight|nine|"
                     r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\b", re.I)
SPLIT_DIGITS_RE = re.compile(r"(?<![\d.,])\d(?: \d)+(?![\d.,])")
MONTH_NAMES = {name.lower(): n for n, names in enumerate((
    ("January", "Jan"), ("February", "Feb"), ("March", "Mar"), ("April", "Apr"), ("May",),
    ("June", "Jun"), ("July", "Jul"), ("August", "Aug"), ("September", "Sep", "Sept"),
    ("October", "Oct"), ("November", "Nov"), ("December", "Dec")), 1) for name in names}
MONTH_NAME_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\.?(?![A-Za-z])", re.I)


SHORT_YEAR_RANGE_RE = re.compile(r"(?<!\d)(\d{4})\s*[-\u2013]\s*(\d{2})(?!\d)")


def source_numbers(text):
    """Numbers a source text states, including spelled-out ones ("three", "forty-eight", "twenty-fifth", "三") and numbers
    whose digits a text layer set apart ("1 0" for 10: only runs of single digits, never "25 75")."""
    out = numbers_in(text)
    for match in SHORT_YEAR_RANGE_RE.finditer(text or ""):
        start, end = map(int, match.groups())
        out.add(float(start // 100 * 100 + end + (100 if end < start % 100 else 0)))
    out.update(float(MONTH_NAMES[m.group(1).lower()]) for m in MONTH_NAME_RE.finditer(text or ""))
    merged = SPLIT_DIGITS_RE.sub(lambda m: m.group(0).replace(" ", ""), text or "")
    merged = re.sub(r"(?<=\d) (?=\.\d)", "", merged)  # a text layer that sets "62 .8" for 62.8
    if merged != (text or ""):
        out |= numbers_in(merged)
    for w in re.findall(r"[A-Za-z]+", text or ""):
        if w.lower() in WORD_NUMS:
            out.add(float(WORD_NUMS[w.lower()]))
        elif w.lower() in ORDINAL_NUMS:
            out.add(float(ORDINAL_NUMS[w.lower()]))
    units = dict(WORD_NUMS, **{"first": 1, "second": 2}, **ORDINAL_NUMS)
    for m in TENS_RE.finditer(text or ""):
        out.add(float(WORD_NUMS[m.group(1).lower()] + units[m.group(2).lower()]))
    for m in re.findall(r"[零〇一二两三四五六七八九十百千万]+", text or ""):
        out.add(float(_cn_value(m)))
    return out


def numbers_in(text):
    t = re.sub(r"(?<![.,]|[^\W　-鿿＀-￯])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d,]|\.\d|[ \u00a0\u202f]\d{3})",
               lambda m: re.sub(r"[ \u00a0\u202f]", "", m.group()), text or "")
    t = REF_SKIP_RE.sub(" ", strip_math_notation(t))
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


_DROP_CAP_LEAD = " \"'“‘(["


def put_drop_cap(text, cap):
    """Insert the drop cap word `cap` after any opening quote or bracket: '"ublished' -> '"Published'."""
    s = text.lstrip()
    n = len(s) - len(s.lstrip(_DROP_CAP_LEAD))
    return s[:n] + cap + s[n:]


def drop_cap_for(text, box, words, body, tol=4.0):
    """Find the drop cap that a paragraph's text lost. A drop cap is one enlarged capital letter set beside the first
    lines of a paragraph; text extraction and layout models both tend to leave it out, so the paragraph then starts
    with a lowercase fragment ("ublished research ..."). `box` is the paragraph's (x0, top, x1, bottom) in PDF points,
    `words` the page's words (dicts with text/x0/x1/top/bottom/size, as segment.get_words returns) and `body` the body
    font size. Returns the word to put back, or None when the paragraph does not look truncated."""
    s = text.lstrip(" \"'\u201c\u2018([")
    if not s or not s[0].islower() or not box:
        return None
    x0, top, x1, bottom = box
    best = None
    for w in words:
        t = w["text"]
        if len(t) != 1 or not ("A" <= t <= "Z") or w["size"] < 1.7 * body:
            continue
        h = w["bottom"] - w["top"]
        if (x0 - 1.5 * w["size"] <= w["x0"] <= x0 + tol and top - tol <= w["top"] <= top + 0.5 * h
                and (best is None or w["size"] > best["size"])):
            best = w
    return best
