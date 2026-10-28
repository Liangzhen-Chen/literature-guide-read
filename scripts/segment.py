#!/usr/bin/env python3
"""把读物切成编号段落，供导读使用。

用法：
  python segment.py reading.pdf --out WORK
  python segment.py reading.pdf --out WORK --pages 3-28 --columns 2
  python segment.py reading.pdf --out WORK --ocr on          # 扫描件
  python segment.py reading.txt --text --out WORK            # 纯文本

纯文本格式：空行分段；以 # 开头的行是标题（# 一级，## 二级）；单独一行 [[p.12]] 表示下面的内容在第 12 页。

输出：
  WORK/paragraphs.json          全部条目（段落 P、标题 H、图表说明 C、脚注 N、碎片 F）
  WORK/paragraphs_partNN.txt    分块的可读文本，供逐块完整阅读
"""
import argparse
from io import BytesIO
import json
import math
import re
import statistics
import shutil
import importlib.util
import unicodedata
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import clean_text, drop_cap_for, fix_split_ligatures, is_cjk, put_drop_cap, use_utf8  # noqa: E402

CAPTION_RE = re.compile(r"^(fig(ure)?s?\.?|table|tab\.|exhibit|chart|plate|图|表)\s*[\dIVX]+(\.\d+)?\s*([.:：|—?]|$)", re.I)
NUM_HEAD_RE = re.compile(r"^(\d+(\.\d+){0,3}|[IVXLC]+|[A-H])[.)]?\s+(\S)")
NUM_PREFIX_RE = re.compile(r"^(\d+(\.\d+){0,3}|[IVXLC]+|[A-H])[.)]?\s+")
REF_RE = re.compile(r"^(references?|bibliography|works cited|literature cited|reference list|参考文献|引用文献)$", re.I)
NOTES_RE = re.compile(r"^(notes|endnotes|注释|尾注)$", re.I)
APPX_RE = re.compile(r"^(appendix|appendices|附录)\b", re.I)
PAGE_NUM_RE = re.compile(r"^[\s\-–—|]*(?:page\s+)?(\d{1,4}|[ivxlcdm]{1,7})[\s\-–—|]*$", re.I)
BANNER_RE = re.compile(r"\b(vol\.|volume|pages|pp\.)\s*\d", re.I)
CAPTION_TITLE_RE = re.compile(r"^(?i:fig(ure)?\.?|table|exhibit|chart|图|表)\s*\d+(\.\d+)?(\s+[A-Z]|\s*[\u4e00-\u9fff])")
KNOWN_HEAD_RE = re.compile(r"^(abstract|introduction|background|literature review|methods?|data|results|discussion|"
                           r"conclusions?|concluding remarks|commentary|summary|acknowledg(e)?ments?|references|"
                           r"bibliography|appendix|notes|摘要|引言|前言|导论|绪论|结论|结语|讨论|致谢|附录|参考文献)$", re.I)
CN_HEAD_RE = re.compile(r"^(第[一二三四五六七八九十百零〇\d]+[章节部篇]|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])")
CIRCLED_RE = re.compile(r"[\u2460-\u2473]")
SUP_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
SMALL_WORDS = {"a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with", "by", "at", "from", "as", "vs", "via"}
MONO_RE = re.compile(r"mono|courier|cmtt|consol|menlo|inconsolata|sftt|typewriter|nimbusmon", re.I)
JSTOR_RE = re.compile(r"your use of the jstor archive|jstor is a not-for-profit", re.I)
STAT_RE = re.compile(r"^[Nn]\s*=\s*\d")
TERMINAL = set(".?!:;。！？；：…")
CLOSERS = "\"'”’)]）」』*†‡ "
STOP_END = {"the", "a", "an", "of", "to", "in", "on", "by", "for", "and", "or", "with", "as",
            "at", "from", "that", "which", "is", "are", "was", "were", "be", "this", "these",
            "its", "their", "his", "her", "our", "not", "but", "than", "into", "between"}


# ---------- 文本小工具 ----------

def end_terminal(text):
    t = re.sub(r"([.!?。！？”\"’)\]])\s*\d{1,3}$", r"\1", text.rstrip())  # 去掉句末脚注号
    t = t.rstrip(CLOSERS)
    return bool(t) and t[-1] in TERMINAL


def starts_lower(text):
    s = text.lstrip(" \"'“‘([")
    return bool(s) and s[0].islower()


def last_word(text):
    m = re.search(r"([A-Za-z]+)\W*$", text)
    return m.group(1).lower() if m else ""


MASTHEAD_RE = re.compile(r"\b(vol\.|volume|issue|no\.)\s*[\dIVXLCM]+", re.I)
TABLE_NOTE_RE = re.compile(r"^((notes?|source|sources)\s*:|\*{1,3}\s*(p\s*[<=]|significant))", re.I)
ACCENT_RE = re.compile(r"^[̀-ͯˆ-˟¨´`]+$")
PUNCT_TOKEN_RE = re.compile(r"^[)\]},;:.!?’”]+$")


def join_words(a, b):
    if not a:
        return b
    if is_cjk(a[-1]) and is_cjk(b[:1]):
        return a + b
    if a[-1] in "([{" or PUNCT_TOKEN_RE.match(b):
        return a + b
    if ACCENT_RE.match(b) or ACCENT_RE.match(a[-1]):
        return unicodedata.normalize("NFC", a + b)  # an accent set as a word of its own: "Ko" "̋" "szegi"  # a bracket or punctuation mark set as a word of its own belongs to its neighbour
    return a + " " + b


HY = ""  # marks a line-end hyphen that was dropped; resolve_hyphens decides, per document, whether it was part of the word


def join_text(a, b, mark=False):
    if not a:
        return b
    if not b:
        return a
    if a.endswith("-") and len(a) > 1 and a[-2].isalpha() and b[:1].islower():
        return a[:-1] + (HY if mark else "") + b
    if is_cjk(a[-1]) and is_cjk(b[0]):
        return a + b
    return a + " " + b


def join_marked(a, b):
    return join_text(a, b, mark=True)


NUMBER_WORDS = set("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                   "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million "
                   "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth twentieth "
                   "thirtieth fortieth fiftieth half".split())
HY_TOKEN_RE = re.compile("[A-Za-z]+(?:-[A-Za-z]+)*")


def resolve_hyphens(texts):
    """Decide for every dropped line-end hyphen whether it belonged to the word, using the document as evidence.
    Keep it when both pieces are number words ("twenty-fifth"), when the document writes the hyphenated form elsewhere,
    when the word before the break is already a compound and the next piece is a word ("out-of-" "pocket"), when the
    second piece has a hyphen itself, or when both pieces occur as words and the closed form never does. Drop it when the
    document writes the closed form elsewhere ("refer-" "ence-dependent"). With no evidence it is dropped, as before.
    Returns the texts without markers and the decisions as (closed, hyphenated, kept)."""
    if not any(HY in x for x in texts):
        return list(texts), []
    tokens, pieces = set(), Counter()
    for x in texts:
        for w in HY_TOKEN_RE.findall(re.sub("[A-Za-z-]*" + HY + "[A-Za-z-]*", " ", x)):
            tokens.add(w.lower())
            for part in w.lower().split("-"):
                pieces[part] += 1
    joined = " " + " ".join(sorted(tokens))
    decisions, out = [], []
    for x in texts:
        while HY in x:
            k = x.index(HY)
            left = re.search("[A-Za-z-]*$", x[:k]).group(0)
            right = re.match("[A-Za-z-]*", x[k + 1:]).group(0)
            first, rfirst = left.lower().split("-")[-1], right.lower().split("-")[0]
            stem, hyph = first + rfirst, first + "-" + rfirst
            if first in NUMBER_WORDS and rfirst in NUMBER_WORDS:
                keep = True
            elif (" " + hyph) in joined:
                keep = True
            elif pieces[stem] or (len(stem) >= 6 and any(p.startswith(stem) for p in pieces)):
                keep = False
            elif "-" in left:
                keep = len(rfirst) >= 4 or bool(pieces[rfirst]) or "-" in right
            elif "-" in right:
                keep = True
            else:
                keep = bool(pieces[first] and pieces[rfirst] and len(first) > 2 and len(rfirst) > 2)
            decisions.append((left + right, left + "-" + right, keep))
            x = x[:k] + ("-" if keep else "") + x[k + 1:]
        out.append(x)
    return out, decisions


def word_count(text):
    cjk = sum(1 for ch in text if is_cjk(ch))
    return len(text.split()) + cjk // 2


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages += list(range(int(a), min(int(b), n) + 1))
        elif part:
            pages.append(int(part))
    return [p for p in pages if 1 <= p <= n]


# ---------- PDF 文字层 ----------

SPACING_ACCENTS = {"¨": "̈", "˝": "̋", "ˆ": "̂", "˜": "̃",
                   "ˇ": "̌", "¯": "̄"}
SPACING_ACCENT_RE = re.compile("([A-Za-z])([" + "".join(SPACING_ACCENTS) + "])")


def compose_accents(text):
    """Old fonts set an accent as a character after its letter ("Ko¨bberling"): put the accented letter back."""
    def one(m):
        c = unicodedata.normalize("NFC", m.group(1) + SPACING_ACCENTS[m.group(2)])
        return c if len(c) == 1 else m.group(0)
    return SPACING_ACCENT_RE.sub(one, text)


def level_glyph_boxes(page):
    """Give every glyph the vertical extent its baseline implies. A font whose metrics are wrong (math and symbol fonts
    that hold the parentheses of a title) reports a box 10pt below its neighbours although the glyph sits on the same
    baseline, so the parenthesis becomes a line of its own. Only glyphs far from the usual extent are moved."""
    try:
        chars = page.chars
        bottom_edge = float(page.bbox[3])
    except Exception:
        return
    for c in chars:
        m, size = c.get("matrix"), float(c.get("size") or 0)
        if not m or size <= 0 or not c.get("upright", True):
            continue
        base = bottom_edge - float(m[5])
        if abs((base - float(c["top"])) - 0.8 * size) > 0.3 * size:
            c["top"] = base - 0.8 * size
            c["bottom"] = c["top"] + size
            c["y1"] = bottom_edge - c["top"]
            c["y0"] = bottom_edge - c["bottom"]


def text_width_reference(pdf, pnos):
    """Learn glyph advances from in-page text, keyed by font and character."""
    widths = defaultdict(list)
    for pno in pnos:
        page = pdf.pages[pno - 1]
        apply_native_case(page, font_properties(page))
        for c in getattr(page, "chars", []):
            if c.get("size", 0) > 0 and page.bbox[0] <= c["x0"] < c["x1"] <= page.bbox[2]:
                widths[(c.get("fontname"), c["text"])].append((c["x1"] - c["x0"]) / c["size"])
    return {k: statistics.median(v) for k, v in widths.items()}


def repair_stretched_text(page, reference):
    """Repair overflowing OCR spans from repeated glyph metrics, never fit to a page edge.

    PDF marked-content spans and baselines delimit independently positioned text.
    Only overflowing spans with a consistently enlarged advance are transformed.
    """
    groups = defaultdict(list)
    for c in getattr(page, "chars", []):
        groups[(c.get("mcid"), round(c["top"]), c.get("fontname"))].append(c)
    for chars in groups.values():
        if max(c["x1"] for c in chars) <= page.bbox[2]:
            continue
        ratios = [(c["x1"] - c["x0"]) / c["size"] / reference[(c.get("fontname"), c["text"])]
                  for c in chars if c.get("size", 0) > 0 and reference.get((c.get("fontname"), c["text"]), 0) > 0]
        if not ratios:
            continue
        scale = statistics.median(ratios)
        # A robust three-deviation test distinguishes systematic scale from glyph variation.
        deviation = statistics.median(abs(r - scale) for r in ratios)
        if (scale <= 1 or abs(scale - 1) < 1e-6 or scale - 1 <= 3 * 1.4826 * deviation
                or len({c["text"] for c in chars}) < 3):
            continue
        origin = min(c["x0"] for c in chars)
        for c in chars:
            c["x0"] = origin + (c["x0"] - origin) / scale
            c["x1"] = origin + (c["x1"] - origin) / scale
            c["width"] = c["x1"] - c["x0"]


def font_name_style(name):
    """Fallback PostScript style names, including delimited B/Bd/I/It abbreviations.

    Delimiters matter: a family name that happens to end in b or i is not a style.
    Embedded descriptors/program metadata remain additional independent evidence.
    """
    bold = bool(re.search(r"bold|black|heavy|semibold|demi|medi|[.,_-](?:b|bd|bi|bdi|bdit)\d*$", name, re.I))
    italic = bool(re.search(r"italic|oblique|[.,_-](?:i|it|bi|ib|bdi|bdit)\d*$", name, re.I))
    return bold, italic


def font_properties(page):
    """Read style and case evidence from PDF descriptors and embedded font metadata.

    Font program weights use the OpenType 100–900 scale. Case repairs require
    agreement between the simple-font encoding and its glyph advance, rather than
    changing mixed case by appearance or vocabulary.
    """
    try:
        from pdfminer.pdftypes import resolve1
        from pdfminer.psparser import literal_name
        from pdfminer.encodingdb import EncodingDB
        from pdfminer.cmapdb import CMapParser, FileUnicodeMap
        fonts = resolve1(page.page_obj.resources.get("Font", {}))
    except (AttributeError, KeyError, TypeError):
        return {}
    cache = getattr(page.pdf, "_segment_fonts", {})
    page.pdf._segment_fonts = cache
    result = {}
    for resource in fonts.values():
        try:
            spec = resolve1(resource)
            name = literal_name(spec["BaseFont"])
            if name in cache:
                result[name] = cache[name]
                continue
            desc_spec = resolve1(resolve1(spec.get("DescendantFonts", [spec]))[0])
            desc = resolve1(desc_spec.get("FontDescriptor", {}))
            props = dict(bold=desc.get("FontWeight", 0) >= 600 or bool(desc.get("Flags", 0) & (1 << 18)),
                         italic=bool(desc.get("ItalicAngle", 0)), smallcaps=bool(desc.get("Flags", 0) & (1 << 17)), cases={}, case_cids={})
            stream = resolve1(desc.get("FontFile2") or desc.get("FontFile3"))
            if stream is not None:
                try:
                    from fontTools.ttLib import TTFont
                    from fontTools.cffLib import CFFFontSet
                    data = stream.get_data()
                    if data[:4] in (b"OTTO", b"\x00\x01\x00\x00", b"true"):
                        font = TTFont(BytesIO(data))
                        if "OS/2" in font:
                            props["bold"] |= font["OS/2"].usWeightClass >= 600
                            props["italic"] |= bool(font["OS/2"].fsSelection & (1 | (1 << 9)))
                        if "post" in font:
                            props["italic"] |= bool(font["post"].italicAngle)
                    else:
                        cff = CFFFontSet()
                        cff.decompile(BytesIO(data), None)
                        top = cff[cff.fontNames[0]]
                        props["bold"] |= bool(re.search(r"bold|black|heavy|demi", getattr(top, "Weight", ""), re.I))
                        props["italic"] |= bool(getattr(top, "ItalicAngle", 0))
                except Exception:
                    pass  # damaged/unsupported font programs still have descriptor/name evidence
            if spec.get("ToUnicode") and spec.get("Widths") and spec.get("Encoding"):
                enc = resolve1(spec["Encoding"])
                if isinstance(enc, dict):
                    native = EncodingDB.get_encoding(literal_name(enc.get("BaseEncoding")), enc.get("Differences", []))
                else:
                    native = EncodingDB.get_encoding(literal_name(enc))
                cmap = FileUnicodeMap()
                CMapParser(cmap, BytesIO(resolve1(spec["ToUnicode"]).get_data())).run()
                widths = resolve1(spec["Widths"])
                first = spec.get("FirstChar", 0)
                for cid, decoded in cmap.cid2unichr.items():
                    glyph = native.get(cid, "")
                    if (len(decoded) == len(glyph) == 1 and decoded.isalpha()
                            and decoded.casefold() == glyph.casefold() and first <= cid < first + len(widths)):
                        props["cases"].setdefault(decoded, []).append((glyph, float(widths[cid - first]) / 1000))
                        if decoded != glyph:
                            props["case_cids"][cid] = glyph
            cache[name] = result[name] = props
        except Exception:
            continue
    return result


def repair_case_cids(font, replacements):
    """With character codes available, case-only Encoding/ToUnicode conflicts are exact."""
    cmap = getattr(font, "unicode_map", None)
    if cmap is not None:
        cmap.cid2unichr.update(replacements)


def apply_native_case(page, props):
    if getattr(page, "_segment_case_applied", False) or not any(p.get("case_cids") for p in props.values()):
        return
    try:
        from pdfminer.pdftypes import resolve1
        from pdfminer.psparser import literal_name
        for resource in resolve1(page.page_obj.resources.get("Font", {})).values():
            spec = resolve1(resource)
            replacements = props.get(literal_name(spec["BaseFont"]), {}).get("case_cids", {})
            if replacements:
                font = page.pdf.rsrcmgr.get_font(getattr(resource, "objid", None), spec)
                repair_case_cids(font, replacements)
        # Re-decode cached characters using their actual character codes. Equal
        # advances (for example a wide lower-case glyph and its capital) are no
        # longer ambiguous, and the original PDF remains untouched.
        page.flush_cache()
        page._segment_case_applied = True
    except (AttributeError, KeyError, TypeError):
        pass


def repair_case_maps(chars, fonts):
    for c in chars:
        if not c.get("size") or not c.get("upright", True):
            continue
        candidates = fonts.get(c.get("fontname"), {}).get("cases", {}).get(c["text"], [])
        advance = (c["x1"] - c["x0"]) / c["size"]
        matches = {glyph for glyph, width in candidates if math.isclose(width, advance, rel_tol=1e-4, abs_tol=1e-6)}
        if len(matches) == 1:
            c["text"] = matches.pop()


def get_words(page):
    props = font_properties(page)
    apply_native_case(page, props)
    repair_case_maps(getattr(page, "chars", []), props)
    level_glyph_boxes(page)
    try:  # 按字号比例判断词间距；没有编码空格的 PDF（常见于 TeX）也能正确分词
        ws = page.extract_words(x_tolerance_ratio=0.15, keep_blank_chars=False,
                                use_text_flow=False, extra_attrs=["size", "fontname"])
    except TypeError:  # 旧版 pdfplumber
        ws = page.extract_words(x_tolerance=1.5, keep_blank_chars=False,
                                use_text_flow=False, extra_attrs=["size", "fontname"])
    out, unmapped = [], []
    # pdfplumber reports coordinates in a frame whose origin is page.bbox, not the page corner; a MediaBox
    # that does not start at (0, 0) (JSTOR scans) would otherwise shift margins, crops and every bbox.
    ox, oy = float(page.bbox[0]), float(page.bbox[1])
    for w in ws:
        if not w.get("upright", True):
            continue  # 侧边竖排水印等
        t = compose_accents(clean_text(w["text"]))
        if "(cid:" in t:
            unmapped.append((float(w["x0"]) - ox, float(w["x1"]) - ox,
                             float(w["top"]) - oy, float(w["bottom"]) - oy))
        if not t or "(cid:" in t:
            continue  # 无法映射的字形（常见于 JSTOR 水印）
        if (float(w["x1"]) - ox < 0 or float(w["x0"]) - ox > float(page.width)
                or float(w["bottom"]) - oy < 0 or float(w["top"]) - oy > float(page.height)):
            continue  # text placed outside the page (a contents panel parked off-screen) is never seen by the reader
        out.append({
            "text": t, "x0": float(w["x0"]) - ox, "x1": float(w["x1"]) - ox,
            "top": float(w["top"]) - oy, "bottom": float(w["bottom"]) - oy,
            "size": round(float(w["size"]), 2),
            "bold": props.get(w["fontname"], {}).get("bold", False) or font_name_style(w["fontname"])[0],
            "italic": props.get(w["fontname"], {}).get("italic", False) or font_name_style(w["fontname"])[1],
            "smallcaps": props.get(w["fontname"], {}).get("smallcaps", False) or bool(re.search(r"smallcaps|small.capitals|[.-]sc$", w["fontname"], re.I)),
            "font": w["fontname"],
            "mono": bool(MONO_RE.search(w["fontname"])),
        })
    gaps = [(b["x0"] - a["x1"]) / a["size"] for a, b in zip(out, out[1:])
            if len(a["text"]) > 1 and len(b["text"]) > 1 and a.get("font") == b.get("font")
            and a["size"] == b["size"] and abs(a["bottom"] - b["bottom"]) <= 0.15 * a["size"]
            and 0 < b["x0"] - a["x1"] < a["size"]]
    # Unmapped visible operators still occupy the gap: they are not tracking.
    if unmapped:
        for w in out:
            w["unmapped_boxes"] = unmapped
    if gaps:
        word_gap = statistics.median(gaps)
        for w in out:
            w["word_gap"] = word_gap
    return out


def join_tracked_words(words):
    """Recover tracking from end-to-start gaps, as in pdfplumber's WordExtractor.

    A same-style run with repeated singleton gaps needs a uniform narrow population separated
    from observed word/group gaps. No lexical evidence or label vocabulary is used.
    Already joined letter fragments participate in that same gap population.
    With no evidence of word spacing, an ambiguous isolated run is left alone.
    """
    out, i = [], 0
    while i < len(words):
        j = i
        while (j < len(words) and words[j]["text"].isalpha()
               and words[j].get("font") == words[i].get("font")
               and words[j]["size"] == words[i]["size"]
               and abs(words[j]["bottom"] - words[i]["bottom"]) <= 1e-6 * words[i]["size"]
               and (j == i or not any(
                   box[0] < words[j]["x0"] and box[1] > words[j - 1]["x1"]
                   and box[2] < words[j]["bottom"] and box[3] > words[j]["top"]
                   for box in words[j].get("unmapped_boxes", [])))):
            j += 1
        if j - i < 3:
            out.append(words[i])
            i += 1
            continue
        run = words[i:j]
        gaps = [b["x0"] - a["x1"] for a, b in zip(run, run[1:])]
        singleton_gaps = [gap for gap, a, b in zip(gaps, run, run[1:])
                          if len(a["text"]) == len(b["text"]) == 1 and gap > 0]
        if len(singleton_gaps) < 2:
            out.extend(run)
            i = j
            continue
        positive = sorted(g for g in gaps if g > 0)
        epsilon = 1e-6 * run[0]["size"]
        if not positive:
            out.extend(run)
            i = j
            continue
        # The largest break in the gap distribution proposes two populations.
        # Accept it only when their robust three-sigma intervals are separated.
        small = positive
        boundaries = [w["word_gap"] * w["size"] for w in run if w.get("word_gap")]
        for a, b in ((words[i - 1], run[0]),) if i else ():
            if a.get("font") == b.get("font"):
                boundaries.append(b["x0"] - a["x1"])
        if j < len(words) and words[j].get("font") == run[-1].get("font"):
            boundaries.append(words[j]["x0"] - run[-1]["x1"])
        if len(positive) > 2:
            cut = max(range(2, len(positive)), key=lambda k: positive[k] - positive[k - 1])
            low = positive[:cut]
            centre = statistics.median(low)
            spread = 1.4826 * statistics.median(abs(g - centre) for g in low)
            if positive[cut] >= 2 * max(low) and positive[cut] > centre + 3 * spread + epsilon:
                small = low
                boundaries.append(positive[cut])
        centre = statistics.median(small)
        spread = 1.4826 * statistics.median(abs(g - centre) for g in small)
        upper = centre + 3 * spread + epsilon
        uniform_votes = sum(abs(g - centre) <= 3 * spread + epsilon for g in singleton_gaps)
        if spread >= centre or uniform_votes < 2 or not any(g > upper for g in boundaries):
            out.extend(run)
            i = j
            continue
        groups = [[run[0]]]
        for gap, w in zip(gaps, run[1:]):
            if 0 < gap <= upper:  # kerning can narrow a letter gap, never turn it into a word gap
                groups[-1].append(w)
            else:
                groups.append([w])
        for group in groups:
            out.append(dict(group[0], text="".join(w["text"] for w in group), x1=group[-1]["x1"],
                            top=min(w["top"] for w in group), bottom=max(w["bottom"] for w in group)))
        i = j
    return out


def line_from_words(ws):
    ws = join_tracked_words(sorted(ws, key=lambda w: w["x0"]))
    text, prev, superscripts = "", None, []
    for w in ws:
        if (prev is not None and w["x0"] - prev["x1"] < 0.1 * max(w["size"], prev["size"])
                and (w["size"] != prev["size"] or w.get("font") != prev.get("font"))
                and (prev["text"][-1:] in ")]" or w["text"][:1] in "([" or (
                    prev["text"].isalpha() and w["text"].isalpha() and w["size"] != prev["size"]
                    and not w["text"].isdigit() and not prev["text"].isdigit()
                    and abs(w["bottom"] - prev["bottom"]) <= 0.12 * max(w["size"], prev["size"])))):
            # words are split where the font or size changes; when they touch there was no space between them:
            # a word with its brackets set in a math font, or a small-caps "R" + "EFERENCES" on one baseline
            text += w["text"]
        elif (prev is not None and w["text"].isdigit() and w["size"] < prev["size"]
              and w["bottom"] < prev["bottom"]
              and (len(re.findall(r"[A-Za-z]", prev["text"])) >= 3 or prev["text"][-1:] in ".,;:!?")):
            superscripts.append((prev["text"], w["text"]))
            text = join_words(text, w["text"])
        else:
            text = join_words(text, w["text"])
        prev = w
    weights = [(w["size"], len(w["text"])) for w in ws]
    total = sum(n for _, n in weights) or 1
    acc, size = 0, weights[0][0]
    for s, n in sorted(weights):
        acc += n
        if acc >= total / 2:
            size = s
            break
    bold = sum(len(w["text"]) for w in ws if w.get("bold")) / total
    italic = sum(len(w["text"]) for w in ws if w.get("italic")) / total
    mono = sum(len(w["text"]) for w in ws if w.get("mono")) / total
    return {"text": text, "x0": ws[0]["x0"], "x1": max(w["x1"] for w in ws),
            "top": min(w["top"] for w in ws), "bottom": max(w["bottom"] for w in ws),
            "size": size, "bold": bold, "italic": italic, "mono": mono, "words": ws, "superscripts": superscripts, "font": ws[0].get("font", ""),
            "text_box": ws[0].get("text_box") if all(w.get("text_box") == ws[0].get("text_box") for w in ws) else None}


def make_lines(words, gap_split=False):
    """按纵向重叠把词归成行；gap_split 时在大空隙处断开（用于识别分栏）。"""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    clusters = []
    for w in ws:
        h = max(0.1, w["bottom"] - w["top"])
        target = None
        for c in reversed(clusters[-8:]):
            ov = min(c["bottom"], w["bottom"]) - max(c["top"], w["top"])
            if ov > 0 and ov >= 0.5 * min(h, c["bottom"] - c["top"]):
                target = c
                break
        if target is None:
            target = {"words": [], "top": w["top"], "bottom": w["bottom"]}
            clusters.append(target)
        target["words"].append(w)
        target["top"] = min(target["top"], w["top"])
        target["bottom"] = max(target["bottom"], w["bottom"])
    out = []
    for c in clusters:
        row = sorted(c["words"], key=lambda w: w["x0"])
        groups = [[row[0]]]
        for w in row[1:]:
            prev = groups[-1][-1]
            gap = w["x0"] - prev["x1"]
            if gap_split and gap > max(0.9 * max(prev["size"], w["size"]), 7.0):
                groups.append([w])
            else:
                groups[-1].append(w)
        out += [line_from_words(g) for g in groups]
    return sorted(out, key=lambda l: (l["top"], l["x0"]))


def body_size(words):
    cnt = Counter()
    for w in words:
        cnt[round(w["size"] * 2) / 2] += len(w["text"])
    return cnt.most_common(1)[0][0] if cnt else 10.0


def split_by_edges(bs, width):
    """双栏的左栏和右栏各有一条整齐的左边线：找第二条边线，并确认左栏的行不越过它。"""
    xs = [s["x0"] for s in bs if len(s["text"]) >= 15]
    if len(xs) < 12:
        return None
    def count_near(x):
        return sum(1 for v in xs if abs(v - x) <= 3)
    cands = sorted({round(v / 2) * 2 for v in xs})
    left = [c for c in cands if c < 0.4 * width]
    if not left:
        return None
    l1 = max(left, key=count_near)
    c1 = count_near(l1)
    right = [c for c in cands if 0.4 * width <= c <= 0.65 * width and c > l1 + 0.25 * width]
    if not right:
        return None
    l2 = max(right, key=count_near)
    c2 = count_near(l2)
    if c2 < max(5, 0.25 * c1):
        return None
    left_lines = [s for s in bs if abs(s["x0"] - l1) <= 3 and len(s["text"]) >= 15]
    inside = [s for s in left_lines if s["x1"] < l2 - 3]
    if len(inside) < 0.6 * len(left_lines):
        return None
    ends = sorted(s["x1"] for s in inside)
    r1 = ends[int(len(ends) * 0.9)] if ends else l2 - 10
    return (r1 + l2) / 2 if r1 < l2 else l2 - 4


def detect_sidebar(segs, width):
    """Find a narrow, smaller-font left metadata column separated by a gutter."""
    candidates = sorted({round(x["x0"]) for x in segs
                         if 0.25 * width <= x["x0"] <= 0.45 * width})
    for edge in candidates:
        right = [x for x in segs if abs(x["x0"] - edge) <= 3 and len(x["text"]) >= 20]
        left = [x for x in segs if x["x1"] < edge - 6 and len(x["text"]) >= 20]
        if len(right) < 6 or len(left) < 6:
            continue
        if statistics.median(x["size"] for x in left) >= 0.9 * statistics.median(x["size"] for x in right):
            continue
        # Require vertical overlap: an author block above the article is not a sidebar.
        overlap = min(max(x["bottom"] for x in left), max(x["bottom"] for x in right)) - max(min(x["top"] for x in left), min(x["top"] for x in right))
        if overlap < 60:
            continue
        return (max(x["x1"] for x in left) + edge) / 2
    return None


def detect_split(segs, width, body, force=False):
    tol = max(1.0, 0.15 * body)
    bs = [s for s in segs if abs(s["size"] - body) <= tol and len(s["text"]) >= 4
          and s.get("mono", 0) < 0.5]
    edge = split_by_edges(bs, width)
    if edge is not None:
        return edge
    if len(bs) < 10 and not force:
        return None
    nb = int(width / 2) + 2
    cov = [0] * nb
    for s in bs:
        for b in range(max(0, int(s["x0"] / 2)), min(nb, int(s["x1"] / 2) + 1)):
            cov[b] += 1
    inner = sorted(cov[int(width * 0.1 / 2): int(width * 0.9 / 2)])
    peak = inner[int(len(inner) * 0.8)] if inner else 0
    thresh = 0.25 * peak
    lo, hi = int(width * 0.3 / 2), int(width * 0.7 / 2)
    best, start = None, None
    for b in range(lo, hi + 2):
        low = b <= hi and cov[b] <= thresh
        if low and start is None:
            start = b
        elif not low and start is not None:
            if best is None or b - start > best[1]:
                best = (start, b - start)
            start = None
    if best and best[1] * 2 >= 6:
        split = (best[0] + best[1] / 2) * 2
        left = sum(1 for s in bs if s["x1"] <= split + 2)
        right = sum(1 for s in bs if s["x0"] >= split - 2)
        if left >= 6 and right >= 6:
            return split
    return width / 2 if force else None


def order_lines(words, segs, split):
    if split is None:
        lines = make_lines(words)
        for ln in lines:
            ln["col"], ln["band"] = 0, 0
        return lines
    left, right, full = [], [], []
    for s in segs:
        if s["x1"] <= split + 2:
            left.append(s)
        elif s["x0"] >= split - 2:
            right.append(s)
        else:
            full.append(s)
    full.sort(key=lambda s: s["top"])
    bounds = [f["top"] for f in full] + [float("inf")]
    out, prev, band, full_band = [], -float("inf"), 0, None
    for i, bound in enumerate(bounds):
        seg_l = [s for s in left if prev <= s["top"] < bound]
        seg_r = [s for s in right if prev <= s["top"] < bound]
        if seg_l or seg_r:
            band += 1
            for col, group in ((1, seg_l), (2, seg_r)):
                if group:
                    for ln in make_lines([w for s in group for w in s["words"]]):
                        ln["col"], ln["band"] = col, band
                        out.append(ln)
            full_band = None
        if i < len(full):
            if full_band is None:
                band += 1
                full_band = band
            f = full[i]
            f["col"], f["band"] = 0, full_band
            out.append(f)
            prev = f["top"]
    return out


def column_gutters(segs, width, body, force=False):
    """x positions of the gutters between text columns, found from where body-size lines leave the page empty.

    Full-width blocks (title, abstract, wide tables, running heads) are not body size or are few, so they
    do not hide a gutter. Returns [] for a single column, one value for two columns, two for three, and so on.
    With force, a page that shows no clear gutters is cut into equal thirds."""
    tol = max(1.0, 0.15 * body)
    # body size and smaller: reference lists and footnotes set in a smaller type still lie in the columns
    bs = [s for s in segs if 0.6 * body <= s["size"] <= body + tol and len(s["text"]) >= 4 and s.get("mono", 0) < 0.5]
    if len(bs) < 10:
        return [width / 3, 2 * width / 3] if force else []
    nb = int(width / 2) + 2
    cov = [0] * nb
    for s in bs:
        for b in range(max(0, int(s["x0"] / 2)), min(nb, int(s["x1"] / 2) + 1)):
            cov[b] += 1
    inner = sorted(cov[int(width * 0.08 / 2): int(width * 0.92 / 2)])
    peak = inner[int(len(inner) * 0.8)] if inner else 0
    thresh = 0.25 * peak
    filled = [b for b in range(nb) if cov[b] > thresh]
    runs = []
    if filled:
        start = None
        for b in range(filled[0], filled[-1] + 2):
            low = b <= filled[-1] and cov[b] <= thresh
            if low and start is None:
                start = b
            elif not low and start is not None:
                if (b - start) * 2 >= 6:
                    runs.append(((start + b) / 2 * 2, b - start))
                start = None
    gutters = sorted(g for g, _ in runs)
    widths = dict(runs)

    span = max(s["bottom"] for s in bs) - min(s["top"] for s in bs)

    def valid(gs):
        edges = [-1e9] + gs + [1e9]
        for a, b in zip(edges, edges[1:]):
            inside = sum(1 for s in bs if s["x0"] >= a - 2 and s["x1"] <= b + 2)
            if inside < max(5, 0.08 * len(bs)):
                return False
            col = [s for s in bs if s["x0"] >= a - 2 and s["x1"] <= b + 2]
            # a real column runs down most of the text area; a short list or a table set in columns does not
            if max(s["bottom"] for s in col) - min(s["top"] for s in col) < 0.3 * span:
                return False
        crossing = sum(1 for s in bs if any(s["x0"] < g - 1 and s["x1"] > g + 1 for g in gs))
        return crossing <= 0.2 * len(bs)

    while gutters and not valid(gutters):
        gutters.remove(min(gutters, key=lambda g: widths[g]))
    if force and len(gutters) < 2:
        return [width / 3, 2 * width / 3]
    return gutters


def slabs_by_gap(segs, thr):
    """Split segments into horizontal slabs wherever a whole row of the region is empty for at least thr."""
    out, cur, reach, big = [], [], None, 0.0  # big: size of the line that reaches lowest
    for s in sorted(segs, key=lambda s: (s["top"], s["x0"])):
        # the gap must also beat the line spacing of large type: the lines of a 25pt title are 5pt apart
        if cur and s["top"] - reach >= max(thr, 0.5 * max(big, s["size"])):
            out.append(cur)
            cur, reach, big = [], None, 0.0
        cur.append(s)
        if reach is None or s["bottom"] > reach:
            reach, big = s["bottom"], s["size"]
    if cur:
        out.append(cur)
    return out


def order_columns(segs, gutters, body, boxes=(), page=(612.0, 792.0)):
    """Reading order for a page with two or more gutters: XY-cut with the detected gutters as the vertical cuts.

    A region is cut at every gutter that no line crosses; when a line crosses (a title, a table that spans some of
    the columns) the region is first cut into horizontal slabs. Slabs are read top to bottom, columns left to right,
    so a wide block stays where it is and the columns below it follow column by column.

    boxes are drawn regions (shaded boxes, tables, figures). One that spans a gutter and holds text is read as a unit:
    column by column when its text keeps to the columns, row by row when it does not (a table)."""
    thr = max(3.0, 0.4 * body)

    def solve(S, leaves):
        if not S:
            return
        lo, hi = min(s["x0"] for s in S), max(s["x1"] for s in S)
        gs = [g for g in gutters if lo < g < hi and any(s["x1"] <= g + 2 for s in S)
              and any(s["x0"] >= g - 2 for s in S)]
        if not gs:
            leaves.append(("flat", S))
            return

        def crossing(g):
            return sum(1 for s in S if s["x0"] < g - 1 and s["x1"] > g + 1)

        def cut(cuts):
            pieces = defaultdict(list)
            for s in S:
                pieces[sum(1 for g in cuts if s["x0"] + s["x1"] > 2 * g)].append(s)
            for k in sorted(pieces):
                solve(pieces[k], leaves)

        free = [g for g in gs if crossing(g) == 0]
        if free:
            cut(free)
            return
        slabs = slabs_by_gap(S, thr)
        if len(slabs) > 1:
            for sl in slabs:
                solve(sl, leaves)
            return
        # a table or figure caption that straddles a gutter: a few such lines do not make it a wide region,
        # so cut anyway and let each straddling line go with the side that holds its middle
        soft = [g for g in gs if crossing(g) <= max(4, 0.12 * len(S))]
        if soft:
            cut(soft)
            return
        leaves.append(("mixed", S))

    rest, wide = list(segs), []
    pw, ph = page
    for bx in boxes:
        if not any(bx[0] + 10 < g < bx[2] - 10 for g in gutters) or (bx[2] - bx[0]) * (bx[3] - bx[1]) > 0.6 * pw * ph:
            continue
        inside = [s for s in rest if s["x0"] >= bx[0] - 2 and s["x1"] <= bx[2] + 2
                  and s["top"] >= bx[1] - 2 and s["bottom"] <= bx[3] + 2]
        if len(inside) < 6 or len(inside) > 0.7 * len(segs):
            continue
        ids = {id(s) for s in inside}
        rest = [s for s in rest if id(s) not in ids]
        inner = [g for g in gutters if bx[0] + 10 < g < bx[2] - 10]
        columns = not any(s["x0"] < g - 1 and s["x1"] > g + 1 for s in inside for g in inner)
        leaves = []
        if columns:
            solve(inside, leaves)
        else:
            leaves.append(("mixed", inside))
        wide.append((bx, [(k + "+", S) for k, S in leaves]))
    leaves = []
    solve(rest, leaves)
    for bx, wl in sorted(wide, key=lambda w: w[0][1], reverse=True):
        over = [i for i, (_, S) in enumerate(leaves)
                if any(bx[0] <= (s["x0"] + s["x1"]) / 2 <= bx[2] for s in S)]
        if not over:
            leaves += wl
        elif min(s["top"] for s in leaves[over[0]][1]) >= bx[1] - 20:
            leaves[over[0]:over[0]] = wl  # the box opens the column it sits in
        else:
            leaves[over[-1] + 1:over[-1] + 1] = wl
    out = []
    for i, (kind, S) in enumerate(leaves, 1):
        if kind.startswith("flat"):
            lines = make_lines([w for s in S for w in s["words"]])
        else:
            lines = sorted(S, key=lambda s: (s["top"], s["x0"]))
        for ln in lines:
            ln["col"], ln["band"] = 0, i
            if kind.endswith("+"):
                ln["aside"] = True  # inside a drawn box: a paragraph here does not continue the text around it
        out += lines
    return out


def headingish(ln, body):
    if ln.get("force_heading"):
        return True
    t = ln["text"]
    asks = t.endswith("?") and (ln["size"] >= body + 1.0 or ln["bold"] >= 0.85)  # the last line of a heading that asks a question
    if len(t) > 100 or (end_terminal(t) and not asks):
        return False
    return bool(ln.get("force_heading") or ln["size"] >= body + 1.0 or ln["bold"] >= 0.85
                or (ln["size"] >= body - 0.5 and word_count(t) <= 8 and NUM_HEAD_RE.match(t) and is_heading_block(dict(ln, n_lines=1), body)))


LIST_MARK_RE = re.compile(r"^(?:[•●◦▪■‣∙*–—-]|\(?\d+[.)]|\(?[a-z][.)])\s+", re.I)
TOC_RE = re.compile(r"\.{3,}|(?:…\s*){2,}")
READING_RE = re.compile(r"^(?:further|suggested|recommended) reading$", re.I)
CHAPTER_RE = re.compile(r"^(?:ch\.?|chapter)\s+(?:\d+|[IVXLC]+)$", re.I)


def emphasized(w):
    return w.get("bold") or w.get("italic") or bool(re.search(r"italic|oblique", w.get("font", ""), re.I))


def prepare_typing_lines(lines, body):
    """Use layout tokens before paragraph assembly (style spans and hanging indents)."""
    out = []
    for line in lines:
        words = line.get("words", [])
        cut = 0
        while cut < len(words) and emphasized(words[cut]):
            cut += 1
        if 0 < cut < len(words):
            prefix = line_from_words(words[:cut])
            # A styled lead phrase, rather than an initial, abbreviation or number.
            if ((line["size"] >= body - 0.5 or line.get("text_box")) and prefix["text"].endswith(".") and len(re.findall(r"[A-Za-z]{3,}", prefix["text"])) >= 1
                    and not CAPTION_RE.match(prefix["text"])):
                previous = next((x for x in reversed(out) if x["band"] == line["band"] and x["col"] == line["col"]), None)
                if (previous and previous.get("words") and all(emphasized(w) for w in previous["words"])
                        and previous.get("font") == prefix.get("font")
                        and 0 <= line["top"] - previous["bottom"] <= line["size"]
                        and not headingish(previous, body)):
                    out.append(line)  # the tail of an italic paragraph is not a run-in heading
                    continue
                head = dict(line, **prefix)
                head["force_heading"] = True
                tail = dict(line, **line_from_words(words[cut:]))
                tail["runin_body"] = True
                out.extend((head, tail))
                continue
        out.append(line)
    streams = defaultdict(list)
    for line in out:
        streams[(line["band"], line["col"])].append(line)
        line["toc"] = bool(TOC_RE.search(line["text"]) and re.search(r"(?:\d+|[ivxlcdm]+)\s*$", line["text"], re.I))
        ws = line.get("words", [])
        line["cell_edges"] = [b["x0"] for a, b in zip(ws, ws[1:])
                              if b["x0"] - a["x1"] >= max(a["size"], b["size"])]
    for ls in streams.values():
        for i, line in enumerate(ls):
            previous = ls[i - 1] if i else None
            following = ls[i + 1] if i + 1 < len(ls) else None
            if (line.get("bold", 0) >= 0.85 and line["text"].endswith(".")
                    and following and following.get("words") and not emphasized(following["words"][0])
                    and previous and previous.get("bold", 0) >= 0.85 and not end_terminal(previous["text"])):
                line["force_heading"] = True
            if (line.get("italic", 0) >= 0.85 and 2 <= word_count(line["text"]) <= 12
                    and not end_terminal(line["text"]) and not display_variable_style([line])
                    and following and following.get("words") and not emphasized(following["words"][0])
                    and following.get("italic", 0) < 0.5 and following.get("bold", 0) < 0.5
                    and (not previous or previous.get("italic", 0) < 0.5)
                    and abs(line["size"] - body) <= max(1, 0.15 * body)):
                line["force_heading"] = True
        for i, line in enumerate(ls):
            if line.get("force_heading") or line.get("toc"):
                continue
            match = LIST_MARK_RE.match(line["text"])
            if match:
                bullet = line["text"][0] in "•●◦▪‣∙"
                peers = [x for x in ls[max(0, i - 3):i + 4] if x is not line and LIST_MARK_RE.match(x["text"])
                         and abs(x["x0"] - line["x0"]) <= 0.15 * body]
                if (bullet or (peers and not line.get("bold", 0) >= 0.85)) and not display_variable_style([line]):
                    line["list_start"] = True
                    words = line.get("words", [])
                    line["list_indent"] = (words[1]["x0"] if len(words) > 1 and len(words[0]["text"]) <= match.end()
                                           else line["x0"])
            if not match:
                # A lost marker is still visible ink at the hanging margin.
                boxes = [box for w in line.get("words", []) for box in w.get("unmapped_boxes", [])
                         if box[1] <= line["x0"] and line["x0"] - box[0] <= 2 * body
                         and box[1] - box[0] <= body and box[2] < line["bottom"] and box[3] > line["top"]]
                if boxes:
                    line["lost_marker"] = max(boxes, key=lambda box: box[1])
        lost = [x for x in ls if x.get("lost_marker")]
        for line in lost:
            if any(x is not line and abs(x["lost_marker"][0] - line["lost_marker"][0]) <= 0.15 * body for x in lost):
                line["list_start"], line["list_indent"] = True, line["x0"]
        hanging = [(a, b) for a, b in zip(ls, ls[1:]) if not a.get("force_heading") and not a.get("cell_edges")
                   and b["x0"] > a["x0"] + 0.8 * body and abs(a["size"] - body) <= 0.5
                   and abs(b["size"] - body) <= 0.5 and not end_terminal(a["text"])
                   and 0 <= b["top"] - a["bottom"] <= body]
        for a, b in hanging:
            if any(x is not a and abs(x["x0"] - a["x0"]) <= 0.15 * body
                   and abs(y["x0"] - b["x0"]) <= 0.15 * body for x, y in hanging):
                a["list_start"], a["list_indent"] = True, b["x0"]
    return out


def aligned_cells(blocks):
    """Tables require a repeated interior cell boundary, not just short lines."""
    if (all("cell_edges" not in b and NUMERIC_ROW_RE.fullmatch(b["text"]) for b in blocks)
            and len({len(b["text"].split()) for b in blocks}) == 1 and len(blocks[0]["text"].split()) >= 2):
        return True  # text-only callers can supply a rectangular numeric matrix
    rows = [edges for b in blocks for edges in b.get("cell_edges", []) if edges]
    return len(rows) >= 3 and any(sum(any(abs(edge - candidate) <= 3 for edge in row) for row in rows) >= 3
                                  for row in rows for candidate in row)


def build_blocks(lines, pno, body):
    lines = prepare_typing_lines(lines, body)
    streams = defaultdict(list)
    for ln in lines:
        streams[(ln["band"], ln["col"])].append(ln)
    left_edge, right_edge = {}, {}
    for k, ls in streams.items():
        good = [l for l in ls if abs(l["size"] - body) <= max(1.0, 0.15 * body) and len(l["text"]) > 25] or ls
        xs = sorted(l["x0"] for l in good)
        rs = sorted(l["x1"] for l in good)
        left_edge[k] = xs[len(xs) // 4]
        right_edge[k] = rs[int(len(rs) * 0.75)]
    gaps = []
    for ls in streams.values():
        for a, b in zip(ls, ls[1:]):
            g = b["top"] - a["bottom"]
            if -1 < g < 1.5 * body:
                gaps.append(g)
    gap_med = statistics.median(gaps) if gaps else 0.25 * body
    blocks, cur = [], None
    for ln in lines:
        key = (ln["band"], ln["col"])
        new = cur is None or key != cur["key"]
        if not new:
            prev = cur["lines"][-1]
            sz = max(prev["size"], ln["size"])
            le = left_edge[key]
            tol = max(1.0, 0.15 * body)
            body_like = abs(ln["size"] - body) <= tol and abs(prev["size"] - body) <= tol
            in_caption = CAPTION_RE.match(cur["lines"][0]["text"]) is not None
            in_list = cur["lines"][0].get("list_start")
            same_heading = (abs(prev["size"] - ln["size"]) <= 0.5 and prev.get("font") == ln.get("font")
                            and (prev.get("bold", 0) >= 0.85 and ln.get("bold", 0) >= 0.85
                                 or prev.get("italic", 0) >= 0.85 and ln.get("italic", 0) >= 0.85)
                            and not NUM_HEAD_RE.match(ln["text"]))
            if (ln.get("list_start") or ln.get("toc") or prev.get("toc") or (prev.get("force_heading") and not same_heading) or ln.get("runin_body")
                    or (ln.get("force_heading") and not ((headingish(prev, body) or same_heading) and abs(prev["size"] - ln["size"]) <= 0.5
                                                         and ln["top"] - prev["bottom"] <= gap_med + max(0.45 * sz, 2.5)))):
                new = True
            elif in_list and abs(ln["x0"] - cur["lines"][0].get("list_indent", ln["x0"])) <= 0.15 * body and ln["top"] - prev["bottom"] <= gap_med + max(0.45 * sz, 2.5):
                pass
            elif ln["top"] - prev["bottom"] > gap_med + max(0.45 * sz, 2.5):
                new = True
            elif abs(ln["size"] - prev["size"]) > max(0.9, 0.09 * body):
                new = True
            elif CAPTION_RE.match(ln["text"]):
                new = True
            elif (ln.get("mono", 0) >= 0.5) != (prev.get("mono", 0) >= 0.5):
                new = True
            elif bool(ln.get("tab")) != bool(prev.get("tab")):
                new = True
            elif in_caption:
                pass
            elif body_like and not same_heading and ln["x0"] - le > 0.8 * ln["size"] and prev["x0"] - le < 0.4 * prev["size"]:
                new = True
            elif (prev["x1"] < right_edge[key] - 2.5 * prev["size"] and end_terminal(prev["text"])
                  and not starts_lower(ln["text"])):
                new = True
            elif ((headingish(prev, body) != headingish(ln, body) and not same_heading)
                  or (headingish(ln, body) and NUM_HEAD_RE.match(ln["text"]))):
                new = True
        if new:
            cur = {"key": key, "lines": [], "page": pno,
                   "column_x0": left_edge[key], "column_x1": right_edge[key], "line_gap": gap_med}
            blocks.append(cur)
        cur["lines"].append(ln)
    return [finish_block(b) for b in blocks]


def column_jumps(lines):
    """How often consecutive lines of a block start far apart: a paragraph read across two columns zigzags."""
    return sum(1 for a, b in zip(lines, lines[1:])
               if abs(b["x0"] - a["x0"]) > 6 * max(a["size"], b["size"]))


def unmapped_ink(lines, block):
    """Retain visible but undecodable ink for the display crop, within its column."""
    top, bottom = min(l["top"] for l in lines), max(l["bottom"] for l in lines)
    left = block.get("column_x0", min(l["x0"] for l in lines))
    right = block.get("column_x1", max(l["x1"] for l in lines))
    boxes = {box for line in lines for w in line.get("words", []) for box in w.get("unmapped_boxes", [])}
    return [box for box in boxes if left <= (box[0] + box[1]) / 2 <= right
            and box[2] < bottom and box[3] > top]


def symbolic_display(text):
    words = re.findall(r"[A-Za-z]{3,}", re.sub(r"\b(?:ln|log|exp)\b", "", text))
    return not any(not w.isupper() for w in words) and math_dense(text)


def display_variable_style(lines):
    """A display row is predominantly short italic variables, rather than prose.

    Keep the font evidence before extraction loses operators with unmapped glyphs.
    This is used only to group consecutive display rows, outside ruled tables.
    """
    if len(lines) > 2:
        return False
    text = " ".join(line["text"] for line in lines)
    # Inspect reconstructed words too: tracked italic headings can have one
    # extracted token per glyph. Long uppercase labels need an actual operator.
    if any(not token.isupper() or not EQUATION_RE.search(text)
           for token in re.findall(r"[A-Za-z]{3,}", text)):
        return False
    words = [w for line in lines for w in line.get("words", []) if w["text"].isalpha()]
    if any(len(w["text"]) > 2 and not w["text"].isupper() for w in words):
        return False  # prose lead-ins stay visible even when they contain many variables
    variables = [w for w in words if len(w["text"]) <= 2 and (w.get("italic") or re.search(r"italic|oblique", w.get("font", ""), re.I))]
    return len(variables) >= 3 and len(variables) > len(words) / 2


def trailing_title_marker(lines):
    words = lines[-1].get("words", [])
    if len(words) < 2:
        return ""
    tail = words[-1]
    all_words = [w for line in lines for w in line.get("words", [])]
    fonts = Counter(w.get("font") for w in all_words[:-1] for _ in w["text"])
    dominant = fonts.most_common(1)[0][0] if fonts else None
    if (len(tail["text"]) == 1 and tail.get("font") != dominant
            and tail.get("font") != words[-2].get("font") and tail["text"] not in ".?!:;,)]}"):
        return tail["text"]
    return ""


def finish_block(b):
    lines = b["lines"]
    text = ""
    for ln in lines:
        text = join_marked(text, ln["text"])
    n = sum(len(l["text"]) for l in lines) or 1
    sizes = sorted((l["size"], len(l["text"])) for l in lines)
    acc, size = 0, sizes[0][0]
    for s, k in sizes:
        acc += k
        if acc >= n / 2:
            size = s
            break
    if (len(lines) > 1 and word_count(lines[0]["text"]) <= 3
            and lines[0].get("font") and lines[0].get("font") != lines[1].get("font")
            and not end_terminal(lines[0]["text"])):
        b["title_text"] = lines[0]["text"] + ": " + " ".join(l["text"] for l in lines[1:])
    return {"title_text": b.get("title_text", text), "text": text, "page": b["page"], "key": b["key"], "size": size,
            "bold": sum(l["bold"] * len(l["text"]) for l in lines) / n,
            "mono": sum(l.get("mono", 0) * len(l["text"]) for l in lines) / n,
            "top": min(l["top"] for l in lines), "bottom": max(l["bottom"] for l in lines),
            "x0": min(l["x0"] for l in lines), "x1": max(l["x1"] for l in lines),
            "title_suffix": trailing_title_marker(lines),
            "font": lines[0].get("font", ""),
            "force_heading": any(l.get("force_heading") for l in lines),
            "list": bool(lines[0].get("list_start")), "toc": any(l.get("toc") for l in lines),
            "line_gap": b.get("line_gap"),
            "cell_edges": [l.get("cell_edges", []) for l in lines],
            "text_box": lines[0].get("text_box"),
            "superscripts": [mark for l in lines for mark in l.get("superscripts", [])],
            "math_style": display_variable_style(lines),
            "unmapped_ink": unmapped_ink(lines, b),
            "n_lines": len(lines), "jumps": column_jumps(lines), "aside": any(l.get("aside") for l in lines),
            "tab": all(l.get("tab") for l in lines)}


def margin_key(text):
    return re.sub(r"\d+", "#", text.lower()).strip()


def strip_margins(pages, get_items, set_items, label_sink, band=0.15):
    """删掉重复的页眉页脚和页码行，并记录印刷页码。get_items(p) 返回该页可删的行或块。

    候选带是页面上下各 band（默认 15%，JSTOR 扫描的页眉常在 12%）。带内的行只有在
    多页重复、是页码、或是期刊横幅时才删除；正文第一行不会跨页重复，所以不会被误删。"""
    n = len(pages)
    keys = Counter()

    inner = min(0.085, band)

    def in_band(it, p):
        return it["top"] < band * p["h"] or it["bottom"] > (1 - band) * p["h"]

    def head_like(it, p):
        """Outside the inner 8.5% a repeated line must also look like a running head: short, not a sentence,
        and not a caption or an equation label ("Table 1" and "Table 2" share a digit-stripped key)."""
        t = it["text"].strip()
        # Repeated decimal-valued rows are chart ticks, legends or table cells,
        # not running heads. Preserve them even when several pages reuse a scale.
        if (CAPTION_RE.match(t) or CAPTION_TITLE_RE.match(t) or EQ_NUMBER_RE.match(t)
                or re.search(r"\d\.\d+\s*$", t)):
            return False
        if it["top"] < inner * p["h"] or it["bottom"] > (1 - inner) * p["h"]:
            return True
        return len(t) < 100 and (not t.rstrip(CLOSERS) or t.rstrip(CLOSERS)[-1] not in TERMINAL)

    for p in pages:
        seen = set()
        for it in get_items(p):
            if in_band(it, p):
                seen.add(margin_key(it["text"]))
        keys.update(seen)
    need = 2 if n >= 3 else 99  # 奇偶页交替的页眉各自只占一部分页面
    # Alternating heads on a short range: the odd-page head repeats but the even-page head may appear once.
    # A head-like line at the same height as a repeated head on a neighbouring page is a running head too.
    head_rows = {}
    for p in pages:
        for it in get_items(p):
            if in_band(it, p) and keys[margin_key(it["text"])] >= need and len(it["text"]) < 200 and head_like(it, p):
                head_rows.setdefault(p["pno"], []).append(it["top"] / p["h"])

    first = pages[0]["pno"] if pages else None

    def same_row(it, p):
        """Only for ranges of three pages or fewer: longer ranges repeat both heads. Chapter openers and
        first pages put titles where running heads sit, so the line must also look like a head itself."""
        if n > 3 or p["pno"] == first:
            return False
        t = it["text"].strip()
        if not t or not (t[0].isupper() or t[0].isdigit()) or re.search(r"[.!?]\s+[a-z]", t):
            return False
        rows = head_rows.get(p["pno"] - 1, []) + head_rows.get(p["pno"] + 1, [])
        return any(abs(it["top"] / p["h"] - r) < 0.015 for r in rows)

    removed = 0
    for p in pages:
        keep = []
        for it in get_items(p):
            in_margin = in_band(it, p)
            m = PAGE_NUM_RE.match(it["text"]) if in_margin else None
            if m:
                label_sink.append((p["pno"], m.group(1)))
                removed += 1
                continue
            banner = it["top"] < band * p["h"] and BANNER_RE.search(it["text"]) and len(it["text"]) < 160
            if banner or (in_margin and len(it["text"]) < 200 and head_like(it, p)
                          and (keys[margin_key(it["text"])] >= need or same_row(it, p))):
                # 页眉里的页码也记下来
                mm = (re.search(r"(?:^|\s)(\d{1,4})\s*/\s*\d{1,4}$", it["text"])
                      or re.match(r"^(\d{1,4})\s+\D", it["text"])
                      or re.search(r"\D\s(\d{1,4})$", it["text"]))
                if mm and len(it["text"]) < 120 and not re.search(r"\d+:\d+|\d+\.\d+\.\d+", it["text"]):
                    label_sink.append((p["pno"], mm.group(1)))
                removed += 1
                continue
            keep.append(it)
        set_items(p, keep)
    return removed


def page_labels_from(pairs, pnos):
    digits = [(p, int(l)) for p, l in pairs if l.isdigit()]
    if len(digits) >= 2:
        offs = Counter(l - p for p, l in digits)
        off, cnt = offs.most_common(1)[0]
        if cnt >= max(2, 0.6 * len(digits)):
            return {str(p): str(p + off) for p in pnos if p + off > 0}
    return {str(p): l for p, l in pairs}


def text_container(box, lines, body):
    """A ruled enclosure containing a paragraph is a text container, not a table.

    Require consecutive body-sized, sentence-like lines with ordinary line spacing;
    table cells and isolated axis labels do not establish a paragraph.
    """
    inside = [l for l in lines if box[0] <= l["x0"] and l["x1"] <= box[2]
              and box[1] <= l["top"] and l["bottom"] <= box[3]
              and word_count(l["text"]) >= 6 and not TABLE_NOTE_RE.match(l["text"])
              and sum(c.isalpha() for c in l["text"]) > len(l["text"]) / 2]
    all_text = sum(len(l["text"]) for l in lines if box[0] <= l["x0"] and l["x1"] <= box[2]
                   and box[1] <= l["top"] and l["bottom"] <= box[3])
    if sum(len(l["text"]) for l in inside) <= all_text / 2:
        return False
    for a, b, c in zip(inside, inside[1:], inside[2:]):
        if (abs(a["x0"] - b["x0"]) <= body and abs(b["x0"] - c["x0"]) <= body
                and -0.5 * body <= b["top"] - a["bottom"] <= body
                and -0.5 * body <= c["top"] - b["bottom"] <= body
                and any(end_terminal(l["text"]) for l in (a, b, c))):
            return True
    return False


def figure_boxes(page):
    """矢量图形密集的区域（示意图、带框线的表格），用来排除图里的标签被当成标题。"""
    W, H = float(page.width), float(page.height)
    boxes = []
    try:
        objs = (page.rects + page.curves + page.lines)[:3000]
    except Exception:
        return []
    ox, oy = float(page.bbox[0]), float(page.bbox[1])
    for o in objs:
        x0, t, x1, b = float(o["x0"]) - ox, float(o["top"]) - oy, float(o["x1"]) - ox, float(o["bottom"]) - oy
        if x1 - x0 > 0.9 * W and b - t < 3:
            continue
        boxes.append([x0, t, x1, b])
    changed = True
    while changed:
        changed, out = False, []
        for bx in boxes:
            for m in out:
                if bx[0] <= m[2] + 6 and bx[2] >= m[0] - 6 and bx[1] <= m[3] + 6 and bx[3] >= m[1] - 6:
                    m[0], m[1] = min(m[0], bx[0]), min(m[1], bx[1])
                    m[2], m[3] = max(m[2], bx[2]), max(m[3], bx[3])
                    changed = True
                    break
            else:
                out.append(bx[:])
        boxes = out
    return [m for m in boxes if (m[2] - m[0]) * (m[3] - m[1]) > 0.01 * W * H] + rule_tables(objs, ox, oy, W)


def rule_tables(objs, ox, oy, W):
    """Tables drawn with horizontal rules only (top, header and bottom rule): the region between the first and last rule
    of rules that share their left and right ends. Each rule is too thin to count as a figure on its own."""
    rules = []
    for o in objs:
        x0, t, x1, b = float(o["x0"]) - ox, float(o["top"]) - oy, float(o["x1"]) - ox, float(o["bottom"]) - oy
        if b - t < 2.5 and 20 <= x1 - x0 <= 0.9 * W:
            rules.append((x0, t, x1, b))
    merged = []  # a rule drawn in pieces (one per column) is one rule
    for r in sorted(rules, key=lambda r: (round(r[1]), r[0])):
        if merged and abs(merged[-1][1] - r[1]) <= 1 and r[0] - merged[-1][2] <= 3:
            merged[-1] = (merged[-1][0], min(merged[-1][1], r[1]), max(merged[-1][2], r[2]), max(merged[-1][3], r[3]))
        else:
            merged.append(r)
    rules = [r for r in merged if r[2] - r[0] >= 80]
    out, used = [], set()
    for i, r in enumerate(sorted(rules)):
        if i in used:
            continue
        group = [r]
        for j, q in enumerate(sorted(rules)):
            if j != i and j not in used and abs(q[0] - r[0]) <= 6 and abs(q[2] - r[2]) <= 6:
                group.append(q)
                used.add(j)
        group.sort(key=lambda q: q[1])
        run = [group[0]]
        for q in group[1:] + [None]:
            if q is not None and q[1] - run[-1][3] <= 450:
                run.append(q)
                continue
            if len(run) >= 2 and run[-1][3] - run[0][1] >= 15:
                out.append([min(x[0] for x in run) - 2, run[0][1] - 2, max(x[2] for x in run) + 2, run[-1][3] + 2, "rules"])
            run = [q] if q is not None else []
    return out


def split_drop_caps(words, body):
    """(words without drop caps, the drop caps): an enlarged single capital with a lowercase word right beside it."""
    caps = [w for w in words if len(w["text"]) == 1 and "A" <= w["text"] <= "Z" and w["size"] >= 1.7 * body
            and any(o["text"][:1].islower() and o["size"] < 0.7 * w["size"] and -0.1 * w["size"] <= o["x0"] - w["x1"] < 0.5 * w["size"]
                    and w["top"] - 4 <= o["top"] <= w["bottom"] for o in words)]
    return [w for w in words if not any(w is c for c in caps)], caps


def restore_drop_caps(page_blocks, words, body):
    """Put a drop cap back at the head of the paragraph that lost it, and remove the lone-letter block it left behind."""
    gone = set()
    for i, b in enumerate(page_blocks):
        w = drop_cap_for(b["text"], (b["x0"], b["top"], b["x1"], b["bottom"]), words, body)
        if w is None:
            continue
        b["text"] = put_drop_cap(b["text"], w["text"])
        b["x0"], b["top"] = min(b["x0"], w["x0"]), min(b["top"], w["top"])
        gone |= {j for j, o in enumerate(page_blocks) if j != i and o["text"].strip() == w["text"]
                 and abs(o["top"] - w["top"]) < 2}
    return [b for j, b in enumerate(page_blocks) if j not in gone]


def unbold_body_font(words, body):
    """Some fonts are named like a bold weight (Medium, Demi) but are the body font of the whole paper. When the body
    text itself counts as bold, bold stops being a heading signal: keep it only for words in some other font."""
    fonts = Counter()
    for w in words:
        if abs(w["size"] - body) <= 0.5 and w.get("font"):
            fonts[w["font"]] += len(w["text"])
    if not fonts:
        return
    body_font, _ = fonts.most_common(1)[0]
    if any(w["bold"] and w.get("font") == body_font for w in words):
        for w in words:
            if w.get("font") == body_font:
                w["bold"] = False


def join_chapter_openers(blocks, body):
    out, i = [], 0
    while i < len(blocks):
        tag = blocks[i]
        if CHAPTER_RE.fullmatch(tag["text"].strip()) and tag["size"] > body:
            j = i + 1
            while (j < len(blocks) and blocks[j]["page"] == tag["page"]
                   and blocks[j]["size"] >= body + 2.5
                   and (not tag.get("font") or blocks[j].get("font") == tag["font"])
                   and (j == i + 1 or abs(blocks[j]["x0"] - blocks[i + 1]["x0"]) <= 3)
                   and (j == i + 1 or blocks[j]["top"] - blocks[j - 1]["bottom"] <= blocks[j]["size"])):
                j += 1
            if j > i + 1:
                run = blocks[i:j]
                text = tag["text"] + ": " + " ".join(b["text"] for b in run[1:])
                out.append(dict(run[1], text=text, title_text=text, force_heading=True, chapter=True,
                                n_lines=sum(b["n_lines"] for b in run), top=min(b["top"] for b in run),
                                bottom=max(b["bottom"] for b in run), x0=min(b["x0"] for b in run),
                                x1=max(b["x1"] for b in run)))
                i = j
                continue
        out.append(tag)
        i += 1
    return out


def from_pdf_text(pdf, pnos, columns, cache=None):
    """cache keeps the extracted words between runs with different column settings (the self-check retries)."""
    pages = []
    cache = {} if cache is None else cache
    if "width_reference" not in cache:
        cache["width_reference"] = text_width_reference(pdf, pnos)
    for pno in pnos:
        if pno not in cache:
            page = pdf.pages[pno - 1]
            repair_stretched_text(page, cache["width_reference"])
            cache[pno] = {"pno": pno, "w": float(page.width), "h": float(page.height),
                          "words": get_words(page), "figs": figure_boxes(page)}
        pages.append(dict(cache[pno]))
    body = body_size([w for p in pages for w in p["words"]])
    unbold_body_font([w for p in pages for w in p["words"]], body)
    for p in pages:  # a drop cap would stretch the first lines into one tall row; set it aside, restore it below
        p["words"], p["caps"] = split_drop_caps(p["words"], body)
    two_col = multi_col = 0
    for p in pages:
        segs = make_lines(p["words"], gap_split=True)
        layout_boxes = p["figs"]
        containers = [f for f in layout_boxes if text_container(f, segs, body)]
        p["figs"] = [f for f in layout_boxes if f not in containers]
        for w in p["words"]:
            for box in containers:
                if ((box[2] - box[0]) * (box[3] - box[1]) <= 0.6 * p["w"] * p["h"]
                        and box[0] <= (w["x0"] + w["x1"]) / 2 <= box[2]
                        and box[1] <= (w["top"] + w["bottom"]) / 2 <= box[3]):
                    w["text_box"] = tuple(box[:4])
                    break
        for ln in segs:
            values = {w.get("text_box") for w in ln.get("words", [])}
            ln["text_box"] = values.pop() if len(values) == 1 else None
        # Establish body columns outside independently drawn figure/table regions.
        column_segs = [l for l in segs if not any(f[0] <= (l["x0"] + l["x1"]) / 2 <= f[2]
                       and f[1] <= (l["top"] + l["bottom"]) / 2 <= f[3] for f in p["figs"])]
        split = None
        gutters = column_gutters(column_segs, p["w"], body, force=(columns == "3")) if columns in ("auto", "3") else []
        if len(gutters) >= 2:  # three or more columns: cut the page at the gutters
            p["sidebar"] = None
            p["lines"] = order_columns(segs, gutters, body, layout_boxes, (p["w"], p["h"]))
            multi_col += 1
            continue
        if columns in ("auto", "2"):
            split = detect_split(column_segs, p["w"], body, force=(columns == "2"))
        sidebar = detect_sidebar(segs, p["w"]) if columns == "auto" and split is None else None
        if sidebar is not None:
            split = sidebar
        p["sidebar"] = sidebar
        if sidebar is not None:
            right = [l for l in segs if l["x0"] >= sidebar and l["size"] >= body - 0.5 and len(l["text"]) >= 20]
            left = [l for l in segs if l["x1"] <= sidebar and l["size"] < body - 0.5
                    and right and l["top"] <= max(r["bottom"] for r in right)
                    and l["bottom"] >= min(r["top"] for r in right) - body]
            p["sidebar_bottom"] = max((l["bottom"] for l in left), default=0)
        if split is not None:
            two_col += 1
        p["lines"] = order_lines(p["words"], segs, split)
    for p in pages:  # text between the rules of a table is table content, whatever its size
        tabs = [f for f in p["figs"] if len(f) > 4]
        for ln in p["lines"]:
            cx, cy = (ln["x0"] + ln["x1"]) / 2, (ln["top"] + ln["bottom"]) / 2
            if any(f[0] <= cx <= f[2] and f[1] <= cy <= f[3] for f in tabs):
                ln["tab"] = True
    labels = []
    removed = strip_margins(pages, lambda p: p["lines"], lambda p, v: p.__setitem__("lines", v), labels)
    blocks = []
    for p in pages:
        page_blocks = build_blocks(p["lines"], p["pno"], body) if p["lines"] else []
        page_blocks = restore_drop_caps(page_blocks, p["caps"], body)
        for b in page_blocks:
            b["pw"], b["ph"] = p["w"], p["h"]
            if p.get("sidebar") is not None and b["x1"] <= p["sidebar"] + 2 and b["top"] <= p.get("sidebar_bottom", 0):
                b["sidebar"] = True
        blocks += page_blocks
    blocks = join_chapter_openers(blocks, body)
    info = {p["pno"]: {"h": p["h"], "w": p["w"], "figs": p["figs"], "text_overflow": bool(
                any(c["x1"] > pdf.pages[p["pno"] - 1].bbox[2] for c in getattr(pdf.pages[p["pno"] - 1], "chars", []))
                and any(i.get("width", 0) >= p["w"] / 2 and i.get("height", 0) >= p["h"] / 2
                        for i in getattr(pdf.pages[p["pno"] - 1], "images", [])))} for p in pages}
    return blocks, body, info, {"two_col": two_col, "multi_col": multi_col, "removed": removed, "labels": labels}


# ---------- OCR ----------

def ocr_available(lang="eng"):
    """Check Python adapters, executables and requested language data before starting OCR."""
    if not all(importlib.util.find_spec(m) for m in ("pytesseract", "pdf2image")):
        return False
    if not all(shutil.which(m) for m in ("tesseract", "pdftoppm", "pdfinfo")):
        return False
    try:
        import pytesseract
        return set(lang.split("+")).issubset(pytesseract.get_languages(config=""))
    except Exception:
        return False


def ocr_page_numbers(pdf, pnos, mode, text_counts=None):
    """Low text coverage calls for OCR only when a raster covers the page's centre.

    Sparse vector pages and blank versos need no OCR. A central image spanning both
    page midlines distinguishes a page scan from a logo or a small illustration.
    """
    counts = {} if text_counts is None else text_counts
    for p in pnos:
        counts[p] = sum(len(w["text"]) for w in get_words(pdf.pages[p - 1]))
    if mode == "on":
        return list(pnos)
    if mode == "off":
        return []
    out = []
    for p in pnos:
        page = pdf.pages[p - 1]
        if counts[p] >= 30:
            continue
        if not hasattr(page, "images"):
            out.append(p)  # unknown raster coverage: retain the OCR candidate
            continue
        ox, oy = page.bbox[:2]
        if any(i["x0"] <= ox + page.width / 4 and i["x1"] >= ox + 3 * page.width / 4
               and i["top"] <= oy + page.height / 4 and i["bottom"] >= oy + 3 * page.height / 4
               for i in getattr(page, "images", [])):
            out.append(p)
    return out


def from_ocr(pdf_path, pnos, lang, dpi):
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:
        sys.exit(f"OCR 需要 pytesseract 和 pdf2image：{e}")
    have = pytesseract.get_languages(config="")
    lacking = [x for x in lang.split("+") if x not in have]
    if lacking:
        sys.exit(f"tesseract is missing language data {lacking}; installed: {', '.join(have)}")
    pages, blocks = [], []
    sc = 72.0 / dpi
    for i, pno in enumerate(pnos, 1):
        print(f"  OCR 第 {pno} 页（{i}/{len(pnos)}）", file=sys.stderr, flush=True)
        img = convert_from_path(str(pdf_path), dpi=dpi, first_page=pno, last_page=pno)[0]
        d = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        groups, order = defaultdict(lambda: defaultdict(list)), []
        for k, raw in enumerate(d["text"]):
            t = clean_text(raw)
            try:
                conf = float(d["conf"][k])
            except (TypeError, ValueError):
                conf = -1
            if not t or conf < 0:
                continue
            if conf < 35 and not re.search(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", t):
                continue
            key = (d["block_num"][k], d["par_num"][k])
            if key not in groups:
                order.append(key)
            groups[key][d["line_num"][k]].append({
                "text": t, "x0": d["left"][k] * sc, "x1": (d["left"][k] + d["width"][k]) * sc,
                "top": d["top"][k] * sc, "bottom": (d["top"][k] + d["height"][k]) * sc})
        p = {"pno": pno, "w": img.size[0] * sc, "h": img.size[1] * sc, "blocks": []}
        for key in order:
            lines = []
            for ln_no in sorted(groups[key]):
                ws = sorted(groups[key][ln_no], key=lambda w: w["x0"])
                text = ""
                for w in ws:
                    text = join_words(text, w["text"])
                hs = sorted(w["bottom"] - w["top"] for w in ws)
                lines.append({"text": text, "x0": ws[0]["x0"], "x1": max(w["x1"] for w in ws),
                              "top": min(w["top"] for w in ws), "bottom": max(w["bottom"] for w in ws),
                              "size": round(hs[len(hs) // 2], 1), "bold": 0.0})
            p["blocks"].append(finish_block({"lines": lines, "page": pno, "key": (pno, key[0])}))
        for b in p["blocks"]:
            b["pw"], b["ph"] = p["w"], p["h"]
        pages.append(p)
    labels = []
    removed = strip_margins(pages, lambda p: p["blocks"], lambda p, v: p.__setitem__("blocks", v), labels)
    for p in pages:
        blocks += p["blocks"]
    cnt = Counter()
    for b in blocks:
        cnt[round(b["size"] * 2) / 2] += len(b["text"])
    body = cnt.most_common(1)[0][0] if cnt else 10.0
    info = {p["pno"]: {"h": p["h"], "w": p["w"]} for p in pages}
    return blocks, body, info, {"two_col": 0, "removed": removed, "labels": labels}


# ---------- 分类、续接、编号 ----------

def is_heading_block(b, body):
    t = b["text"]
    if b.get("force_heading") or READING_RE.fullmatch(t.strip()):
        return True
    if b["n_lines"] > 3 or len(t) > 160:
        return False
    words = word_count(t)
    if words > 20:
        return False
    numbered = NUM_HEAD_RE.match(t)
    run_in = t.endswith(".") and words <= 8 and b["bold"] >= 0.85  # 单独成行的粗体小标题，如 "Type specialization."
    question = t.endswith("?") and words <= 12 and (b["size"] >= body + 1.0 or b["bold"] >= 0.85)  # a heading that asks
    if t.rstrip().endswith((",", ";")):
        return False  # a line that stops at a comma is the start of a sentence, whatever its number or size
    if end_terminal(t) and not (numbered and words <= 12) and not run_in and not question:
        return False
    letters = sum(1 for c in t if c.isalpha() or is_cjk(c))
    if KNOWN_HEAD_RE.fullmatch(t.strip()) and b["n_lines"] == 1:
        return True
    if letters < 3 or letters / max(1, len(t.replace(" ", ""))) < 0.6:
        return False
    strong = (b["size"] >= body + 2.5 or b["bold"] >= 0.85) and words <= 12
    toks = NUM_PREFIX_RE.sub("", t).split()
    if not strong and not question and len(toks) >= 3 and sum(1 for k in toks if len(k) <= 2) / len(toks) >= 0.4:
        return False  # 像 "i 1 t 1 Outer Tree" 这样的图内标签
    if starts_lower(t) and re.search(r"[.!?]\s+\w", t):
        return False  # a sentence restart inside a page-break continuation
    strong = (b["size"] >= body + 2.5 or b["bold"] >= 0.85) and words <= 12
    if starts_lower(t) and not is_cjk(t.lstrip()[:1]) and not strong and not question:
        return False  # a continuation line from the previous page, however large OCR says it is
    toks_cap = [w for w in toks if w.lower() not in SMALL_WORDS]
    cap_share = sum(1 for w in toks_cap if w[:1].isupper()) / len(toks_cap) if toks_cap else 0
    big = b["size"] >= body + 1.0 and (words <= 8 or cap_share >= 0.5 or bool(numbered))
    bold = b["bold"] >= 0.85 and words <= 12
    caps = t.isupper() and 1 <= words <= 10 and letters >= 4
    plain_numbered = (bool(numbered) and words <= 20 and not end_terminal(t)
                      and re.match(r"^\S+\s+([A-Z][a-z]{2,}|[\u4e00-\u9fff])", t) is not None)
    known = KNOWN_HEAD_RE.match(NUM_PREFIX_RE.sub("", t).strip()) is not None and b["n_lines"] == 1
    cn = CN_HEAD_RE.match(t.strip()) is not None and len(t) <= 40 and not end_terminal(t)
    big_words = [w for w in toks if w.lower() not in SMALL_WORDS]
    title_case = (1 <= words <= 8 and not end_terminal(t) and big_words
                  and sum(1 for w in big_words if w[:1].isupper()) / len(big_words) >= 0.8
                  and b["size"] >= 1.04 * body and b["n_lines"] <= 2)
    # a small-caps subheading ("A. generating Bounds on risk Aversion"): numbered, one line, capitals further in
    # (the capitals of small caps are often lost, "C. industry comparisons": then it must at least stand centred)
    centred = "pw" not in b or abs((b["x0"] + b["x1"]) / 2 - b["pw"] / 2) < 0.12 * b["pw"]
    small_caps = (bool(numbered) and words <= 8 and b["n_lines"] == 1 and not end_terminal(t)
                  and re.match(r"^\S+\s+[a-z]{3,}", t) is not None
                  and (any(k[:1].isupper() for k in toks[1:]) or (centred and re.match(r"^([A-H]|[IVX]+)[.)]\s", t))))
    return question or strong or big or bold or caps or plain_numbered or known or title_case or cn or small_caps


FOOT_MARK_RE = re.compile(r"^\s*([\u2460-\u2473]|[*†‡§¶■]|\d{1,2}\s?(?=[A-Z\u4e00-\u9fff'\"“‘]))")  # a footnote, not a reference
NOTE_MARK_RE = re.compile(r"^(\d{1,3}|[*†‡§¶■•'’‘\u2460-\u2473])\s*\S")


def classify(blocks, body, info, first_page):
    title_done = False
    tol = max(1.0, 0.15 * body)
    # the title is the largest type at the top of the first page, not a smaller label above it ("Essay", "Open access")
    # a masthead (journal name, then a "Vol. / Issue" line) is never the title, however large its type
    first = [b for b in blocks if b["page"] == first_page]
    metadata = re.compile(r"https?://|www\.|\bdoi\s*[:/]|\bISSN\b", re.I)
    mast = [k for k, b in enumerate(first[:8]) if len(b["text"]) < 160 and (
        MASTHEAD_RE.search(b["text"]) or (
            metadata.search(b["text"]) and b["top"] < 0.45 * info[b["page"]]["h"]
            and any(o["top"] >= b["bottom"] and o["size"] > b["size"]
                    and o["top"] < 0.45 * info[o["page"]]["h"]
                    and o["size"] >= body + 2.5 and len(o["text"]) < 250
                    and o["n_lines"] <= 3 for o in first[k + 1:])))]
    for b in first[:mast[-1] + 1 if mast else 0]:
        b["_mast"] = True
    cands = [b["size"] for b in first if b["size"] >= body + 2.5 and not b.get("_mast")
             and b["top"] < 0.45 * info[b["page"]]["h"] and len(b["text"]) < 250]
    title_size = max(cands) if cands else 0.0
    title_block = None
    if not cands:  # a title set no larger than the text (small capitals): the first heading-like block under the masthead
        title_block = next((b for b in first if not b.get("_mast") and b["top"] < 0.45 * info[b["page"]]["h"]
                            and b["n_lines"] <= 3 and word_count(b["text"]) >= 3 and is_heading_block(b, body)
                            and not KNOWN_HEAD_RE.match(NUM_PREFIX_RE.sub("", b["text"]).strip())
                            and not re.match(r"^(\d+(\.\d+)*|[IVXLC]+)[.)]?\s", b["text"])), None)
    lowest = defaultdict(float)  # 每页每栏正文的最低位置；脚注在它下面
    for b in blocks:
        if abs(b["size"] - body) <= tol and len(b["text"]) > 80:
            k = (b["page"], b.get("key"))
            lowest[k] = max(lowest[k], b["bottom"])
    for b in blocks:
        t0 = b["text"]
        small = b["size"] <= min(body - 0.8, 0.92 * body)
        below = b["top"] >= lowest[(b["page"], b.get("key"))] - 1
        h0 = info[b["page"]]["h"]
        ref_head = len(t0) < 40 and REF_RE.match(NUM_PREFIX_RE.sub("", t0).strip().rstrip(":：").strip())
        b["_note"] = small and not b.get("text_box") and not ref_head and not CAPTION_RE.match(t0) and (
            below or (NOTE_MARK_RE.match(t0) and b["top"] > 0.6 * h0))
    for b in blocks:
        t = b["text"]
        h = info[b["page"]]["h"]
        letters = sum(1 for ch in t if ch.isalpha() or is_cjk(ch)) / max(1, len(t))
        if b.get("toc"):
            b["type"] = "para"
        elif b.get("list") and not b.get("_note") and not b.get("tab"):
            b["type"] = "para"
        elif b.get("sidebar"):
            b["type"] = "frag"
        elif b.get("tab") and not CAPTION_RE.match(t):
            b["type"], b["table"] = "frag", True
        elif TABLE_NOTE_RE.match(t) and b["top"] > 0.1 * h:  # "Notes: ..." under a table or figure
            b["type"], b["table"] = "frag", True
        elif b.get("_mast"):
            b["type"] = "frag"
        elif not title_done and b["page"] == first_page and (b is title_block or (
                b["size"] >= body + 2.5 and b["size"] >= title_size - 0.5 and b["top"] < 0.45 * h and len(t) < 250)):
            b["type"], b["level"], title_done = "heading", 0, True
            b["text"] = re.sub(r"\s*[*†‡§¶]+$", "", b.get("title_text", t))  # the footnote mark after a title is not part of it
            suffix = b.get("title_suffix")
            if suffix and b["text"].endswith(suffix):
                b["text"] = b["text"][:-len(suffix)].rstrip()
            for o in blocks:  # a journal line above the title (name, volume, DOI) is not part of the reading
                if o is b:
                    break
                if o["page"] == first_page and o["type"] in ("para", "note", "heading") and o.get("level") != 0:
                    o["type"] = "frag"
        elif CAPTION_RE.match(t) or (CAPTION_TITLE_RE.match(t) and word_count(t) <= 25):
            b["type"] = "caption"
        elif b.pop("_note", False) or (re.match(r"^[*■]\s", t) and b["top"] > 0.55 * h and len(t) < 700):
            b["type"] = "note"
        elif (b.get("math_style") or (b["n_lines"] <= 2 and symbolic_display(t))) and not b.get("table"):
            b["type"], b["equation"] = "frag", True
        elif b.get("mono", 0) >= 0.6:
            b["type"] = "frag"  # 代码清单
        elif is_heading_block(b, body):
            b["type"] = "heading"
        elif b.get("text_box") and letters > 0.5:
            b["type"] = "para"
        elif (word_count(t) < 6 and not end_terminal(t)) or (letters < 0.5 and len(t) < 160) \
                or (b["size"] <= body - 2.5 and b["n_lines"] <= 3):  # small type set into the text: an equation annotation
            b["type"] = "frag"
        else:
            b["type"] = "para"
    def drawn(b):
        """The table or figure box that holds block b, unless the box is a shaded text box (an abstract, a sidebar):
        a box that holds a body-size paragraph of three lines or more is text, and its heading is a heading."""
        cx, cy = (b["x0"] + b["x1"]) / 2, (b["top"] + b["bottom"]) / 2
        for f in info[b["page"]].get("figs", []):
            if f[0] - 2 <= cx <= f[2] + 2 and f[1] - 2 <= cy <= f[3] + 2:
                if any(o["page"] == b["page"] and o["type"] == "para" and o["n_lines"] >= 3 and o["size"] >= body - 0.5
                       and f[0] - 2 <= (o["x0"] + o["x1"]) / 2 <= f[2] + 2 and f[1] - 2 <= (o["top"] + o["bottom"]) / 2 <= f[3] + 2
                       for o in blocks):
                    return None
                return f
        return None

    for b in blocks:  # text set smaller than the body inside a drawn table or figure is table content
        if b["type"] in ("note", "para", "heading") and b.get("level") != 0 and b["size"] <= body - 0.5:
            if drawn(b):
                b["type"], b["table"] = "frag", True
    for b in blocks:
        if b["type"] == "heading" and b.get("level") != 0 and not NUM_HEAD_RE.match(b["text"]):
            if drawn(b):
                b["type"] = "frag"
    i = 0
    while i < len(blocks):
        j = i
        while j < len(blocks) and blocks[j]["type"] in ("heading", "frag", "caption"):
            j += 1
        run = blocks[i:j]
        small = [b for b in run if b["type"] == "heading" and b.get("level") != 0
                 and not NUM_HEAD_RE.match(b["text"]) and b["size"] < body + 1.5
                 and not b.get("force_heading") and b["bold"] < 0.85]
        if len(run) >= 3 and len(small) >= 2:
            for b in small:
                b["type"] = "frag"
        i = j + 1 if j == i else j
    i = 0
    while i < len(blocks):  # 连续三行以上的短"段落"是表格行
        j = i
        while (j < len(blocks) and blocks[j]["type"] in ("para", "frag") and len(blocks[j]["text"]) < 70
               and blocks[j]["page"] == blocks[i]["page"] and not STAT_RE.match(blocks[j]["text"])
               and sum(is_cjk(ch) for ch in blocks[j]["text"]) < 20):
            j += 1
        if j - i >= 3:
            run = blocks[i:j]
            numeric = sum(1 for b in run if NUMERIC_ROW_RE.match(b["text"]))
            if any(EQ_NUMBER_RE.search(b["text"]) for b in run) or (
                    numeric < len(run) / 2 and any(EQUATION_RE.search(b["text"]) for b in run)):
                # a display equation set over several short lines (fraction parts, the equation, its number)
                for b in run:
                    if b["type"] == "para" and word_count(b["text"]) < 6:
                        b["type"] = "frag"
                    elif b["type"] == "para" and EQUATION_RE.search(b["text"]) and not end_terminal(b["text"]):
                        b["type"] = "frag"
            elif aligned_cells(run):
                for b in run:
                    if not b.get("list") and not b.get("toc"):
                        b["type"] = "frag"
                        b["table"] = True
        i = max(j, i + 1)
    i = 0
    while i < len(blocks):  # a table set in small type reads as footnotes: short rows, many of them only numbers
        j = i
        while (j < len(blocks) and blocks[j]["type"] == "note" and len(blocks[j]["text"]) < 80
               and blocks[j]["page"] == blocks[i]["page"]):
            j += 1
        run = blocks[i:j]
        if len(run) >= 4 and sum(1 for b in run if NUMERIC_ROW_RE.match(b["text"].replace("1:", "").strip() or "x")
                                 or not re.search(r"[A-Za-z]{2,}", b["text"])) >= 0.35 * len(run):
            for b in run:
                b["type"], b["table"] = "frag", True
        i = max(j, i + 1)
    for b in blocks:  # a footnote is a sentence: not a stray formula fragment, not a capitalised address line
        if b["type"] != "note":
            continue
        words = re.findall(r"[A-Za-z]{3,}|[一-鿿]{2,}", b["text"])
        if (len(words) < 2 and len(b["text"]) < 40) or (b["text"].isupper() and len(b["text"]) < 120):
            b["type"] = "frag"
    for k, b in enumerate(blocks[:-1]):  # 标题后面紧跟的作者署名
        nb = blocks[k + 1]
        if b.get("level") == 0 and nb["type"] == "heading" and word_count(nb["text"]) <= 12 \
                and not NUM_HEAD_RE.match(nb["text"]) and not KNOWN_HEAD_RE.match(nb["text"].strip()) \
                and not CN_HEAD_RE.match(nb["text"].strip()):
            nb["type"] = "frag"
    box_groups = defaultdict(list)
    for b in blocks:
        if b.get("text_box"):
            box_groups[(b["page"], b["text_box"])].append(b)
    for group in box_groups.values():
        prose = [b for b in group if b["type"] == "para"]
        sizes = Counter()
        for b in prose:
            sizes[b["size"]] += len(b["text"])
        if sizes:
            local_body = sizes.most_common(1)[0][0]
            headline = min((b for b in group if b["type"] == "heading"), key=lambda b: b["top"], default=None)
            for b in group:
                if b["type"] == "heading" and b is not headline and b["size"] < local_body - 0.5:
                    b["type"] = "para"  # a smaller internal label is not the box's headline
    title = next((b for b in blocks if b.get("level") == 0), None)
    if title:
        after = sorted((b for b in blocks if b["page"] == first_page and b["top"] >= title["bottom"]), key=lambda b: b["top"])
        reach, previous_size = title["bottom"], title["size"]
        for b in after:
            if (b["size"] >= title["size"] - 0.5 and b["n_lines"] <= 3
                    and b["top"] - reach <= title["size"]):
                reach, previous_size = max(reach, b["bottom"]), b["size"]
                continue  # a subtitle belongs to the title region, not the byline
            marked = bool(re.search(r"[†‡∗*]", b["text"]))
            names = [w for w in re.findall(r"[A-Za-z]+", b["text"]) if w.lower() not in SMALL_WORDS]
            if ((b["top"] - reach > 2 * previous_size and not marked) or b["n_lines"] > 2 or len(names) < 2
                    or sum(w[0].isupper() for w in names) < 0.8 * len(names)
                    or end_terminal(b["text"]) or NUM_HEAD_RE.match(b["text"])
                    or KNOWN_HEAD_RE.fullmatch(b["text"])):
                break
            b["type"], b["byline"] = "frag", True
            reach, previous_size = max(reach, b["bottom"]), b["size"]
    heads = [b for b in blocks if b["type"] == "heading" and b.get("level") != 0]
    # Group heading sizes that differ by less than 8%: OCR text layers give same-rank headings slightly
    # different sizes, which must not turn into different levels.
    clusters = []
    for sz in sorted({round(b["size"], 1) for b in heads if not NUM_HEAD_RE.match(b["text"])}, reverse=True):
        if clusters and (clusters[-1][-1] - sz) / clusters[-1][-1] < 0.08:
            clusters[-1].append(sz)
        else:
            clusters.append([sz])
    rank = {sz: i for i, c in enumerate(clusters) for sz in c}
    sizes = [c[0] for c in clusters if c[0] >= body + 1.0]
    depths = [NUM_HEAD_RE.match(b["text"]).group(1).count(".") + 1 for b in heads
              if NUM_HEAD_RE.match(b["text"]) and re.match(r"^\d", b["text"])]
    deepest = max(depths) if depths else 0
    for b in heads:
        m = NUM_HEAD_RE.match(b["text"])
        if m and re.match(r"^\d", b["text"]):
            b["level"] = min(4, m.group(1).count(".") + 1)
        elif deepest == 0:
            b["level"] = min(3, rank.get(round(b["size"], 1), 0) + 1)
        else:
            b["level"] = min(4, deepest + 1) if rank.get(round(b["size"], 1), 0) >= len(sizes) else 1
    cn_heads = [b for b in heads if CN_HEAD_RE.match(b["text"].strip())]
    has_chapter = any(re.match(r"^第.+?[章部篇]", b["text"].strip()) for b in cn_heads)
    for b in cn_heads:
        t = b["text"].strip()
        if re.match(r"^第.+?[章部篇]", t):
            b["level"] = 1
        elif re.match(r"^第.+?节", t):
            b["level"] = 2
        elif re.match(r"^[一二三四五六七八九十]+、", t):
            b["level"] = 2 if has_chapter else 1
        else:
            b["level"] = 3 if has_chapter else 2

    last_page = max((b["page"] for b in blocks), default=first_page)
    tail = [b for b in blocks if b["page"] == last_page]
    contact = " ".join(b["text"] for b in tail)
    phone = re.search(r"(?:\+\d{1,3}|\b(?:tel|fax|phone)\b)[\d\s():+.-]{6,}", contact, re.I)
    if (last_page != first_page and re.search(r"https?://|www\.", contact)
            and (phone or re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]+", contact))
            and sum(len(b["text"]) for b in tail if b["n_lines"] <= 4) > len(contact) / 2):
        for b in tail:
            b["backmatter"] = True
            if b["type"] in ("frag", "note") and not b.get("equation"):
                b["type"] = "para"
    for b in blocks:
        if b.get("chapter"):
            b["type"], b["level"] = "heading", 0 if b["page"] == first_page else 1
    for i, b in enumerate(blocks[1:-1], 1):
        previous, following = blocks[i - 1], blocks[i + 1]
        if (b["type"] == "caption" and previous["type"] == "frag" and following["type"] == "para"
                and not previous.get("table") and not previous.get("math_style")
                and previous["size"] >= body - 0.5 and starts_lower(following["text"])
                and not end_terminal(previous["text"])):
            previous["type"] = "para"
    group_display_rows(blocks)


def group_display_rows(blocks):
    """Keep consecutive mathematical rows and their limits in one display region.

    Prose and new equation numbers delimit displays. Grouping never crosses a page,
    column, table or caption, and therefore does not undo paragraph endpoint checks.
    """
    out, i = [], 0
    while i < len(blocks):
        j = i
        while j < len(blocks):
            b = blocks[j]
            if (b["type"] not in ("para", "frag") or b.get("table")
                    or not (b.get("math_style") or is_display_equation(b))
                    or b.get("page") != blocks[i].get("page") or b.get("key") != blocks[i].get("key")
                    or (j > i and EQ_NUMBER_RE.match(b["text"]))):
                break
            j += 1
        if j - i >= 2 and any(b.get("math_style") for b in blocks[i:j]):
            run = blocks[i:j]
            display = dict(run[0], type="frag", equation=True,
                           text="\n".join(b["text"] for b in run),
                           n_lines=sum(b["n_lines"] for b in run),
                           x0=min(b["x0"] for b in run), x1=max(b["x1"] for b in run),
                           top=min(b["top"] for b in run), bottom=max(b["bottom"] for b in run))
            ink = [box for b in run for box in b.get("unmapped_ink", [])]
            if ink:
                display["x0"] = min(display["x0"], min(box[0] for box in ink))
                display["x1"] = max(display["x1"], max(box[1] for box in ink))
                display["top"] = min(display["top"], min(box[2] for box in ink))
                display["bottom"] = max(display["bottom"], max(box[3] for box in ink))
            # Tall operators can have incomplete font boxes. Use the whitespace
            # between neighboring prose and the mapped rows as the crop boundary.
            if i and blocks[i - 1].get("page") == display["page"] and blocks[i - 1].get("key") == display.get("key"):
                previous = blocks[i - 1]
                if previous["bottom"] < run[0]["top"]:
                    display["top"] = (previous["bottom"] + run[0]["top"]) / 2
            if j < len(blocks) and blocks[j].get("page") == display["page"] and blocks[j].get("key") == display.get("key"):
                following = blocks[j]
                if following["top"] > run[-1]["bottom"]:
                    display["bottom"] = (run[-1]["bottom"] + following["top"]) / 2
            out.append(display)
            i = j
        else:
            out.append(blocks[i])
            i += 1
    blocks[:] = out


def mark_sections(blocks):
    mode, n_refs, refs_level = "body", 0, 1
    for b in blocks:
        label = NUM_PREFIX_RE.sub("", b["text"]).strip().rstrip(":：").strip()
        if READING_RE.fullmatch(label):
            b["type"], b["level"], mode = "heading", 1, "reading"
            continue
        if b.get("backmatter"):
            mode = "body"
        if mode == "reading" and b["type"] == "heading":
            mode = "body"
        if mode == "reading" and b["type"] in ("para", "frag", "note") and not is_display_equation(b):
            b["type"], b["reading"] = "para", True
            continue
        if NOTES_RE.fullmatch(label):
            mode = "notes"
            continue
        if b["type"] == "heading":
            name = NUM_PREFIX_RE.sub("", b["text"]).strip().rstrip(":：").strip()
            if REF_RE.match(name):
                mode = "refs"
                refs_level = b.get("level", 1)
                b["type"] = "ref"
                continue
            if NOTES_RE.match(name):
                mode = "notes"
                continue
            # A bibliography can have its own subheadings. Only explicit textbook
            # body transitions at the reference heading's rank (or above) end it.
            chapter = re.match(r"^chapter\s+(?:\d+|[ivxlcdm]+)\b|^第[一二三四五六七八九十百零〇\d]+章|^\d+\s*[|｜]\s*\S", b["text"].strip(), re.I)
            solutions = re.fullmatch(r"solutions?|answer key|answers to (?:exercises|selected exercises)|习题解答|参考答案", name, re.I)
            resume = (mode == "refs" and b.get("level", 1) <= refs_level
                      and (chapter or solutions))
            if APPX_RE.match(name) or mode == "notes" or resume:
                mode = "body"
            elif mode == "refs":
                b["type"] = "ref"
                n_refs += 1
                continue
        elif mode == "refs" and not (b["type"] == "note" and FOOT_MARK_RE.match(b["text"])):
            b["type"] = "ref"
            n_refs += 1
        elif mode == "notes" and b["type"] in ("para", "note"):
            b["type"] = "note"
            b["endnote"] = True
    return n_refs


def mark_pull_quotes(blocks, body):
    """A pull quote is large type set into the column, between the two halves of a sentence: the paragraph before it
    stops without a full stop and the next one starts in lower case. It repeats the body text, so it becomes a fragment."""
    i = 0
    while i < len(blocks):
        k = i
        while (k < len(blocks) and blocks[k]["type"] in ("heading", "para") and blocks[k].get("level") != 0
               and blocks[k]["size"] >= body + 2 and blocks[k].get("key") == blocks[i].get("key")
               and blocks[k]["page"] == blocks[i]["page"]):
            k += 1
        if k > i and i > 0 and k < len(blocks) and sum(len(b["text"]) for b in blocks[i:k]) < 250:
            a, c = blocks[i - 1], blocks[k]
            if (a["type"] == "para" and c["type"] == "para" and a.get("key") == c.get("key") == blocks[i].get("key")
                    and a["page"] == c["page"] == blocks[i]["page"] and not end_terminal(a["text"])
                    and starts_lower(c["text"]) and abs(c["size"] - a["size"]) < 1.0):
                for b in blocks[i:k]:
                    b["type"], b["pull"] = "frag", True
        i = max(k, i + 1)


def block_span(b):
    """(top, bottom) of a block as fractions of its page, from a normalised bbox or from points; None when unknown."""
    bb = b.get("bbox")
    if bb and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb):
        return bb[1], bb[3]
    if all(k in b for k in ("top", "bottom", "ph")) and b["ph"]:
        return b["top"] / b["ph"], b["bottom"] / b["ph"]
    return None


def paragraph_continues(a, b, across_breaks=True):
    """Does paragraph b carry on from paragraph a? One rule for both engines.

    a is open (no full stop, or a hyphenated word) and b starts like a continuation: lower case, a comma, a joined CJK
    run, or a after-a-function-word. With across_breaks, a b that merely starts in another column or on another page
    also counts, provided the geometry (when known) says a ran to the bottom and b opens the next column or page."""
    a = dict(a, page=a.get("_end_page", a["page"]))
    if b.get("list") or (a.get("list") and a["page"] == b["page"] and a.get("key") == b.get("key")) or a.get("toc") or b.get("toc") or a.get("backmatter") or b.get("backmatter"):
        return False
    if a.get("closed") or end_terminal(a["text"]):
        return False
    if (starts_lower(b["text"]) or a["text"].endswith("-") or a["text"].rstrip().endswith(",")
            or (is_cjk(a["text"][-1]) and is_cjk(b["text"][0]))
            or last_word(a["text"]) in STOP_END or b["text"][:1] in ",;)"):
        return True
    if not across_breaks or not (b["page"] != a["page"] or b.get("key") != a.get("key")):
        return False
    sa, sb = block_span(a), block_span(b)
    if sa and sb:
        return sa[1] >= 0.55 and sb[0] <= 0.45 and (b["page"] != a["page"] or sb[0] < sa[1])
    return True


def join_open_paragraphs(blocks):
    """Join a paragraph that stops mid-sentence with the next one that carries on, when only figures, tables, equations,
    captions or footnotes sit between them (they stay where they are, after the joined paragraph). Headings and
    other paragraphs end the search. The joined paragraph keeps its first page and lists the others in `pages`."""
    out, joins = [], 0
    for b in blocks:
        if b["type"] == "para":
            j = len(out) - 1
            while j >= 0 and out[j]["type"] in ("frag", "note", "caption"):
                j -= 1
            if j >= 0 and out[j]["type"] == "para" and paragraph_continues(out[j], b, across_breaks=False):
                a = out[j]
                a["text"] = join_marked(a["text"], b["text"])
                a.setdefault("pages", {a["page"]}).add(b["page"])
                joins += 1
                continue
        out.append(b)
    return out, joins


def continuation_gap(a, b):
    if not all(k in a and k in b for k in ("top", "bottom", "size")):
        return True
    if a["page"] != b["page"] or a.get("key") != b.get("key"):
        sa, sb = block_span(a), block_span(b)
        return not (sa and sb) or (sa[1] >= 0.55 and sb[0] <= 0.45)
    size = max(a["size"], b["size"])
    gap = a.get("line_gap")
    return b["top"] - a["bottom"] <= (0.25 * size if gap is None else gap) + max(0.45 * size, 2.5)


def merge_continuations(blocks, body=None):
    if body:
        mark_pull_quotes(blocks, body)
    out, merges = [], 0
    for b in blocks:
        if (b["type"] == "note" and starts_lower(b["text"]) and out and out[-1]["type"] in ("para", "note")
                and out[-1]["page"] == b["page"] and re.match(r"^(\d{1,2}[A-Z]|['’]\s?[A-Z])", out[-1]["text"])):
            out[-1]["text"] = join_marked(out[-1]["text"], b["text"])
            out[-1]["type"] = "note"
            merges += 1
            continue
        if (b["type"] == "para" and out and out[-1]["type"] == "caption" and starts_lower(b["text"])
                and not end_terminal(out[-1]["text"]) and continuation_gap(out[-1], b)):
            out[-1]["text"] = join_marked(out[-1]["text"], b["text"])  # 图注跨栏的后半句
            merges += 1
            continue
        if not b.get("list") and b["type"] in ("para", "frag") and STAT_RE.match(b["text"]) and len(b["text"]) < 120 \
                and out and out[-1]["type"] == "para":
            out[-1]["text"] = out[-1]["text"] + "　" + b["text"]  # 调查结果行并入题目
            out[-1]["closed"] = True
            merges += 1
            continue
        if b["type"] == "para":
            j = len(out) - 1
            while j >= 0 and (out[j]["type"] in ("frag", "note", "caption")
                              or (body and out[j]["type"] == "heading" and out[j]["size"] <= body - 0.5)  # a table's header row
                              or (out[j]["type"] == "para" and bool(out[j].get("aside")) != bool(b.get("aside")))):
                j -= 1
            if j >= 0 and out[j]["type"] == "para":
                a = out[j]
                # A capitalized prose restart after a complete display is a new
                # paragraph, even if its lead-in ended in a function word.
                display_boundary = (any(x.get("equation") for x in out[j + 1:])
                                    and not starts_lower(b["text"]))
                if not display_boundary and paragraph_continues(a, b):
                    tail = dict(a, page=a.get("_end_page", a["page"]))
                    if b["page"] != tail["page"] or b.get("key") != tail.get("key"):
                        a["breaks"] = a.get("breaks", 0) + 1
                    text = a["text"]
                    between = out[j + 1:]
                    kept = []
                    for x in between:
                        if (x["type"] == "frag" and x["page"] == tail["page"] and x.get("key") == tail.get("key")
                                and x.get("mono", 0) < 0.5 and not x.get("pull") and not x.get("table") and not x.get("equation")):
                            text = join_marked(text, x["text"])  # 夹在段内的公式等
                            if is_display_equation(x):
                                a["has_math"] = True
                            if x["page"] == a["page"] and all(k in a and k in x for k in ("x0", "x1", "bottom")):
                                a["x0"], a["x1"] = min(a["x0"], x["x0"]), max(a["x1"], x["x1"])
                                a["bottom"] = max(a["bottom"], x["bottom"])
                        else:
                            kept.append(x)
                    a["text"] = join_marked(text, b["text"])
                    a.setdefault("superscripts", []).extend(b.get("superscripts", []))
                    a["jumps"] = a.get("jumps", 0) + b.get("jumps", 0)
                    a.setdefault("pages", {a["page"]}).add(b["page"])
                    geometry = ("page", "key", "x0", "x1", "top", "bottom", "pw", "ph", "bbox")
                    a.setdefault("_origin", {k: a[k] for k in geometry if k in a})
                    a.update({k: b[k] for k in geometry if k in b and k != "page"})
                    a["_end_page"] = b.get("_end_page", b["page"])
                    out[j + 1:] = kept
                    merges += 1
                    continue
        out.append(b)
    return out, merges


def link_notes(items):
    """给脚注编号，并挂到正文里引用它的段落上（段末或句末的小号数字）。"""
    notes = [it for it in items if it["type"] == "note"]
    used = set()
    for it in notes:
        m = re.match(r"^\s*(\d{1,2})[.．]?\s*", it["text"])
        q = re.match(r"^\s*['’‘]\s*", it["text"])
        c = re.match(r"^\s*([\u2460-\u2473])\s*", it["text"])
        if c and ord(c.group(1)) - 0x245F not in used:
            it["num"] = ord(c.group(1)) - 0x245F
            it["text"] = it["text"][c.end():].strip()
        elif m and int(m.group(1)) not in used:
            it["num"] = int(m.group(1))
            it["text"] = it["text"][m.end():].strip()
        elif q and 1 not in used:
            it["num"] = 1
            it["text"] = it["text"][q.end():].strip()
        elif re.match(r"^\s*[*■•†‡]", it["text"]):
            it["num"] = None  # 作者简介、致谢一类的星号注
            it["text"] = re.sub(r"^\s*[*■•†‡]\s*", "", it["text"])
            continue
        else:
            continue
        used.add(it["num"])
    by_num = {it["num"]: it for it in notes if it.get("num")}
    marker = re.compile(r"(?:(?<=[a-z][.,;:)\]”\"’])|(?<=[a-z]))(\d{1,2})(?=\s|$)|(?<=[a-z][.;:])['’]$")
    for it in items:
        if it["type"] != "para":
            continue
        found = [(int(m.group(1)) if m.group(1) else 1) for m in marker.finditer(it["text"].translate(SUP_DIGITS))]
        found += [ord(ch) - 0x245F for ch in CIRCLED_RE.findall(it["text"])]
        for n in found:
            note = by_num.get(n)
            pages = it.get("pages") or [it["page"]]
            if note and not note.get("ref") and note["page"] in pages:  # 脚注和引用它的段落在同一页
                note["ref"] = it["id"]
                it.setdefault("notes", []).append(note["id"])
    return items


OCR_LABEL_RE = re.compile(r"\b(Question|Table|Figure|Fig\.|Problem|Item|Hypothesis|Proposition|Experiment)\s+[lI]([a-z]?)\b")
ROMAN_USE_RE = re.compile(r"\b(?:Table|Figure|Fig\.|Experiment|Section|Part|Study|Hypothesis|Proposition|Appendix|Chapter)\s+"
                          r"(?:II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b|^(?:II|III|IV|V|VI|VII|VIII|IX|X)[.)]?\s+\S")


NUMERIC_ROW_RE = re.compile(r"^[\d.,%()\s±−–-]+$")  # a table row of numbers only
MATH_TOKEN_RE = re.compile(r"^[A-Za-z]$|^[A-Za-z]?\d+$|[=+−×·/√∑∏∫^_()|\[\]{}<>≤≥≈∞∂]")


def math_dense(text):
    """A paragraph that is mostly formula: an '=' and most tokens are single letters, numbers or operators."""
    toks = text.split()
    if "=" not in text or len(toks) < 4 or len(text) > 600:
        return False
    return sum(1 for t in toks if MATH_TOKEN_RE.search(t)) / len(toks) >= 0.5


EQUATION_RE = re.compile(r"[=≈≤≥∑∫√∏]|\b(?:ln|log|exp)\(|\b[a-zA-Z]\s*[=<>]\s*[\d(a-zA-Z]")
EQ_NUMBER_RE = re.compile(r"^\(\d{1,3}[a-z]?\)|\(\d{1,3}[a-z]?\)[.,]?$")


def is_display_equation(b):
    """A fragment that is a display equation: short, not a table row, with an operator or an equation number."""
    t = b["text"]
    return (b["type"] == "frag" and not b.get("table") and (b.get("equation") or (len(t) < 160
            and (bool(EQUATION_RE.search(t)) or bool(EQ_NUMBER_RE.search(t))))))


def uses_roman_numerals(blocks):
    """True when the reading numbers anything with Roman numerals, so a lone 'I' is not an OCR misread of '1'."""
    return any(ROMAN_USE_RE.search(b["text"]) for b in blocks if b["type"] in ("para", "heading", "caption"))


def finalize(blocks):
    note_numbers = defaultdict(set)
    for b in blocks:
        if b["type"] == "note":
            mark = FOOT_MARK_RE.match(b["text"])
            if mark and mark.group(1).strip().isdigit():
                note_numbers[b["page"]].add(mark.group(1).strip())
    counters, items = Counter(), []
    prefix = {"para": "P", "heading": "H", "caption": "C", "note": "N", "frag": "F"}
    roman = uses_roman_numerals(blocks)
    counters["roman_rewrites"] = 0
    counters["roman_suppressed"] = roman
    for b in blocks:
        if b["type"] == "ref":
            continue
        k = prefix[b["type"]]
        counters[k] += 1
        text = b["text"].strip()
        # Preserve marks under the existing link_notes convention, but require a
        # corresponding note. Raised powers and squared table labels are not notes.
        for previous, mark in b.get("superscripts", []):
            if any(mark in note_numbers[p] for p in b.get("pages", {b["page"]})):
                text = re.sub(re.escape(previous) + r"\s+" + re.escape(mark) + r"(?!\d)",
                              lambda _: previous + mark, text, count=1)
        if not roman:
            text, n = OCR_LABEL_RE.subn(lambda m: f"{m.group(1)} 1{m.group(2)}", text)
            counters["roman_rewrites"] += n
        origin = dict(b, **b.get("_origin", {}))
        it = {"id": f"{k}{counters[k]}", "type": b["type"], "text": text, "page": origin["page"]}
        if b["type"] == "heading":
            it["level"] = b.get("level", 1)
        if b.get("table"):
            it["table"] = True
        pages = sorted(b.get("pages", {b["page"]}))
        if len(pages) > 1:
            it["pages"] = pages
        if all(k in origin for k in ("x0", "top", "x1", "bottom", "pw", "ph")) and origin["pw"] and origin["ph"]:
            it["bbox"] = [round(origin["x0"] / origin["pw"], 4), round(origin["top"] / origin["ph"], 4),
                          round(origin["x1"] / origin["pw"], 4), round(origin["bottom"] / origin["ph"], 4)]
        if is_display_equation(b):
            it["equation"] = True
        if b.get("has_math") or (b["type"] == "para" and math_dense(text)):
            it["has_math"] = True
        items.append(it)
    return link_notes(items), counters


# ---------- 自检：切分结果的好坏 ----------

REF_ENTRY_RE = re.compile(r"^\W{0,2}(?:\d{1,3}[.\]]?\s+)?[A-Z][\w'’-]+,?\s+(?:[A-Z]{1,3}\b|[A-Z]\.)")
REF_TAIL_RE = re.compile(r"\b(?:19|20)\d\d\b[^.]{0,30}[;:,]\s*\d+\s*[(:]?\s*\d*|\b\d+\s*:\s*\d+\s*[-–]\s*\d+")


def looks_like_reference(text):
    """An author-year or numbered bibliography entry: leading surname and initials, a year, volume and pages."""
    return len(text) < 600 and bool(REF_ENTRY_RE.match(text)) and bool(REF_TAIL_RE.search(text))


def layout_signals(blocks, n_pages, info=None):
    """Simple signals that a split went wrong. Returns (score, reasons); a lower score is a better split."""
    paras = [b for b in blocks if b["type"] == "para"]
    if not paras:
        return 99.0, ["no paragraphs"]
    n = len(paras)
    # A footnote sits at the foot of its page; a "footnote" in the upper half is body text or a reference list that
    # was set small. A footnote-heavy paper is fine as long as its notes are where footnotes are.
    notes = 0
    for b in blocks:
        if b["type"] == "note" and not b.get("endnote"):
            span = block_span(b)
            if span is not None and span[0] < 0.45:
                notes += 1
    heads = sum(1 for b in blocks if b["type"] == "heading" and b.get("level") != 0
                and not re.match(r"^\d+(?:\.\d+)*[.)]?\s|^[A-Za-z]+\s+\d{1,3}\s*[:.)]", b["text"]))
    prose = [b for b in paras if not any(b.get(k) for k in ("list", "toc", "backmatter", "reading"))]
    lower = sum(1 for b in prose if starts_lower(b["text"]) and not is_cjk(b["text"].lstrip()[:1])) / max(1, len(prose))
    open_end = sum(1 for b in prose if not end_terminal(b["text"])) / max(1, len(prose))
    zigzag = sum(1 for b in paras if b.get("jumps", 0) >= 2) / n
    leak = sum(1 for b in paras if not b.get("reading") and looks_like_reference(b["text"]))
    heads_pp = heads / max(1, n_pages)
    reasons = []
    overflow = [p for p, data in (info or {}).items() if data.get("text_overflow")]
    if overflow:
        reasons.append(f"raster-backed text layer extends beyond page bounds on pages {overflow}")
    if lower > 0.12:
        reasons.append(f"{lower:.0%} of the paragraphs start in lower case")
    if open_end > 0.3:
        reasons.append(f"{open_end:.0%} of the paragraphs end without a full stop")
    if zigzag > 0.08:
        reasons.append(f"{zigzag:.0%} of the paragraphs jump between distant columns")
    if heads_pp > 2.5:
        reasons.append(f"{heads_pp:.1f} headings per page")
    if notes >= 5 and notes >= 0.2 * n:
        reasons.append(f"{notes} footnotes in the upper half of the page, next to {n} paragraphs")
    if leak >= 3 and leak >= 0.1 * n:
        reasons.append(f"{leak} paragraphs look like reference entries")
    page_blocks = defaultdict(list)
    for b in blocks:
        if b["type"] != "ref":
            page_blocks[b.get("page")].append(b)
    fragmented, flooded, hidden_lists = [], [], []
    prose_size = statistics.median(b.get("size", 0) for b in paras)
    for page, rows in page_blocks.items():
        total = sum(len(b["text"]) for b in rows) or 1
        if any(b["type"] == "frag" and not b.get("table") and not b.get("equation")
               and b.get("size", prose_size) >= prose_size - 0.8
               and LIST_MARK_RE.match(b["text"]) for b in rows):
            hidden_lists.append(page)
        frags = [b for b in rows if b["type"] == "frag" and word_count(b["text"]) >= 6
                 and not b.get("equation") and not b.get("pull") and not TABLE_NOTE_RE.match(b["text"])
                 and sum(c.isalpha() for c in b["text"]) > 0.5 * len(b["text"])]
        if sum(len(b["text"]) for b in frags) > total / 2:
            fragmented.append(page)
        high_notes = [b for b in rows if b["type"] == "note" and not b.get("endnote")
                      and block_span(b) and block_span(b)[0] < 0.45]
        if high_notes and sum(len(b["text"]) for b in rows if b["type"] == "note") > total / 2:
            flooded.append(page)
    # Tukey's outer fence on log length: document-relative and robust to ordinary
    # right-skewed paragraph lengths, unlike a fixed character limit.
    lengths = sorted(math.log(max(1, len(b["text"]))) for b in paras)
    q1, q3 = lengths[len(lengths) // 4], lengths[3 * len(lengths) // 4]
    long_pages = sorted({b["page"] for b in paras if math.log(max(1, len(b["text"]))) > q3 + 3 * (q3 - q1)
                         and b.get("breaks", 0) >= 2})
    if hidden_lists:
        reasons.append(f"list markers hidden in fragments on pages {hidden_lists}")
    if fragmented:
        reasons.append(f"most page text is in fragments on pages {fragmented}")
    if flooded:
        reasons.append(f"footnotes dominate page text outside a notes section on pages {flooded}")
    if long_pages:
        reasons.append(f"paragraph length outliers crossing multiple breaks on pages {long_pages}")
    score = (4 * lower + 2 * open_end + 4 * zigzag + 0.4 * max(0.0, heads_pp - 2.0)
             + (min(1.0, notes / n) if notes >= 5 else 0) + 3 * leak / n)
    return score, reasons


def segment_text_layer(pdf, pnos, columns, cache=None):
    """One full pass of the default tier: blocks, classification, references, continuations."""
    blocks, body, info, stats = from_pdf_text(pdf, pnos, columns, cache)
    classify(blocks, body, info, pnos[0])
    n_refs = mark_sections(blocks)
    blocks, merges = merge_continuations(blocks, body)
    score, reasons = layout_signals(blocks, len(pnos), info)
    return {"blocks": blocks, "body": body, "info": info, "stats": stats, "n_refs": n_refs,
            "merges": merges, "score": score, "reasons": reasons, "columns": columns}


def choose_columns(pdf, pnos, columns):
    """Run the default tier. With columns=auto, a split that looks bad is retried with 1, 2 and 3 columns and the
    best result is kept. Returns (result, message lines for the person running the script)."""
    cache = {}
    first = segment_text_layer(pdf, pnos, columns, cache)
    msgs = []
    best = first
    if columns == "auto":
        layout_reasons = [r for r in first["reasons"] if not any(label in r for label in
                          ("most page text", "dominate page text", "length outliers", "raster-backed", "list markers hidden"))]
        if layout_reasons:
            tried = [first]
            for c in ("1", "2", "3"):
                tried.append(segment_text_layer(pdf, pnos, c, cache))
            best = min(tried, key=lambda r: r["score"])  # ties keep the earlier (auto) result
            if best is first:
                msgs.append("自检：自动分栏的结果有疑点（" + "；".join(first["reasons"]) + "），试过 --columns 1/2/3 都没有更好，保留自动分栏。")
            else:
                msgs.append(f"自检：自动分栏有疑点（{'；'.join(first['reasons'])}），改用 --columns {best['columns']}"
                            f"（疑点 {len(best['reasons'])} 个，自动分栏 {len(first['reasons'])} 个）。")
        elif first["reasons"]:
            msgs.append("自检：自动分栏保留，需检查内容区域（" + "；".join(first["reasons"]) + "）。")
        else:
            cols = best["stats"]["multi_col"] + best["stats"]["two_col"]
            msgs.append(f"自检：分栏自动识别通过（多栏页 {cols}/{len(pnos)}），未发现串栏或混入参考文献的迹象。")
    elif first["reasons"]:
        msgs.append("自检：--columns " + columns + " 的结果有疑点（" + "；".join(first["reasons"]) + "）。")
    else:
        msgs.append(f"自检：--columns {columns} 的结果未发现串栏迹象。")
    if best["reasons"]:
        msgs.append("给执行的 agent（不是给用户的）：切分仍有疑点，自己按顺序处理，不要让用户动手："
                    "先看这行说的页，再试 --pages 缩小范围或 --columns 1/2/3；已装 MinerU 就加 --engine mineru；"
                    "最后手工提取文字（pdfplumber 按栏抽取，去掉页眉和参考文献），写成 --text 格式再用 segment.py --text，"
                    "之后给 render.py 传 --pdf。详见 SKILL.md 第 1 步。")
    return best, msgs


# ---------- 纯文本 ----------

def from_text(path):
    items, buf, page = [], [], None

    def flush():
        if buf:
            text = ""
            for ln in buf:
                text = join_marked(text, ln)
            typ = "caption" if CAPTION_RE.match(text) else "para"
            items.append({"type": typ, "text": text, "page": page})
            buf.clear()

    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = clean_text(raw)
        m = re.match(r"^\[\[\s*p\.?\s*(\d+)\s*\]\]$", line, re.I)
        if m:
            flush()
            page = int(m.group(1))
            continue
        if not line:
            flush()
            continue
        h = re.match(r"^(#{1,4})\s+(.+)$", line)
        if h:
            flush()
            items.append({"type": "heading", "level": len(h.group(1)), "text": h.group(2), "page": page})
            continue
        buf.append(line)
    flush()
    for it in items:
        it.setdefault("n_lines", 1)
    return items


# ---------- 输出 ----------

def page_tag(it, labels):
    p = it.get("page")
    if p is None:
        return ""
    lab = labels.get(str(p))
    return f"[p{p}/印{lab}]" if lab else f"[p{p}]"


def write_outputs(doc, out, chunk_chars):
    its = [i for i in doc["items"] if isinstance(i.get("text"), str)]
    resolved, doc_decisions = resolve_hyphens([i["text"] for i in its])
    for i, t in zip(its, resolved):
        i["text"] = t
    write_outputs.decisions = doc_decisions
    for i, t in zip(its, fix_split_ligatures([i["text"] for i in its])):
        i["text"] = t
    out.mkdir(parents=True, exist_ok=True)
    (out / "paragraphs.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for old in out.glob("paragraphs_part*.txt"):
        old.unlink()
    labels = doc.get("page_labels", {})
    chunks, buf, size = [], [], 0
    for it in doc["items"]:
        tag = page_tag(it, labels)
        t = it["type"]
        if t == "heading":
            line = f"\n{'#' * max(1, it.get('level', 1) + 1)} {it['id']} {tag} {it['text']}"
        elif t == "para":
            line = f"{it['id']} {tag}\n{it['text']}\n"
        elif t == "caption":
            line = f"{it['id']} {tag} 图表说明\n{it['text']}\n"
        elif t == "note":
            line = f"{it['id']} {tag} 脚注\n{it['text']}\n"
        else:
            line = f"（{it['id']} 碎片 {tag}）{it['text'][:120]}"
        if buf and ((size > 0.7 * chunk_chars and t == "heading") or size + len(line) > chunk_chars):
            chunks.append(buf)
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        chunks.append(buf)
    names = []
    for i, ch in enumerate(chunks, 1):
        name = f"paragraphs_part{i:02d}.txt"
        head = f"# {doc.get('source', '')} 第 {i}/{len(chunks)} 块（编号固定，导读只引用这些编号）\n"
        (out / name).write_text(head + "\n".join(ch) + "\n", encoding="utf-8")
        names.append(name)
    return names


def main():
    use_utf8()
    ap = argparse.ArgumentParser(description="把读物切成编号段落")
    ap.add_argument("input")
    ap.add_argument("--out", required=True, help="工作目录")
    ap.add_argument("--text", action="store_true", help="输入是纯文本")
    ap.add_argument("--pages", help="只处理这些 PDF 页，如 3-28 或 1,3-9")
    ap.add_argument("--columns", choices=["auto", "1", "2", "3"], default="auto",
                    help="auto detects the columns of every page and, when the result looks wrong, tries the other settings")
    ap.add_argument("--ocr", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--lang", default="eng", help="OCR languages, e.g. eng, chi_sim or eng+chi_sim")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--chunk-chars", type=int, default=12000)
    ap.add_argument("--engine", choices=["auto", "pdfplumber", "mineru"], default="auto",
                    help="auto uses MinerU when it is installed (see requirements.txt), otherwise pdfplumber")
    args = ap.parse_args()
    src = Path(args.input)
    out = Path(args.out)
    if not src.exists():
        sys.exit(f"找不到文件：{src}")

    report = []
    is_text = args.text or src.suffix.lower() in (".txt", ".md")
    engine = args.engine
    if engine == "auto" and not is_text:
        from mineru_backend import available
        engine = "mineru" if available() else "pdfplumber"
    doc = None
    if engine == "mineru" and not is_text:
        from mineru_backend import convert, run
        if args.ocr != "auto" or args.columns != "auto" or args.lang != "eng":
            print("注意：MinerU 引擎自己判断 OCR 和分栏，--ocr、--columns、--lang 在这里不起作用")
        try:
            sc_path = run(src, out / "_mineru", args.pages)
            doc = convert(json.loads(sc_path.read_text(encoding="utf-8")), src.name, str(src.resolve()))
            if not any(i["type"] == "para" for i in doc["items"]):
                raise SystemExit("MinerU 没有切出任何段落")
        except SystemExit as e:
            if args.engine != "auto":
                sys.exit(f"{e}\n改用 --engine pdfplumber 可以跳过 MinerU")
            print(f"MinerU 失败（{str(e).splitlines()[0]}），改用 pdfplumber 引擎；--engine pdfplumber 可以直接跳过 MinerU")
            doc = None
    if doc is not None:
        from crops import crop_regions
        names = write_outputs(doc, out, args.chunk_chars)
        made = crop_regions(src, doc["items"], out / "crops")
        if made:
            doc["crops"] = {k: str(Path(v).relative_to(out)) for k, v in made.items()}
            (out / "paragraphs.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        c = Counter(i["type"] for i in doc["items"])
        print(f"模式：{doc['mode']}")
        print(f"条目：段落 P {c['para']}，标题 H {c['heading']}，图表说明 C {c['caption']}，脚注 N {c['note']}，"
              f"碎片 F {c['frag']}（不编入导读），参考文献 {doc['refs_excluded']} 条（不编入导读）")
        print(f"公式 {sum(1 for i in doc['items'] if i.get('equation'))} 条（{sum(1 for i in doc['items'] if i.get('tex'))} 条带 LaTeX），"
              f"表格 {sum(1 for i in doc['items'] if i.get('html'))} 张；裁剪图 {len(made)} 张到 {out / 'crops'}")
        if doc.get("title_guess"):
            print(f"标题猜测：{doc['title_guess'][:80]}")
        print(f"输出：{out / 'paragraphs.json'}；" + "，".join(names))
        print("下一步：逐个完整阅读 part 文件，抽查有无串栏、段落被切断；公式转写时对照 crops/ 里的图。")
        return
    if is_text:
        raw = from_text(src)
        mode, page_count, pnos = "纯文本", None, []
        blocks = [dict(b, size=10.0, bold=0.0, top=0, bottom=0) for b in raw]
        for b in blocks:
            if b["type"] == "para" and word_count(b["text"]) < 3 and not end_terminal(b["text"]):
                b["type"] = "frag"
        n_refs = mark_sections(blocks)
        blocks, merges = blocks, 0
        stats = {"two_col": 0, "removed": 0, "labels": []}
    else:
        try:
            import pdfplumber
        except ImportError:
            sys.exit("缺少 pdfplumber：pip install pdfplumber")
        with pdfplumber.open(str(src)) as pdf:
            page_count = len(pdf.pages)
            pnos = parse_pages(args.pages, page_count)
            if not pnos:
                sys.exit("--pages 选出的页为空")
            chars = [len(pdf.pages[p - 1].chars) for p in pnos]
            if pnos and not args.pages:
                first_text = pdf.pages[pnos[0] - 1].extract_text() or ""
                if JSTOR_RE.search(first_text) and len(pnos) > 1:
                    report.append(f"第 {pnos[0]} 页是 JSTOR 封面，已跳过")
                    pnos, chars = pnos[1:], chars[1:]
            text_counts = {}
            ocr_pnos = ocr_page_numbers(pdf, pnos, args.ocr, text_counts)
            text_pnos = [p for p in pnos if p not in ocr_pnos]
            usable_pages = [p for p in pnos if text_counts[p] >= 30]
            usable = bool(usable_pages)
            if not usable and not ocr_available(args.lang):
                sys.exit("给执行的 agent（不是给用户的）：没有可用文字层。已装 MinerU 就用 --engine mineru；否则自行安装 Tesseract、Poppler 和 OCR Python 依赖后重试，不要让用户动手。")
            if ocr_pnos and not ocr_available(args.lang):
                skipped = [p for p in ocr_pnos if p not in usable_pages]
                text_pnos = sorted(set(text_pnos) | set(usable_pages))
                report.append(f"OCR unavailable; using text layer, skipped image-only pages {skipped}.")
                ocr_pnos = []
            if not text_pnos:
                mode = f"OCR（tesseract {args.lang}）"
                blocks, body, info, stats = from_ocr(src, pnos, args.lang, args.dpi)
            else:
                mode = "PDF 文字层"
                if ocr_pnos:
                    blocks, body, info, stats = from_pdf_text(pdf, text_pnos, args.columns)
                else:
                    res, check_msgs = choose_columns(pdf, text_pnos, args.columns)
                    blocks, body, info, stats = res["blocks"], res["body"], res["info"], res["stats"]
                    n_refs, merges = res["n_refs"], res["merges"]
                    report.extend(check_msgs)
                if ocr_pnos:
                    # Classify each extraction mode at its own font-size scale. OCR character
                    # heights are not PDF font sizes. Preserve page order before continuation.
                    classify(blocks, body, info, pnos[0])
                    ob, osize, oi, ostats = from_ocr(src, ocr_pnos, args.lang, args.dpi)
                    classify(ob, osize, oi, pnos[0])
                    blocks.extend(ob)
                    blocks.sort(key=lambda b: b["page"])
                    info.update(oi)
                    stats["removed"] += ostats["removed"]
                    stats["labels"].extend(ostats["labels"])
                    mode = f"PDF 文字层 + OCR（tesseract {args.lang}；页 {ocr_pnos}）"
                if args.ocr == "off":
                    empty = [p for p in pnos if chars[pnos.index(p)] < 30]
                    if empty:
                        report.append(f"警告：页 {empty} 几乎没有文字层；可用 --ocr auto")
        if text_pnos and not ocr_pnos:
            pass  # classified, sectioned and merged by choose_columns
        else:
            if not (ocr_pnos and text_pnos):
                classify(blocks, body, info, pnos[0])
            n_refs = mark_sections(blocks)
            blocks, merges = merge_continuations(blocks, body)

    items, counters = finalize(blocks)
    labels = page_labels_from(stats["labels"], pnos) if pnos else {}
    title = next((i["text"] for i in items if i["type"] == "heading" and i.get("level") == 0), "")
    doc = {"version": 2, "source": src.name, "source_path": str(src.resolve()), "mode": mode, "page_count": page_count,
           "pages_processed": [pnos[0], pnos[-1]] if pnos else None,
           "page_labels": labels, "title_guess": title, "items": items}
    if counters["P"] == 0:
        sys.exit("没有切出任何段落。扫描件试试 --ocr on；版式特殊时可以把正文整理成纯文本再用 --text。")
    names = write_outputs(doc, out, args.chunk_chars)
    made = {}
    if pnos:
        from crops import crop_regions
        made = crop_regions(src, items, out / "crops")
        if made:
            doc["crops"] = {k: str(Path(v).relative_to(out)) for k, v in made.items()}
            (out / "paragraphs.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    paras = [i for i in items if i["type"] == "para"]
    long_p = [f"{i['id']}（{len(i['text'])}）" for i in paras if len(i["text"]) > 2500]
    short_p = [i["id"] for i in paras if len(i["text"]) < 100]
    print(f"模式：{mode}")
    if pnos:
        extra = (f"；双栏页 {stats['two_col']}" if stats["two_col"] else "") + (f"；三栏或更多栏页 {stats['multi_col']}" if stats.get("multi_col") else "")
        print(f"页数：处理 {len(pnos)} 页（PDF 第 {pnos[0]}-{pnos[-1]} 页，共 {page_count} 页）{extra}")
    print(f"条目：段落 P {counters['P']}，标题 H {counters['H']}，图表说明 C {counters['C']}，"
          f"脚注 N {counters['N']}，碎片 F {counters['F']}（不编入导读），参考文献 {n_refs} 条（不编入导读）")
    if made:
        print(f"裁剪了 {len(made)} 个公式/表格区域到 {out / 'crops'}（公式转写时对照这些图）")
    if counters["roman_rewrites"]:
        print(f"OCR 修正：把 {counters['roman_rewrites']} 处 “Figure l / Experiment I” 改成了 1（文档未使用罗马数字编号）")
    elif counters.get("roman_suppressed"):
        print("文档使用罗马数字编号（Table II 等），未做 “Figure l → Figure 1” 的 OCR 修正；若有 l 误读为 1 的地方请在阅读时留意")
    breaks = sum(b.get("breaks", 0) for b in blocks)
    if pnos:
        lab = "已识别" if labels else "未识别"
        print(f"删除页眉页脚和页码 {stats['removed']} 行；印刷页码{lab}；跨栏跨页续接合并 {merges} 处"
              + (f"（其中段落跨栏或跨页接上 {breaks} 处）" if breaks else ""))
    if title:
        print(f"标题猜测：{title[:80]}")
    for r in report:
        print(r)
    if long_p:
        print("超长段落（可能漏切）：" + "，".join(long_p[:12]))
    if short_p:
        print(f"很短的段落（<100 字符，可能是误切或标题）：{'，'.join(short_p[:20])}" + (" 等" if len(short_p) > 20 else ""))
    print(f"输出：{out / 'paragraphs.json'}；" + "，".join(names))
    print("下一步：逐个完整阅读 part 文件，抽查有无串栏、页眉混入、段落被切断。")


if __name__ == "__main__":
    main()
