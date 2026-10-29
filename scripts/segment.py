#!/usr/bin/env python3
"""把读物切成编号段落，供导读使用。

用法：
  python segment.py reading.pdf --out WORK
  python segment.py reading.pdf --out WORK --pages 3-28 --columns 2
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
import unicodedata
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIGATURES, clean_text, drop_cap_for, fix_split_ligatures, is_cjk, put_drop_cap, use_utf8  # noqa: E402

CAPTION_RE = re.compile(r"^(fig(ure)?s?\.?|table|tab\.|exhibit|chart|plate|图|表)\s*(?:(?:[A-Z][.-]?)?\d+|[IVXLCDM]+)(?:[.-]\d+)?\s*([.:：|—?]|$)", re.I)
NUM_HEAD_RE = re.compile(r"^(\d+(\.\d+){0,3}|[IVXLC]+|[A-H])[.)]?\s+(\S)")
NUM_PREFIX_RE = re.compile(r"^(\d+(\.\d+){0,3}|[IVXLC]+|[A-H])[.)]?\s+")
REF_RE = re.compile(r"^(references?|bibliography|works cited|literature cited|reference list|参考文献|引用文献)$", re.I)
NOTES_RE = re.compile(r"^(notes|endnotes|注释|尾注)$", re.I)
APPX_RE = re.compile(r"^(appendix|appendices|附录)\b", re.I)
PAGE_NUM_RE = re.compile(r"^[\s\-–—|]*(?:page\s+)?(\d{1,4}|[ivxlcdm]{1,7})[\s\-–—|]*$", re.I)
BANNER_RE = re.compile(r"\b(vol\.|volume|pages|pp\.)\s*\d", re.I)
CAPTION_TITLE_RE = re.compile(r"^(?i:fig(ure)?\.?|table|exhibit|chart|图|表)\s*(?:(?:[A-Z][.-]?)?\d+|[IVXLCDM]+)(?:[.-]\d+)?(\s+[A-Z]|\s*[\u4e00-\u9fff])")
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

def terminal_text(text, superscripts=None):
    t = text.rstrip()
    if superscripts is not None:
        for previous, mark in superscripts:
            if t.endswith(mark) and t[:-len(mark)].rstrip().endswith(previous):
                t = t[:-len(mark)].rstrip()
    # Geometry supplements the textual fallback: OCR may leave a reference
    # number on the baseline. The digit look-behind preserves decimal values.
    t = re.sub(r"((?<!\d)[.!?。！？”\"’)\]])\s*\d{1,3}$", r"\1", t)  # 去掉句末脚注号
    return t.rstrip(CLOSERS)


def end_terminal(text, superscripts=None):
    t = terminal_text(text, superscripts)
    return bool(t) and t[-1] in TERMINAL


def starts_lower(text):
    s = text.lstrip(" \"'“‘([")
    return bool(s) and s[0].islower()


def last_word(text):
    m = re.search(r"([A-Za-z]+)\W*$", text)
    return m.group(1).lower() if m else ""


MASTHEAD_RE = re.compile(r"\b(vol\.|volume|issue|no\.)\s*[\dIVXLCM]+", re.I)
TABLE_NOTE_RE = re.compile(r"^(\*{0,3}\s*(notes?|source|sources)\s*:|\*{1,3}\s*(p\s*[<=]|significant))", re.I)
ACCENT_RE = re.compile(r"^[̀-ͯˆ-˟¨´`]+$")
PUNCT_TOKEN_RE = re.compile(r"^[)\]},;:.!?’”]+$")


def join_words(a, b):
    if not a:
        return b
    if is_cjk(a[-1]) and is_cjk(b[:1]):
        return a + b
    if re.search(r"\w-$", a) and b[:1].isalpha():
        return a + b  # an encoded intra-line compound keeps its explicit hyphen
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
    if a.endswith("-") and len(a) > 1 and a[-2].isalpha() and b[:1].isalpha():
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
                # An independently occurring plural also attests the second word.
                keep = bool(pieces[first] and (pieces[rfirst] or pieces[rfirst + "s"])
                            and len(first) > 2 and len(rfirst) > 2)
            decisions.append((left + right, left + "-" + right, keep))
            # A capital can start a separate label or heading. Without document
            # evidence for the compound, retain that boundary instead of gluing it.
            replacement = "-" if keep else "- " if right[:1].isupper() else ""
            x = x[:k] + replacement + x[k + 1:]
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
            props["fallback_cids"] = {}
            props["symbolic"] = bool(desc.get("Flags", 0) & 4) and not bool(desc.get("Flags", 0) & 32)
            props["pua_glyphs"] = {}
            props["glyph_names"] = {}
            props["glyph_bounds"] = {}
            if not spec.get("DescendantFonts") and spec.get("Encoding"):
                enc = resolve1(spec["Encoding"])
                if isinstance(enc, dict):
                    props["fallback_cids"].update(EncodingDB.get_encoding(literal_name(enc.get("BaseEncoding")), resolve1(enc.get("Differences", []))))
                    code=0
                    for value in resolve1(enc.get("Differences", [])):
                        if isinstance(value,int):
                            code=value
                        else:
                            props["glyph_names"][code]=literal_name(value)
                            code+=1
                else:
                    props["fallback_cids"].update(EncodingDB.get_encoding(literal_name(enc)))
            from pdfminer.fontmetrics import FONT_METRICS
            # PDF Reference 5.5: Adobe's standard Type 1 .notdef is blank.
            # Only unassigned controls in an unembedded standard font qualify;
            # zero advance alone does not prove that a combining glyph is blank.
            # https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.3.pdf
            props["blank_controls"] = (name in FONT_METRICS and literal_name(spec.get("Subtype"))=="Type1"
                                        and not any(desc.get(k) for k in ("FontFile","FontFile2","FontFile3"))
                                        and not spec.get("ToUnicode"))
            stream = resolve1(desc.get("FontFile2") or desc.get("FontFile3"))
            if desc.get("FontFile"):
                try:
                    from fontTools.t1Lib import T1Font
                    from fontTools.agl import toUnicode
                    program = T1Font.__new__(T1Font)
                    program.data = resolve1(desc["FontFile"]).get_data()
                    program.encoding = "ascii"
                    program.parse()
                    props["glyph_bounds"].update(unmapped_font_bounds(program.getGlyphSet(),props["glyph_names"],program.font.get("FontMatrix",[.001,0,0,.001,0,0])))
                    props["fallback_cids"].update({code: text for code, glyph in enumerate(program.font.get("Encoding", []))
                                                   if (text := toUnicode(glyph))})
                except Exception:
                    pass
            if stream is not None:
                try:
                    from fontTools.ttLib import TTFont
                    from fontTools.cffLib import CFFFontSet
                    data = stream.get_data()
                    if data[:4] in (b"OTTO", b"\x00\x01\x00\x00", b"true"):
                        font = TTFont(BytesIO(data))
                        from fontTools.agl import toUnicode
                        props["pua_glyphs"] = {chr(code): text for code, glyph in (getattr(font, "getBestCmap", lambda: {})() or {}).items()
                                               if 0xE000 <= code <= 0xF8FF and (text := toUnicode(glyph))}
                        if "OS/2" in font:
                            props["bold"] |= font["OS/2"].usWeightClass >= 600
                            props["italic"] |= bool(font["OS/2"].fsSelection & (1 | (1 << 9)))
                        if "post" in font:
                            props["italic"] |= bool(font["post"].italicAngle)
                    else:
                        cff = CFFFontSet()
                        cff.decompile(BytesIO(data), None)
                        top = cff[cff.fontNames[0]]
                        props["glyph_bounds"].update(unmapped_font_bounds(top.CharStrings,props["glyph_names"],top.FontMatrix))
                        props["bold"] |= bool(re.search(r"bold|black|heavy|demi", getattr(top, "Weight", ""), re.I))
                        props["italic"] |= bool(getattr(top, "ItalicAngle", 0))
                        if not spec.get("DescendantFonts"):
                            from fontTools.agl import toUnicode
                            props["fallback_cids"].update({code: text for code, glyph in cff_encoding_names(top, data).items()
                                                           if (text := toUnicode(glyph))})
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


def unmapped_font_bounds(glyphs,names,matrix):
    """Actual glyph outlines avoid substituting a font-wide ascent for ink.

    https://fonttools.readthedocs.io/en/latest/pens/boundsPen.html
    """
    from fontTools.agl import toUnicode
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.misc.transform import Transform
    result={}
    for code,name in names.items():
        if name not in glyphs or toUnicode(name):
            continue
        pen=BoundsPen(glyphs)
        try:
            glyphs[name].draw(pen)
        except Exception:
            continue  # unsupported/damaged outlines keep their original warning
        if pen.bounds:
            x0,y0,x1,y1=pen.bounds
            pts=[Transform(*matrix).transformPoint(p) for p in [(x0,y0),(x0,y1),(x1,y0),(x1,y1)]]
            result[code]=(min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts))
    return result


def repair_case_cids(font, replacements):
    """With character codes available, case-only Encoding/ToUnicode conflicts are exact."""
    cmap = getattr(font, "unicode_map", None)
    if cmap is not None:
        cmap.cid2unichr.update(replacements)


def cff_encoding_names(top, data):
    """CFF section 12: character codes include zero; GIDs start at one.

    fontTools treats code zero as an unencoded placeholder in format 0. PDF
    renderers (including FreeType) honor an explicitly encoded zero as well.
    """
    encoding = getattr(top, "Encoding", [])
    names = {k: v for k, v in enumerate(encoding) if v != ".notdef"} if isinstance(encoding, list) else {}
    offset = top.rawDict.get("Encoding", 0)
    if offset > 1 and data[offset] & 0x7f == 0:
        count = data[offset + 1]
        for gid, code in enumerate(data[offset + 2:offset + 2 + count], 1):
            if gid < len(top.charset):
                names[code] = top.charset[gid]
    return names


def apply_native_case(page, props):
    if getattr(page, "_segment_case_applied", False) or not any(p.get("case_cids") or p.get("fallback_cids") for p in props.values()):
        return
    try:
        from pdfminer.pdftypes import resolve1
        from pdfminer.psparser import literal_name
        for resource in resolve1(page.page_obj.resources.get("Font", {})).values():
            spec = resolve1(resource)
            evidence = props.get(literal_name(spec["BaseFont"]), {})
            replacements = evidence.get("case_cids", {})
            if replacements or evidence.get("fallback_cids"):
                font = page.pdf.rsrcmgr.get_font(getattr(resource, "objid", None), spec)
                repair_case_cids(font, replacements)
                cmap = getattr(font, "unicode_map", None)
                target = cmap.cid2unichr if cmap is not None else getattr(font, "cid2unicode", {})
                for cid, text in evidence.get("fallback_cids", {}).items():
                    current = target.get(cid, "")
                    if not current or (any(unicodedata.category(c) in ("Cc", "Co") for c in current)
                                       and all(unicodedata.category(c) not in ("Cc", "Co") for c in text)):
                        target[cid] = text
        # Re-decode cached characters using their actual character codes. Equal
        # advances (for example a wide lower-case glyph and its capital) are no
        # longer ambiguous, and the original PDF remains untouched.
        page.flush_cache()
        page._segment_case_applied = True
    except (AttributeError, KeyError, TypeError):
        pass


# Adobe's full Symbol encoding, including its published Unicode alternatives:
# https://www.unicode.org/Public/MAPPINGS/VENDORS/ADOBE/symbol.txt
# Keep the first Unicode alternative for each byte, as ordered in the source.
ADOBE_SYMBOL = {}
for _row in Path(__file__).with_name("adobe_symbol.txt").read_text(encoding="ascii").splitlines():
    if _row and not _row.startswith("#"):
        _unicode, _byte = _row.split()[:2]
        ADOBE_SYMBOL.setdefault(int(_byte, 16), chr(int(_unicode, 16)))


def repair_case_maps(chars, fonts):
    for c in chars:
        if not c.get("size") or not c.get("upright", True):
            continue
        candidates = fonts.get(c.get("fontname"), {}).get("cases", {}).get(c["text"], [])
        advance = (c["x1"] - c["x0"]) / c["size"]
        matches = {glyph for glyph, width in candidates if math.isclose(width, advance, rel_tol=1e-4, abs_tol=1e-6)}
        if len(matches) == 1:
            c["text"] = matches.pop()
        evidence = fonts.get(c.get("fontname"), {})
        missing=re.fullmatch(r"\(cid:(\d+)\)",c["text"])
        if (missing and evidence.get("blank_controls") and int(missing.group(1))<32
                and int(missing.group(1)) not in evidence.get("glyph_names",{})
                and int(missing.group(1)) not in evidence.get("fallback_cids",{})
                and c.get("adv")==0 and c["x0"]==c["x1"]):
            c["text"]=""
            continue
        c["text"] = "".join(evidence.get("pua_glyphs", {}).get(ch, ch) for ch in c["text"])
        # Microsoft symbol cmaps store byte codes at F000 + code. Decode only
        # the known Symbol encoding, never arbitrary private-use characters.
        if re.fullmatch(r"(?:[A-Z]{6}\+)?Symbol(?:MT)?", c.get("fontname", ""), re.I):
            c["text"] = "".join(ADOBE_SYMBOL.get(ord(ch) - 0xF000, ch)
                                if 0xF020 <= ord(ch) <= 0xF0FF else ch for ch in c["text"])


def font_word_tolerances(chars):
    """Separate kerning from word spaces per font (pdfminer's relative margins).

    Only lower the default when a near-touching glyph population is separated
    from a repeated space population by more than three robust deviations.
    Encoded spaces remain explicit boundaries in pdfplumber.
    """
    gaps = defaultdict(list)
    for a, b in zip(chars, chars[1:]):
        if (a.get("fontname") == b.get("fontname") and a.get("text", "").isalpha()
                and b.get("text", "").isalpha() and a.get("size", 0)
                and abs(a["bottom"] - b["bottom"]) <= 0.15 * a["size"]):
            g = (b["x0"] - a["x1"]) / a["size"]
            if -0.15 <= g <= 1:
                gaps[a["fontname"]].append(g)
    ratios = {}
    encoded = {c.get("fontname") for c in chars if c.get("text", "").isspace()}
    for font, vals in gaps.items():
        if font in encoded:
            continue
        vs = sorted(vals)
        candidates = [(b - a, i) for i, (a, b) in enumerate(zip(vs, vs[1:]))
                      if a < 0.15 and b <= 0.3 and i >= 2 and len(vs) - i > 3]
        if not candidates:
            continue
        distance, i = max(candidates)
        low, high = vs[:i+1], vs[i+1:]
        med = statistics.median(low)
        dev = statistics.median(abs(v-med) for v in low) * 1.4826
        if (abs(med) <= 0.001 and distance > 3 * max(dev, 0.001)
                and high[0] > 0.15 * statistics.median((c["x1"]-c["x0"])/c["size"] for c in chars
                    if c.get("fontname")==font and c.get("text", "").isalpha() and c.get("size",0))):
            ratios[font] = min(0.15, (low[-1] + high[0]) / 2)
    return ratios


def deduplicate_text_runs(chars):
    """Remove translated copies of a text layer, not repeated words in prose.

    Extends pdfplumber's dedupe_chars (text + font + position) to a repeated
    displacement supported by several complete lines. An individual repeated
    line, or glyphs at different x positions, cannot establish a duplicate layer.
    https://github.com/jsvine/pdfplumber#extracting-text
    """
    # Faux bold overprints individual glyphs, sometimes only part of a row.
    # As in pdfplumber.dedupe_chars, require matching text/font/size/position.
    # Several distinct letters must support the overprint on this page; normal
    # repeated letters have separate advances, not almost coincident boxes.
    glyphs, duplicates = defaultdict(list), []
    for c in chars:
        key = (c.get("text"), c.get("fontname"), round(c.get("size", 0), 2))
        step = .01*max(key[2],.1)
        band = math.floor(c["top"]/step)
        width = abs(c["x1"] - c["x0"])
        tolerance = min(.05 * c.get("size", 0), .25 * width)
        match = next((o for row in (band-1,band,band+1) for o in glyphs[key+(row,)]
                      if abs(o["top"]-c["top"]) <= .01*c.get("size",0)
                      and abs(o["x0"]-c["x0"]) <= tolerance), None)
        if match is not None and tolerance > 0:
            duplicates.append(c)
        else:
            glyphs[key+(band,)].append(c)
    if len({c["text"] for c in duplicates if c["text"].isalpha()}) >= 3:
        removed = {id(c) for c in duplicates}
        chars = [c for c in chars if id(c) not in removed]
    rows = defaultdict(list)
    for c in chars:
        if c.get("upright", True):
            rows[(c.get("fontname"), round(c.get("size", 0), 2), round(c["top"], 2))].append(c)
    signatures = defaultdict(list)
    for (font, size, top), row in rows.items():
        row = sorted(row, key=lambda c: c["x0"])
        text = "".join(c["text"] for c in row)
        if sum(c.isalpha() for c in text) < 2:
            continue
        signature = (font, size, text)
        signatures[signature].append((top, row))
    shifts = defaultdict(list)
    for signature, copies in signatures.items():
        for (a, aa), (b, bb) in zip(sorted(copies), sorted(copies)[1:]):
            if (0 < b-a <= 2*signature[1] and len(aa)==len(bb)
                    and all(abs(x["x0"]-y["x0"]) <= 1 for x,y in zip(aa,bb))):
                shifts[round(b-a, 1)].append((aa, bb, signature[2]))
    removed = set()
    for pairs in shifts.values():
        # Repeated formula components, chart ticks and isolated labels are not
        # a duplicate prose layer. Establish the translation on full word runs.
        if len({text for aa,bb,text in pairs if len(re.findall(r"[^\W\d_]{3,}",text)) >= 2}) >= 3:
            for aa, bb, text in pairs:
                removed.update(id(c) for c in aa)
    return [c for c in chars if id(c) not in removed]


def get_words(page):
    props = font_properties(page)
    apply_native_case(page, props)
    # Font-map repairs flush pdfplumber's character cache. Deduplicate the
    # re-decoded layer, otherwise the flush silently restores every overprint.
    overprinted = False
    if hasattr(page, "objects") and getattr(page, "chars", None):
        before = page.chars
        page.objects["char"] = deduplicate_text_runs(before)
        overprinted = len(page.chars)<len(before)
    repair_case_maps(getattr(page, "chars", []), props)
    level_glyph_boxes(page)
    chars = getattr(page, "chars", [])
    flow = source_spaces_overlap(chars) and not overprinted
    try:  # 按字号比例判断词间距；没有编码空格的 PDF（常见于 TeX）也能正确分词
        ws = page.extract_words(x_tolerance_ratio=0.15, keep_blank_chars=False,
                                use_text_flow=flow, expand_ligatures=False, extra_attrs=["size", "fontname"])
    except TypeError:  # 旧版 pdfplumber
        ws = page.extract_words(x_tolerance=1.5, keep_blank_chars=False,
                                use_text_flow=flow, expand_ligatures=False, extra_attrs=["size", "fontname"])
    ratios = font_word_tolerances(chars) if not flow else {}
    if any(r < 0.15 for r in ratios.values()):
        from pdfplumber.utils.text import WordExtractor

        class FontWordExtractor(WordExtractor):
            def char_begins_new_word(self, prev_char, curr_char, direction, x_tolerance, y_tolerance):
                # The ratio holds within the font it was learned from. Dashes
                # carry their own side bearings and are set closed, so a gap
                # beside one keeps pdfplumber's default tolerance.
                ratio = ratios.get(prev_char.get("fontname"))
                if (ratio is not None and direction in ("ltr", "rtl")
                        and prev_char.get("fontname") == curr_char.get("fontname")
                        and not {prev_char.get("text"), curr_char.get("text")} & set("-‐‑‒–—―")):
                    x_tolerance = ratio * prev_char["size"]
                return super().char_begins_new_word(prev_char,curr_char,direction,x_tolerance,y_tolerance)

        # Keep consecutive source font runs intact. Regrouping the entire page
        # by font would join text across intervening symbols and superscripts.
        try:
            ws = FontWordExtractor(x_tolerance_ratio=0.15,keep_blank_chars=False,
                                   use_text_flow=flow,expand_ligatures=False,extra_attrs=["size","fontname"]).extract_words(chars)
        except TypeError:
            pass  # older pdfplumber: retain the extraction obtained above
    out, unmapped, marks, sources = [], [], [], []
    # pdfplumber reports coordinates in a frame whose origin is page.bbox, not the page corner; a MediaBox
    # that does not start at (0, 0) (JSTOR scans) would otherwise shift margins, crops and every bbox.
    ox, oy = float(page.bbox[0]), float(page.bbox[1])
    baselines={(c.get("fontname"),round(c["x0"],4),round(c["top"],4),round(c.get("size",0),3)):
               float(page.bbox[3])-float(c["matrix"][5])-oy
               for c in chars if c.get("matrix") and c.get("upright",True)}
    ligature_starts={(c.get("fontname"),round(c["x0"],4),round(c["top"],4)) for c in chars
                     if c.get("text") in LIGATURES or c.get("text") in LIGATURES.values()}
    space_before={(c.get("fontname"),round(c["x0"],4),round(c["top"],4)) for i,c in enumerate(chars)
                  if i and chars[i-1].get("text","").isspace()
                  and abs(chars[i-1]["bottom"]-c["bottom"])<=.15*c["size"]
                  and (flow or abs(chars[i-1]["x1"]-c["x0"])<=.15*c["size"])}
    space_after={(c.get("fontname"),round(c["x1"],4),round(c["bottom"],4)) for i,c in enumerate(chars[:-1])
                 if chars[i+1].get("text","").isspace()
                 and abs(chars[i+1]["bottom"]-c["bottom"])<=.15*c["size"]
                 and (flow or abs(chars[i+1]["x0"]-c["x1"])<=.15*c["size"])}
    # An explicit space can span both word edges when font advances overlap.
    # Its two source neighbours establish a boundary even at zero geometric
    # gap. Requiring both edges and the baseline avoids unrelated spaces from
    # interleaved text runs; a font/run split has no intervening space glyph.
    for left,space,right in zip(chars,chars[1:],chars[2:]):
        if (space.get("text","").isspace()
                and abs(left["bottom"]-space["bottom"])<=.15*left["size"]
                and abs(left["bottom"]-right["bottom"])<=.15*left["size"]
                and space["x0"]<=left["x1"]<=space["x1"]
                and space["x0"]<=right["x0"]<=space["x1"]):
            space_after.add((left.get("fontname"),round(left["x1"],4),round(left["bottom"],4)))
            space_before.add((right.get("fontname"),round(right["x0"],4),round(right["top"],4)))
    for w in ws:
        if not w.get("upright", True):
            continue  # 侧边竖排水印等
        t = compose_accents(clean_text(w["text"]))
        if "(cid:" in t:
            unmapped.append((float(w["x0"]) - ox, float(w["x1"]) - ox,
                             float(w["top"]) - oy, float(w["bottom"]) - oy))
            marks.append((re.findall(r"\(cid:(\d+)\)", t), unmapped[-1], t))
            sources.append(dict(codes=[f"⟦cid:{cid}⟧" for cid in marks[-1][0]],
                                bbox=[round(unmapped[-1][0]/page.width,8),round(unmapped[-1][2]/page.height,8),
                                      round(unmapped[-1][1]/page.width,8),round(unmapped[-1][3]/page.height,8)],
                                raw=re.sub(r"\(cid:(\d+)\)",r"⟦cid:\1⟧",t),font=w["fontname"],
                                glyph_names=[props.get(w["fontname"],{}).get("glyph_names",{}).get(int(cid),"") for cid in marks[-1][0]]))
            ink=[]
            outlined=0
            for c in chars:
                match=re.fullmatch(r"\(cid:(\d+)\)",c.get("text",""))
                bounds=props.get(w["fontname"],{}).get("glyph_bounds",{}).get(int(match.group(1))) if match else None
                if (bounds and c.get("matrix") and c.get("fontname")==w["fontname"]
                        and w["x0"]<=c["x0"]<=c["x1"]<=w["x1"] and w["top"]<=c["top"]<=c["bottom"]<=w["bottom"]):
                    a,b,d,e,x,y=c["matrix"]
                    for gx,gy in [(bounds[0],bounds[1]),(bounds[0],bounds[3]),(bounds[2],bounds[1]),(bounds[2],bounds[3])]:
                        ink.append((a*gx+d*gy+x,b*gx+e*gy+y))
                    outlined+=1
            if ink and outlined==len(marks[-1][0]):
                sources[-1]["ink_bbox"]=[(min(x for x,y in ink)-ox)/page.width,
                    (float(page.bbox[3])-max(y for x,y in ink)-oy)/page.height,
                    (max(x for x,y in ink)-ox)/page.width,
                    (float(page.bbox[3])-min(y for x,y in ink)-oy)/page.height]
            # A named Symbol font is an encoding clue, but a CID is a glyph
            # index, not an Adobe Symbol byte. Without a cmap/glyph name it
            # cannot safely be guessed. Keep a visible placeholder as well as
            # the provenance, including when it occurs in a prose definition.
            if not re.fullmatch(r"(?:[A-Z]{6}\+)?Symbol(?:MT)?",w["fontname"],re.I):
                continue  # preserve the raw token, code and geometry as item metadata
        t = re.sub(r"\(cid:(\d+)\)", r"⟦cid:\1⟧", t)
        if not t:
            continue
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
            # Keep the glyph identity until line construction. pdfplumber's
            # extra_attrs deliberately splits font runs, including fallback
            # ligature fonts: https://github.com/jsvine/pdfplumber#extracting-text
            "ligature": any(c in LIGATURES for c in w["text"]) or (w["fontname"],round(float(w["x0"]),4),round(float(w["top"]),4)) in ligature_starts,
            "baseline": baselines.get((w["fontname"],round(float(w["x0"]),4),round(float(w["top"]),4),round(float(w["size"]),3)),float(w["bottom"])-oy),
            "space_before": (w["fontname"],round(float(w["x0"]),4),round(float(w["top"]),4)) in space_before,
            "space_after": (w["fontname"],round(float(w["x1"]),4),round(float(w["bottom"]),4)) in space_after,
            "symbolic": props.get(w["fontname"], {}).get("symbolic", False),
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
            w["unmapped_marks"] = marks
            w["unmapped_sources"] = sources
    if gaps:
        word_gap = statistics.median(gaps)
        for w in out:
            w["word_gap"] = word_gap
    learn_tracking_boundaries(out)
    return out


def learn_tracking_boundaries(words):
    """Borrow word/group-gap evidence from other labels in the same font.

    Isolated tracked words have no internal word gap; a separate multiword label
    in that font can supply it. Separate populations by robust three-sigma gaps.
    """
    samples = defaultdict(list)
    for a, b in zip(words, words[1:]):
        if (len(a["text"]) == len(b["text"]) == 1 and a["text"].isalpha() and b["text"].isalpha()
                and a["font"] == b["font"] and a["size"] == b["size"]
                and abs(a["bottom"] - b["bottom"]) <= 1e-6 * a["size"] and b["x0"] > a["x1"]):
            samples[(a["font"], a["size"])].append(b["x0"] - a["x1"])
    boundaries = {}
    for key, values in samples.items():
        values = sorted(values)
        if len(values) < 3:
            continue
        cut = max(range(2, len(values)), key=lambda i: values[i] - values[i - 1])
        low = values[:cut]
        centre = statistics.median(low)
        spread = 1.4826 * statistics.median(abs(x - centre) for x in low)
        # Repeated exact advances can make MAD zero. IQR retains between-label
        # variation; one PDF font-width unit covers quantization of advances.
        spread = max(spread, (low[3 * len(low) // 4] - low[len(low) // 4]) / 1.349)
        if values[cut] > centre + 3 * spread + 1e-6 * key[1] and spread < centre:
            boundaries[key] = (values[cut], centre + 3 * spread + key[1] / 1000)
    for w in words:
        evidence = boundaries.get((w["font"], w["size"]))
        if evidence:
            w["tracking_boundary"], w["tracking_upper"] = evidence


def source_spaces_overlap(chars):
    """OCR proxy-font advances can place a space after the next word's start.

    In that case preserve explicit spaces in content-stream order while building
    words (pdfplumber's text-flow mode); reading order still uses word geometry.
    """
    return any(b["text"].isspace() and a["x0"] < c["x0"] < b["x0"] - 1e-6 * a["size"]
               and abs(a["bottom"] - c["bottom"]) <= 0.15 * a["size"]
                 and abs(a["bottom"] - b["bottom"]) <= 0.15 * a["size"]
               for a, b, c in zip(chars, chars[1:], chars[2:]))


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
        boundaries.extend(w["tracking_boundary"] for w in run if w.get("tracking_boundary"))
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
        upper = max([centre + 3 * spread + epsilon] + [w["tracking_upper"] for w in run if w.get("tracking_upper")])
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
                            top=min(w["top"] for w in group), bottom=max(w["bottom"] for w in group),
                            tracking_sources=group))
        i = j
    return out


def line_from_words(ws):
    ws = join_tracked_words(sorted(ws, key=lambda w: w["x0"]))
    text, prev, superscripts = "", None, []
    for w in ws:
        previous_letters = prev["text"].lstrip("([\"'“‘").replace("’", "").replace("'", "") if prev else ""
        following_letters = w["text"].rstrip(".,;:!?)]\"'”’").replace("’", "").replace("'", "")
        if (prev is not None and w["text"].isdigit() and w["size"] < prev["size"]
                and w["bottom"] < prev["bottom"]
                and (len(re.findall(r"[A-Za-z]", prev["text"])) >= 3 or prev["text"][-1:] in ".,;:!?)]")):
            superscripts.append((prev["text"], w["text"]))
            text = join_words(text, w["text"])
        elif (prev is not None and w["x0"] - prev["x1"] < 0.1 * max(w["size"], prev["size"])
                and w.get("font")==prev.get("font") and w["size"]==prev["size"]
                and (following_letters.isalpha() and previous_letters.isalpha()
                     and (max(len(following_letters),len(previous_letters))>1 or not w.get("italic") and not prev.get("italic"))
                     or following_letters.isdigit() and previous_letters.isdigit())
                and not prev.get("space_after") and not w.get("space_before")
                and abs(w.get("baseline",w["bottom"])-prev.get("baseline",prev["bottom"]))<=.12*w["size"]):
            text += w["text"]  # touching source runs are one word, not a space
        elif (prev is not None and w["x0"] - prev["x1"] < 0.1 * max(w["size"], prev["size"])
                and (w["size"] != prev["size"] or w.get("font") != prev.get("font"))
                and (prev["text"][-1:] in ")]" or w["text"][:1] in "([" or (
                    (prev.get("ligature") or w.get("ligature"))
                    and not prev.get("space_after") and not w.get("space_before")
                    and prev["text"][-1:].isalpha() and w["text"][:1].isalpha()
                    and abs(w.get("baseline",w["bottom"])-prev.get("baseline",prev["bottom"])) <= .12*max(w["size"],prev["size"])) or (
                    prev["text"].isalpha() and w["text"].isalpha() and w["size"] != prev["size"]
                    and not w["text"].isdigit() and not prev["text"].isdigit()
                    and abs(w["bottom"] - prev["bottom"]) <= 0.12 * max(w["size"], prev["size"])))):
            # words are split where the font or size changes; when they touch there was no space between them:
            # a word with its brackets set in a math font, or a small-caps "R" + "EFERENCES" on one baseline
            text += w["text"]
        else:
            text = join_words(text, w["text"])
        prev = w
    weights = [(w["size"], len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"]))) for w in ws]
    total = sum(n for _, n in weights) or 1
    acc, size = 0, weights[0][0]
    for s, n in sorted(weights):
        acc += n
        if acc >= total / 2:
            size = s
            break
    # Indices can outnumber the baseline letters in a mathematical explanation.
    # Its ordinary words, when present, establish the reading-text size.
    prose = [w for w in ws if re.fullmatch(r"[A-Za-z]{3,}[.,;:]?",w["text"])
             and not w.get("symbolic") and not re.search(r"math|symbol",w.get("font",""),re.I)]
    if len(prose) >= 2:
        prose_size = statistics.median(w["size"] for w in prose)
        if size < prose_size-.5:
            size = prose_size
    bold = sum(len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"])) for w in ws if w.get("bold")) / total
    italic = sum(len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"])) for w in ws if w.get("italic")) / total
    mono = sum(len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"])) for w in ws if w.get("mono")) / total
    return {"text": text, "x0": ws[0]["x0"], "x1": max(w["x1"] for w in ws),
            "top": min(w["top"] for w in ws), "bottom": max(w["bottom"] for w in ws),
            "size": size, "bold": bold, "italic": italic, "mono": mono, "words": ws, "superscripts": superscripts, "font": ws[0].get("font", ""),
            "graphic": any(w.get("graphic") for w in ws), "tab": any(w.get("tab") for w in ws),
            "ocr_layer": any(w.get("ocr_layer") for w in ws),
            "graphic_label": any(w.get("graphic_label") for w in ws),
            "caption_group": ws[0].get("caption_group") if all(w.get("caption_group") == ws[0].get("caption_group") for w in ws) else None,
            "caption_measure": ws[0].get("caption_measure"),
            "caption_indent": ws[0].get("caption_indent"),
            "caption_center": ws[0].get("caption_center"),
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
            peers = [v for v in c["words"] if .8*w["size"] <= v["size"] <= 1.25*w["size"]
                     and "baseline" in v and "baseline" in w]
            if (peers and any(v["size"] > 2*w["size"] and not v.get("symbolic")
                             and v["text"].isalpha() and len(v["text"])>=2 for v in c["words"])
                    and abs(w["baseline"]-statistics.median(v["baseline"] for v in peers)) > .5*w["size"]):
                continue  # a tall logo must not bridge two distinct text baselines
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
        baselines = defaultdict(list)
        for w in row:
            baselines[(round(w["top"],1),round(w["bottom"],1))].append(w)
        printed = [ws for ws in baselines.values() if len(ws)>=3 and sum(len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"])) for w in ws)>=20]
        overlap = any(sum(min(a["x1"],b["x1"])-max(a["x0"],b["x0"])>0
                          for a in aa for b in bb)>=3 for j,aa in enumerate(printed) for bb in printed[j+1:])
        if (overlap and len(printed)==len(baselines) and len({w.get("font") for w in row})==1
                and max(w["top"] for w in row)-min(w["top"] for w in row)<=0.15*max(w["size"] for w in row)):
            for ws in sorted(printed,key=lambda ws:min(w["top"] for w in ws)):
                out.append(dict(line_from_words(ws), overprinted=True))
            continue
        groups = [[row[0]]]
        for w in row[1:]:
            prev = groups[-1][-1]
            gap = w["x0"] - prev["x1"]
            if (gap_split and gap > max(0.9 * max(prev["size"], w["size"]), 7.0)
                    or w.get("caption_group") != prev.get("caption_group")):
                groups.append([w])
            else:
                groups[-1].append(w)
        out += [line_from_words(g) for g in groups]
    return sorted(out, key=lambda l: (l["top"], l["x0"]))


def body_size(words):
    cnt = Counter()
    for w in words:
        cnt[round(w["size"] * 2) / 2] += len(re.sub(r"\u27e6cid:\d+\u27e7", "_", w["text"]))
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
        # A text container has its own column flow, even if it spans only some
        # page columns. Extract it as a unit, without slabbing the whole page.
        container = (any(bx[0] + 10 < g < bx[2] - 10 for g in gutters)
                     and any(s.get("text_box") == tuple(bx[:4]) for s in segs))
        crossed = sum(bx[0] + 10 < g < bx[2] - 10 for g in gutters)
        if 0 < crossed < len(gutters) and text_container(bx, segs, body, column_flow=True):
            container = True
            for ln in segs:
                if bx[0]-2 <= ln["x0"] and ln["x1"] <= bx[2]+2 and bx[1]-2 <= ln["top"] and ln["bottom"] <= bx[3]+2:
                    ln["text_box"] = tuple(bx[:4])
                    ln["graphic"], ln["tab"] = False, False
        if (not container and not all(bx[0] + 10 < g < bx[2] - 10 for g in gutters)
                or (bx[2] - bx[0]) * (bx[3] - bx[1]) > 0.6 * pw * ph):
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
            if any(any(bx[0]+10 < g < bx[2]-10 for g in gutters)
                   and bx[0]-2 <= ln["x0"] and ln["x1"] <= bx[2]+2
                   and bx[1]-2 <= ln["top"] and ln["bottom"] <= bx[3]+2 for bx in boxes):
                ln["aside"] = True
        out += lines
    return out


def headingish(ln, body):
    ln = dict(ln, size=round(ln["size"]*2)/2)  # same half-point classes as body_size
    if ln.get("page_top_continuation") or ln.get("runin_para") or ln.get("graphic") or ln.get("tab"):
        return False
    if ln.get("force_heading"):
        return True
    body = max(body,ln.get("local_body") or body)
    t = ln["text"]
    asks = t.endswith("?") and (ln["size"] >= body + 1.0 or ln["bold"] >= 0.85)  # the last line of a heading that asks a question
    if len(t) > 100 or (end_terminal(t) and not asks):
        return False
    return bool(ln.get("force_heading") or ln["size"] >= body + 1.0 or ln["bold"] >= 0.85
                or (ln["size"] >= body - 0.5 and word_count(t) <= 20 and NUM_HEAD_RE.match(t) and is_heading_block(dict(ln, n_lines=1), body)))


LIST_MARK_RE = re.compile(r"^(?:[•●◦▪■‣∙*–—-]|\(?\d+[.)]|\(?[a-z][.)])\s+", re.I)
TOC_RE = re.compile(r"\.{3,}|(?:…\s*){2,}")


def toc_entry(text):
    # A leader connects a title to a standalone folio. Ellipses within a
    # sentence, including words ending in Roman-numeral letters, are prose.
    folio = re.search(r"(?<!\w)(?:\d+|[ivxlcdm]+)\s*$", text, re.I)
    if not folio:
        return False
    prefix = text[:folio.start()].rstrip()
    # Separate the suffix tests: a single nested leader/whitespace expression
    # backtracks exponentially on long mathematical ellipsis rows.
    leader = re.search(r"\.{3,}$|…(?:\s*…)+$", prefix)
    return bool(leader and prefix[:leader.start()].strip())
READING_RE = re.compile(r"^(?:further|suggested|recommended) reading$", re.I)
CHAPTER_RE = re.compile(r"^(?:ch\.?|chapter)\s+(?:\d+|[IVXLC]+)$", re.I)


def emphasized(w):
    return w.get("bold") or w.get("italic") or bool(re.search(r"italic|oblique", w.get("font", ""), re.I))


def caption_cells(line):
    """A caption continuation is a text run, not a row of separated cells."""
    if any(line.get("cell_edges", [])):
        return True
    ws = line.get("words", [])
    return any(b["x0"] - a["x1"] > max(0.9 * max(a["size"], b["size"]), 7.0)
               for a, b in zip(ws, ws[1:]))


def caption_wrap(previous, following, left=None, measure=None):
    """A wrap fills the preceding measure and returns to its text left edge."""
    if any(following.get(k) for k in ("table", "tab", "graphic", "display_region")) or caption_cells(following):
        return False
    left = previous.get("caption_indent") or left or previous.get("first_x0", previous["x0"])
    measure = measure or previous.get("caption_measure") or previous.get("column_x1") or previous["x1"]
    size = max(previous["size"], following["size"])
    ws = following.get("words", [])
    gaps = [b["x0"]-a["x1"] for a,b in zip(ws,ws[1:]) if b["x0"]>=a["x1"]]
    space = statistics.median(gaps) if gaps else .25*size
    next_width = ws[0]["x1"]-ws[0]["x0"]+space if ws else 0
    def fonts(line):
        return set(line.get("fonts", [])) or {w.get("font") for w in line.get("words", [])} or {line.get("font"),line.get("end_font")}
    center=previous.get("caption_center")
    if center is None:
        center=(previous["x0"]+previous["x1"])/2
    # pdfminer groups neighbouring aligned lines with line_margin relative to
    # line height (default .5). Centred titles need no filled right measure.
    # https://pdfminersix.readthedocs.io/en/latest/topic/converting_pdf_to_text.html
    normal_gap = 0 <= following["top"]-previous["bottom"] <= .5*size
    centered = (abs((following["x0"]+following["x1"])/2-center) <= max(1,.5*size) and normal_gap
                and (previous.get("caption_center") is not None
                     or abs(following["x0"]-previous["x0"])>max(1,.15*size)))
    aligned = abs(following.get("first_x0", following["x0"]) - left) <= max(1, 0.15 * size)
    hanging_title = previous.get("caption_indent") is not None and aligned and normal_gap
    return ((centered or hanging_title or aligned
             and previous.get("last_x1", previous["x1"]) >= measure - max(2.5 * size,next_width))
            and bool(fonts(previous) & fonts(following))
            and abs(previous["size"] - following["size"]) <= 0.5)


def caption_word_sources(words):
    """Include original glyph words when tracking created a temporary word."""
    for word in words:
        yield word
        yield from caption_word_sources(word.get("tracking_sources", []))


def prepare_typing_lines(lines, body):
    """Use layout tokens before paragraph assembly (style spans and hanging indents)."""
    out = []
    for line in lines:
        words = line.get("words", [])
        if (len(words)>1 and words[0]["text"].strip(".:").casefold()=="abstract"
                and (emphasized(words[0]) or words[0]["text"].endswith(":"))):
            head = dict(line, **line_from_words(words[:1]), force_heading=True)
            tail = dict(line, **line_from_words(words[1:]), runin_body=True)
            out.extend((head,tail))
            continue
        cut = 0
        while cut < len(words) and emphasized(words[cut]):
            cut += 1
        if 0 < cut < len(words):
            prefix = line_from_words(words[:cut])
            if prefix["text"].endswith(":") and not CAPTION_RE.match(prefix["text"]):
                out.append(dict(line, runin_para=True, colon_label_font=prefix.get("font")))
                continue
            previous = next((x for x in reversed(out) if x["band"] == line["band"] and x["col"] == line["col"]), None)
            if (previous and word_count(prefix["text"])==1 and prefix["text"].endswith(".")
                    and previous.get("bold",0)>=.85 and prefix.get("bold",0)>=.85 and prefix.get("italic",0)>=.85
                    and not previous.get("force_heading")
                    and word_count(previous["text"])>=6 and not end_terminal(previous["text"])
                    and abs(previous["size"]-line["size"])<=.5
                    and abs(previous["x0"]-line["x0"])<=max(1,.15*body)
                    and 0<=line["top"]-previous["bottom"]<=.5*line["size"]):
                out.append(line)  # a styled last word still finishes the preceding sentence
                continue
            continued_head = (previous and NUM_HEAD_RE.match(previous["text"]) and is_heading_block(dict(previous, n_lines=1), body)
                              and previous.get("font") == prefix.get("font")
                              and 0 <= line["top"] - previous["bottom"] <= line["size"])
            # A styled lead phrase, rather than an initial, abbreviation or number.
            if ((line["size"] >= body - max(1, 0.15 * body) or line.get("text_box")) and (prefix["text"].endswith(".") or continued_head) and len(re.findall(r"[A-Za-z]{3,}", prefix["text"])) >= 1
                    and not CAPTION_RE.match(prefix["text"])):
                previous = next((x for x in reversed(out) if x["band"] == line["band"] and x["col"] == line["col"]), None)
                if (not continued_head and previous and previous.get("words") and all(emphasized(w) for w in previous["words"])
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
        line["toc"] = False  # established from neighbouring leader entries below
        ws = line.get("words", [])
        line["cell_edges"] = [b["x0"] for a, b in zip(ws, ws[1:])
                              if b["x0"] - a["x1"] >= max(a["size"], b["size"])]
    for ls in streams.values():
        entries = [l for l in ls if toc_entry(l["text"])]
        for i, line in enumerate(ls):
            if line in entries and sum(toc_entry(x["text"]) for x in ls[max(0,i-2):i+3]) >= 3:
                line["toc"] = True
        # A glossary pairs abbreviation cells with definitions at repeated tab
        # stops. Ordinary justified prose does not establish such a table.
        for i in range(len(ls) - 2):
            run = ls[i:i + 3]
            if any(l.get("list_start") or LIST_MARK_RE.match(l["text"]) or l.get("caption_group") for l in run):
                continue
            if not all(len(l.get("cell_edges", [])) == 1 and l.get("words")
                       and l["words"][0]["text"].isalnum()
                       and (sum(c.isupper() for c in l["words"][0]["text"]) >= 2
                            or any(c.isalpha() for c in l["words"][0]["text"])
                            and all(not c.isalpha() or c.isupper() for c in l["words"][0]["text"]))
                       and l["words"][1]["x0"] == l["cell_edges"][0]
                       and len(l["words"]) >= 2 for l in run):
                continue
            if any(l["text"].rstrip().endswith((",", ";")) or last_word(l["text"]) in STOP_END for l in run):
                for l in run:
                    l["cell_sentence"] = True
                continue  # a sentence's aligned variable definitions are still prose
            edges = run[0].get("cell_edges", [])
            if any(all(any(abs(e - candidate) <= 0.3 * body for e in l.get("cell_edges", []))
                           for l in run[1:]) for candidate in edges):
                for l in run:
                    l["tab"] = True
        stream_gaps = [b["top"]-a["bottom"] for a,b in zip(ls,ls[1:])
                       if 0<=b["top"]-a["bottom"]<=1.5*body]
        normal_gap = statistics.median(stream_gaps) if stream_gaps else 0.25*body
        for i, line in enumerate(ls):
            if not line.get("colon_label_font"):
                continue
            tail = line
            for previous in reversed(ls[:i]):
                if (NUM_HEAD_RE.match(previous["text"]) or end_terminal(previous["text"])
                        or previous.get("font") != line["colon_label_font"]
                        or not previous.get("words") or not all(emphasized(w) for w in previous["words"])
                        or abs(previous["size"] - line["size"]) > 0.5
                        or tail["top"] - previous["bottom"] > normal_gap + max(0.45 * body, 2.5)):
                    break
                previous["runin_para"] = True
                tail = previous
        for i, line in enumerate(ls):
            previous = ls[i - 1] if i else None
            following = ls[i + 1] if i + 1 < len(ls) else None
            paragraph_gap = normal_gap + max(0.45 * body, 2.5)
            same_display_style = (following and line.get("body_font") is False
                                  and line.get("font") == following.get("font")
                                  and abs(line["size"]-following["size"]) <= 0.5)
            line["heading_boundary"] = ((previous is None or end_terminal(previous["text"])
                                         or NUM_HEAD_RE.match(line["text"]) and headingish(previous, body)
                                         or line["top"] - previous["bottom"] > paragraph_gap)
                                        and not (following and starts_lower(following["text"]) and not same_display_style))
            peers = [l["size"] for l in (previous,following) if l and l.get("font")==line.get("font")
                     and line.get("bold",0)<0.5 and line.get("italic",0)<0.5
                     and l.get("bold",0)<0.5 and l.get("italic",0)<0.5
                     and word_count(l["text"])>=6 and abs(l["size"]-body)<=max(1,0.15*body)]
            if peers and line.get("ocr_layer"):
                line["local_body"]=statistics.median(peers)
            # An isolated small-type subhead has paragraph gaps on both sides,
            # rather than merely being an OCR word assigned a large glyph box.
            if (previous and following and 1<=word_count(line["text"])<=8 and not end_terminal(line["text"])
                    and line["text"][:1].isupper() and not re.match(r"\d",line["text"])
                    and not line.get("tab") and not line.get("graphic")
                    and line["top"]-previous["bottom"]>body and following["top"]-line["bottom"]>body
                    and line["heading_boundary"]
                    and word_count(following["text"])>=6 and not starts_lower(following["text"])
                    and re.search(r"[A-Za-z]{3,}",line["text"])
                    and not display_variable_style([line]) and not symbolic_display(line["text"])
                    and not display_variable_style([following]) and not symbolic_display(following["text"])):
                line["force_heading"]=True
            candidate = bool(CAPTION_RE.match(line["text"]) or CAPTION_TITLE_RE.match(line["text"]))
            wrapped = bool(previous and not end_terminal(previous["text"])
                           and not headingish(previous, body)
                           and previous.get("font") == line.get("font")
                           and abs(previous["size"] - line["size"]) <= 0.15 * body
                           and 0 <= line["top"] - previous["bottom"] <= normal_gap + max(0.45*body,2.5)
                           and not previous.get("tab") and not previous.get("graphic"))
            line["caption_candidate"] = candidate and not (wrapped and word_count(line["text"]) > 3)
            if (previous and previous.get("caption_candidate") and not candidate
                    and not any(line.get(k) for k in ("tab","graphic","display_region"))
                    and not caption_cells(line)
                    and 0 <= line["top"]-previous["bottom"] <= .5*max(line["size"],previous["size"])):
                # Before prose assembly, preserve a caption's neighbouring text
                # line. OCR proxy-font boxes can drift horizontally even though
                # the printed title is centred: an inset same-style line stays
                # caption text rather than becoming a body paragraph opener.
                inset_ocr = (line.get("ocr_layer") and previous.get("ocr_layer")
                             and previous["x0"]<line["x0"]<line["x1"]<previous["x1"]
                             and previous.get("font")==line.get("font")
                             and abs(previous["size"]-line["size"])<=.15*previous["size"])
                if caption_wrap(previous,line) or inset_ocr:
                    group=previous.get("caption_group") or (previous["x0"],previous["top"])
                    previous["caption_group"]=line["caption_group"]=group
                    line["caption_candidate"]=True
                    line["caption_tail"]=True
                    line.pop("force_heading",None)
            if (not line.get("page_top_continuation") and line["text"].endswith(":") and word_count(line["text"]) <= 8
                    and (not previous or (end_terminal(previous["text"]) and line["top"] - previous["bottom"] > max(0.45 * body, 2.5)))
                    and line["size"] >= body - max(1, 0.15 * body) and not line.get("tab")
                    and following and following["x1"] > line["x1"] + body
                    and not starts_lower(following["text"]) and not following["text"].endswith(":")):
                line["force_heading"] = True
            if (previous and following and NUM_HEAD_RE.match(previous["text"])
                    and previous.get("words") and all(emphasized(w) for w in previous["words"])
                    and not end_terminal(previous["text"])
                    and previous.get("font") == line.get("font")
                    and all(emphasized(w) for w in line.get("words", []))
                    and following.get("words") and not emphasized(following["words"][0])
                    and 0 <= line["top"] - previous["bottom"] <= line["size"]):
                line["force_heading"] = True
            if (line.get("bold", 0) >= 0.85 and line["text"].endswith(".")
                    and following and following.get("words") and not emphasized(following["words"][0])
                    and previous and previous.get("bold", 0) >= 0.85 and not end_terminal(previous["text"])):
                line["force_heading"] = True
            if (line.get("italic", 0) >= 0.85 and 2 <= word_count(line["text"]) <= 12
                    and not re.search(r"\w_\w", line["text"])
                    and not end_terminal(line["text"]) and not display_variable_style([line])
                    and following and following.get("words") and not emphasized(following["words"][0])
                    and following.get("italic", 0) < 0.5 and following.get("bold", 0) < 0.5
                    and (not previous or previous.get("italic", 0) < 0.5)
                    and (not previous or end_terminal(previous["text"]) or previous.get("force_heading")
                         or symbolic_display(previous["text"]) or display_variable_style([previous])
                         or line["top"]-previous["bottom"]>normal_gap+max(0.45*body,2.5))
                    and abs(line["size"] - body) <= max(1, 0.15 * body)):
                line["force_heading"] = True
        for i, line in enumerate(ls):
            if line.get("runin_para"):
                line.pop("force_heading", None)
            if line.get("force_heading") or line.get("toc"):
                continue
            previous = ls[i-1] if i else None
            if (previous and re.match(r"^[A-Za-z]\.\s+\d",line["text"])
                    and previous["text"].count("(")>previous["text"].count(")")
                    and not end_terminal(previous["text"])
                    and 0<=line["top"]-previous["bottom"]<=normal_gap+max(.45*body,2.5)):
                continue  # a wrapped parenthesis/citation is not a new list item
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
        hanging = [(a, b) for a, b in zip(ls, ls[1:]) if not headingish(a, body) and not display_variable_style([a]) and not a.get("cell_edges")
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
    if any(b.get("cell_sentence") for b in blocks):
        return False
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
        prose = [l for l in ls if not l.get("tab") and not l.get("graphic")
                 and (not l.get("caption_candidate") or l.get("caption_tail"))]
        good = [l for l in prose if abs(l["size"] - body) <= max(1.0, 0.15 * body) and len(l["text"]) > 25] or prose or ls
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
            in_caption = cur["lines"][0].get("caption_candidate", bool(CAPTION_RE.match(cur["lines"][0]["text"])))
            in_list = cur["lines"][0].get("list_start")
            title_kicker = (cur["lines"][0]["size"] >= body + 2.5
                            and word_count(cur["lines"][0]["text"]) <= 3
                            and not end_terminal(cur["lines"][0]["text"].rstrip(":")))
            measure = right_edge[key]
            if (len(cur["lines"]) >= 2
                    and min(l["x0"] for l in cur["lines"]) > min(l["x0"] for l in streams[key]) + .8*body
                    and cur["lines"][0]["text"].startswith(('"', "'", "\u201c", "\u2018"))):
                # An explicitly quoted inset has a narrower measure than body
                # text. A filled quote line is not a paragraph-ending short line.
                measure = max(l["x1"] for l in cur["lines"])
            same_heading = (abs(prev["size"] - ln["size"]) <= 0.5
                            and (prev.get("font") == ln.get("font") or title_kicker)
                            and (prev.get("bold", 0) >= 0.85 and ln.get("bold", 0) >= 0.85
                                 or prev.get("italic", 0) >= 0.85 and ln.get("italic", 0) >= 0.85
                                 or ((cur["lines"][0]["size"] > body + 0.5 or cur["lines"][0].get("body_font") is False) and headingish(cur["lines"][0], body)
                                     and not KNOWN_HEAD_RE.fullmatch(NUM_PREFIX_RE.sub("",cur["lines"][0]["text"]).strip().rstrip(":"))))
                            and not NUM_HEAD_RE.match(ln["text"]))
            if (any(bool(ln.get(flag)) != bool(prev.get(flag)) for flag in ("front_meta", "abstract", "contents_page", "graphic", "display_region", "byline", "subtitle", "roman_section", "footnote"))
                    or ln.get("caption_group") != prev.get("caption_group")
                    or (not in_caption and headingish(cur["lines"][0], body)
                        and cur["lines"][0]["size"] <= body + 0.5
                        and prev.get("font") != ln.get("font"))
                    or ln.get("list_start") or ln.get("toc") or prev.get("toc") or (prev.get("force_heading") and not same_heading) or ln.get("runin_body")
                    or (ln.get("force_heading") and not ((headingish(prev, body) or same_heading) and abs(prev["size"] - ln["size"]) <= 0.5
                                                         and ln["top"] - prev["bottom"] <= gap_med + max(0.45 * sz, 2.5)))):
                new = True
            elif in_list and abs(ln["x0"] - cur["lines"][0].get("list_indent", ln["x0"])) <= 0.15 * body and ln["top"] - prev["bottom"] <= gap_med + max(0.45 * sz, 2.5):
                pass
            elif ln["top"] - prev["bottom"] > gap_med + max(0.45 * sz, 2.5):
                new = True
            elif abs(ln["size"] - prev["size"]) > max(0.9, 0.09 * body):
                new = True
            elif ln.get("caption_candidate", bool(CAPTION_RE.match(ln["text"]))):
                new = True
            elif (ln.get("mono", 0) >= 0.5) != (prev.get("mono", 0) >= 0.5):
                new = True
            elif bool(ln.get("tab")) != bool(prev.get("tab")):
                new = True
            elif in_caption:
                same_group = prev.get("caption_group") is not None and prev.get("caption_group") == ln.get("caption_group")
                new = not (same_group or caption_wrap(prev, ln, cur["lines"][0]["x0"],
                                                       cur["lines"][0].get("caption_measure") or cur["column_x1"]))
            elif (not end_terminal(prev["text"]) and abs(prev["size"] - ln["size"]) <= 0.5
                  and re.fullmatch(r"[\d\s.,%]+", ln["text"]) and re.search(r"[A-Za-z]", prev["text"])
                  and abs(prev["x0"] + prev["x1"] - ln["x0"] - ln["x1"]) <= ln["size"]):
                pass  # centered prose wraps around a shared center, not a left margin
            elif body_like and not same_heading and ln["x0"] - le > 0.8 * ln["size"] and prev["x0"] - le < 0.4 * prev["size"]:
                new = True
            elif (not same_heading and prev["x1"] < measure - 2.5 * prev["size"] and end_terminal(prev["text"])
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
    text = re.sub(r"⟦cid:\d+⟧", "", text)
    words = re.findall(r"[A-Za-z]{3,}", re.sub(r"\b(?:ln|log|exp)\b", "", text))
    return not any(not w.isupper() for w in words) and math_dense(text)


def display_variable_style(lines):
    """A display row is predominantly short italic variables, rather than prose.

    Keep the font evidence before extraction loses operators with unmapped glyphs.
    This is used only to group consecutive display rows, outside ruled tables.
    """
    if len(lines) > 2:
        return False
    text = re.sub(r"⟦cid:\d+⟧", "", " ".join(line["text"] for line in lines))
    # Inspect reconstructed words too: tracked italic headings can have one
    # extracted token per glyph. Long uppercase labels need an actual operator.
    if any((not token.isupper() or not EQUATION_RE.search(text)) and not re.search(r"[a-z][A-Z]", token)
           for token in re.findall(r"[A-Za-z]{3,}", text)):
        return False
    words = [w for line in lines for w in line.get("words", []) if w["text"].isalpha()]
    if any(len(w["text"]) > 2 and not w["text"].isupper() and not re.search(r"[a-z][A-Z]", w["text"]) for w in words):
        return False  # prose lead-ins stay visible even when they contain many variables
    variables = [w for w in words if (len(w["text"]) <= 2 or re.search(r"[a-z][A-Z]", w["text"])) and (w.get("italic") or re.search(r"italic|oblique", w.get("font", ""), re.I))]
    return len(variables) >= 3 and len(variables) > len(words) / 2


def trailing_title_marker(lines):
    words = lines[-1].get("words", [])
    if len(words) < 2:
        return ""
    tail = words[-1]
    if tail["text"].isdigit() and any(mark == tail["text"] for _, mark in lines[-1].get("superscripts", [])):
        return tail["text"]
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
    for i, ln in enumerate(lines):
        text = text + ln["text"] if i and lines[i-1].get("ocr_join_next") else join_marked(text, ln["text"])
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
            "italic": sum(l.get("italic",0) * len(l["text"]) for l in lines) / n,
            "mono": sum(l.get("mono", 0) * len(l["text"]) for l in lines) / n,
            "top": min(l["top"] for l in lines), "bottom": max(l["bottom"] for l in lines),
            "x0": min(l["x0"] for l in lines), "x1": max(l["x1"] for l in lines),
            "first_x0": lines[0]["x0"], "last_x1": lines[-1]["x1"],
            "column_x0": b.get("column_x0"), "column_x1": b.get("column_x1"),
            "title_suffix": trailing_title_marker(lines),
            "caption_candidate": lines[0].get("caption_candidate"),
            "local_body": statistics.median(l["local_body"] for l in lines if l.get("local_body")) if any(l.get("local_body") for l in lines) else None,
            "page_top_continuation": lines[0].get("page_top_continuation", False),
            "font": lines[0].get("font", ""),
            "first_word_font": (lines[0].get("words") or [{}])[0].get("font", lines[0].get("font")),
            "end_font": lines[-1].get("words", [{}])[-1].get("font", lines[-1].get("font", "")),
            "heading_boundary": lines[0].get("heading_boundary"),
            "body_font": lines[0].get("body_font"),
            "display_region": any(l.get("display_region") for l in lines),
            "caption_group": lines[0].get("caption_group"),
            "caption_measure": lines[0].get("caption_measure"),
            "caption_indent": lines[0].get("caption_indent"),
            "caption_center": lines[0].get("caption_center"),
            "fonts": sorted({w.get("font", "") for l in lines for w in l.get("words", [])}),
            "runin_para": any(l.get("runin_para") for l in lines),
            "pull": any(l.get("pull") for l in lines),
            "lead_text_x0": lines[0].get("words", [{}, {}])[1].get("x0") if len(lines[0].get("words", [])) > 1 else None,
            "line_texts": [l["text"] for l in lines],
            "gutter_crossings": sum(l.get("gutter_crossing", False) for l in lines),
            "force_heading": any(l.get("force_heading") for l in lines),
            "front_meta": any(l.get("front_meta") for l in lines),
            "abstract": any(l.get("abstract") for l in lines),
            "independent_text": any(l.get("independent_text") for l in lines),
            "article_title": any(l.get("article_title") for l in lines),
            "byline": any(l.get("byline") for l in lines),
            "subtitle": any(l.get("subtitle") for l in lines),
            "roman_section": any(l.get("roman_section") for l in lines),
            "footnote": any(l.get("footnote") for l in lines),
            "inline_math_prose": any(l.get("inline_math_prose") for l in lines),
            "ocr_layer": any(l.get("ocr_layer") for l in lines),
            "contents_page": any(l.get("contents_page") for l in lines),
            "graphic": any(l.get("graphic") for l in lines),
            "overprinted": any(l.get("overprinted") for l in lines),
            "graphic_label": any(l.get("graphic_label") for l in lines),
            "list": bool(lines[0].get("list_start")), "toc": any(l.get("toc") for l in lines),
            "line_gap": b.get("line_gap"),
            "cell_edges": [l.get("cell_edges", []) for l in lines],
            "cell_sentence": any(l.get("cell_sentence") for l in lines),
            "text_box": lines[0].get("text_box"),
            "superscripts": [mark for l in lines for mark in l.get("superscripts", [])],
            "math_style": display_variable_style(lines),
            "unmapped_ink": unmapped_ink(lines, b),
            "unmapped_glyphs": sorted({f"⟦cid:{cid}⟧" for ln in lines for w in ln.get("words", [])
                                      for codes, box, raw in w.get("unmapped_marks", [])
                                      if min(l["top"] for l in lines) - size <= box[3] and max(l["bottom"] for l in lines) + size >= box[2]
                                      and b.get("column_x0", 0) <= (box[0] + box[1]) / 2 <= b.get("column_x1", float("inf"))
                                      for cid in codes}),
            "n_lines": len(lines), "jumps": column_jumps(lines), "aside": any(l.get("aside") for l in lines),
            "tab": all(l.get("tab") for l in lines)}


def margin_key(text):
    return re.sub(r"\s+", "", re.sub(r"\d+", "#", text.casefold()))


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
            # Bibliographical vocabulary also occurs in citations. It only
            # identifies a banner with independent running-head evidence.
            continuation = starts_lower(it["text"]) or (len(it["text"].split()) > 12
                            and re.search(r"[.!?]\s+\w|[,;]", it["text"]))
            banner = (it["top"] < band * p["h"] and BANNER_RE.search(it["text"])
                      and ((not continuation and len(it["text"].split()) <= 12)
                           or re.match(r"^(?:vol\.|volume)\s",it["text"],re.I)
                           or (MASTHEAD_RE.search(it["text"]) and len(it["text"])<160 and not starts_lower(it["text"]))
                           or keys[margin_key(it["text"])] >= need and not starts_lower(it["text"])))
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
        if cnt >= max(2, 0.6 * len({p for p, _ in digits})):
            return {str(p): str(p + off) for p in pnos if p + off > 0}
    # A constant logo or reversed sequence is not a folio. Preserve isolated
    # labels and Roman front matter, but never fill pages from invalid digits.
    by_page = {p: l for p, l in pairs}
    numeric = sorted((p, int(l)) for p, l in by_page.items() if l.isdigit())
    valid = len(numeric) < 2 or all(b > a for (_, a), (_, b) in zip(numeric, numeric[1:]))
    return {str(p): l for p, l in by_page.items() if valid or not l.isdigit()}


def text_container(box, lines, body, column_flow=False):
    """A ruled enclosure containing a paragraph is a text container, not a table.

    Require consecutive body-sized, sentence-like lines with ordinary line spacing;
    table cells and isolated axis labels do not establish a paragraph.
    """
    inside = [l for l in lines if box[0] <= l["x0"] and l["x1"] <= box[2]
              and box[1] <= l["top"] and l["bottom"] <= box[3]
              and not TABLE_NOTE_RE.match(l["text"])
              and sum(c.isalpha() for c in l["text"]) > len(l["text"]) / 2]
    all_text = sum(len(l["text"]) for l in lines if box[0] <= l["x0"] and l["x1"] <= box[2]
                   and box[1] <= l["top"] and l["bottom"] <= box[3])
    if sum(len(l["text"]) for l in inside) <= all_text / 2:
        return False
    long_lines = [l for l in inside if word_count(l["text"]) >= 6]
    if sum(len(l["text"]) for l in long_lines) > all_text / 2:
        for a, b, c in zip(long_lines, long_lines[1:], long_lines[2:]):
            if (abs(a["x0"] - b["x0"]) <= body and abs(b["x0"] - c["x0"]) <= body
                    and -0.5 * body <= b["top"] - a["bottom"] <= body
                    and -0.5 * body <= c["top"] - b["bottom"] <= body
                    and any(end_terminal(l["text"]) for l in (a, b, c))):
                return True
    if not column_flow:
        return False
    # Test paragraph runs within each left-edge cluster. Interleaved lines from
    # two columns must not make a genuine text container look like a graphic.
    columns = []
    for ln in sorted(inside, key=lambda l: l["x0"]):
        if not columns or ln["x0"] - columns[-1][0]["x0"] > body:
            columns.append([])
        columns[-1].append(ln)
    paragraphs = 0
    for col in columns:
        col.sort(key=lambda l: l["top"])
        run = []
        for ln in col:
            if run and not -0.5 * body <= ln["top"] - run[-1]["bottom"] <= body:
                run = []
            run.append(ln)
            # Keep the former 3 × 6-word evidence mass across the paragraph,
            # rather than rejecting its short final line or narrow columns.
            if (len(run) >= 3 and sum(word_count(l["text"]) for l in run) >= 18
                    and any(end_terminal(l["text"]) for l in run)):
                paragraphs += 1
                break
    # One sentence can wrap from the left column into the right. Require two
    # independently populated, horizontally disjoint columns, not two sentence
    # endings; an indented first-line cluster is not another column.
    supporting = [col for col in columns if len(col) >= 3 and sum(word_count(l["text"]) for l in col) >= 18]
    if paragraphs and any(max(l["x1"] for l in left) < min(l["x0"] for l in right)
                          and max(min(l["top"] for l in left), min(l["top"] for l in right))
                              < min(max(l["bottom"] for l in left), max(l["bottom"] for l in right))
                          for i, left in enumerate(supporting) for right in supporting[i+1:]):
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


def rule_tables(objs, ox, oy, W, lines=()):
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
            barrier = q is not None and any(
                run[-1][3] < l["top"] and l["bottom"] < q[1]
                and r[0] <= (l["x0"]+l["x1"])/2 <= r[2]
                and (re.match(r"^(?:table|tab\.|exhibit)\s",l["text"],re.I) and CAPTION_RE.match(l["text"]) or NUM_HEAD_RE.match(l["text"])
                     and l.get("bold",0)>=.85 and re.search(r"[A-Za-z]{3,}",l["text"]))
                for l in lines)
            if q is not None and q[1] - run[-1][3] <= 450 and not barrier:
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


def early_float_regions(page, words, boxes, body):
    """Find float regions before columns or typing, using drawing extents.

    Ruled tables use the same shared-edge evidence as pdfplumber TableFinder;
    shaded row bands provide the corresponding edges in unruled tables.
    Captions anchor a run of such bands. Vector plots retain their labels up to
    the neighbouring body/caption line instead of treating each panel alone.
    """
    lines = make_lines(words, gap_split=True)
    containers = [f for f in boxes if text_container(f, lines, body)]
    prose_sizes = [l["size"] for l in lines if word_count(l["text"])>=6
                   and abs(l["size"]-body)<=max(1,.15*body)
                   and not TABLE_NOTE_RE.match(l["text"]) and not CAPTION_RE.match(l["text"])
                   and not any(f[0]<=l["x0"] and l["x1"]<=f[2] and f[1]<=l["top"] and l["bottom"]<=f[3]
                               for f in boxes)]
    local_body = statistics.median(prose_sizes) if prose_sizes else body
    # Equal-width rules can belong to separate floats (or a running header).
    # Reconstruct their regions with textual boundaries before any typing.
    if (any(len(f)>4 and f[4]=="rules" for f in boxes)
            and (getattr(page,"lines",[]) or getattr(page,"rects",[]))):
        ox, oy = map(float, getattr(page,"bbox",(0,0))[:2])
        boxes = [f for f in boxes if f in containers or not (len(f)>4 and f[4]=="rules")]
        rebuilt = rule_tables((list(getattr(page,"rects",[]))+list(getattr(page,"curves",[]))
                              +list(getattr(page,"lines",[])))[:3000],
                             ox,oy,page.width,lines)
        boxes += [f for f in rebuilt if not any(c[0]<=f[0] and c[1]<=f[1] and f[2]<=c[2] and f[3]<=c[3]
                                               for c in containers)]
    containers = [f for f in boxes if text_container(f, lines, body)]
    def body_text_box(f):
        ls = [l for l in lines if f[0]-body<=l["x0"] and l["x1"]<=f[2]+body
              and f[1]<=l["top"] and l["bottom"]<=f[3] and l["size"]>=body-0.5
              and word_count(l["text"])>=6 and sum(c.isalpha() for c in l["text"])>len(l["text"])/2]
        return any(a.get("font")==b.get("font")==c.get("font")
                   and 0<=b["top"]-a["bottom"]<=body and 0<=c["top"]-b["bottom"]<=body
                   for a,b,c in zip(ls,ls[1:],ls[2:]))
    floats = [list(f) for f in boxes if f not in containers and not (len(f)==4 and body_text_box(f))]
    # Raster figures supply the same caption boundary as vector drawings.
    ox,oy=map(float,getattr(page,"bbox",(0,0))[:2])
    caption_floats = floats + [[float(i["x0"])-ox,float(i["top"])-oy,float(i["x1"])-ox,float(i["bottom"])-oy]
               for i in getattr(page,"images",[]) if float(i["x1"])-float(i["x0"])>body
               and float(i["bottom"])-float(i["top"])>body
               and not (float(i["x1"])-float(i["x0"])>=page.width/2
                        and float(i["bottom"])-float(i["top"])>=page.height/2)]
    captions = [l for l in lines if (CAPTION_RE.match(l["text"]) or CAPTION_TITLE_RE.match(l["text"]))
                and word_count(l["text"]) <= 25]
    caption_text = list(captions)
    # Separate explicit captions on a shared row before page-wide ordering
    # can recombine the two figure columns into one line.
    for cap in captions:
        if any(other is not cap and min(cap["bottom"],other["bottom"])>max(cap["top"],other["top"])
               and (other["x0"]-cap["x1"]>body or cap["x0"]-other["x1"]>body) for other in captions):
            group=(cap["x0"],cap["top"])
            for w in caption_word_sources(cap.get("words",[])):
                w["caption_group"]=group
    # Explicit lines and rectangle edges are cell separators, as in pdfplumber's
    # TableFinder (https://github.com/jsvine/pdfplumber#extracting-tables).
    ox, oy = map(float, getattr(page,"bbox",(0,0))[:2])
    rules = []
    if hasattr(page,"edges"):
        rules = [(float(e["x0"])-ox,float(e["top"])-oy,float(e["x1"])-ox)
                 for e in page.edges if e.get("orientation")=="h"]
    else:
        for obj in list(getattr(page,"lines",[]))+list(getattr(page,"rects",[])):
            x0,x1=float(obj["x0"])-ox,float(obj["x1"])-ox
            if x1>x0:
                rules.extend((x0,float(obj[y])-oy,x1) for y in ("top","bottom"))
    for cap in captions:
        nearby = [f for f in caption_floats if (cap["x0"] <= f[2] and cap["x1"] >= f[0]
                        and min(abs(cap["top"]-f[3]),abs(f[1]-cap["bottom"])) <= 2*body)
                       or (cap["x1"] <= f[0]+body and abs(cap["top"]-f[1]) <= 2*body)]
        anchor = min(nearby, key=lambda f:min(abs(cap["top"]-f[3]),abs(f[1]-cap["bottom"]))) if nearby else None
        if anchor is None:
            # Associate an unobstructed caption with the preceding graphic in
            # its column; raster figures can leave a larger caption margin.
            above=[f for f in caption_floats if f[3]<=cap["top"] and f[0]<=cap["x0"]+body and f[2]>=cap["x1"]-body
                   and not any(f[3]<=l["top"] and l["bottom"]<=cap["top"]
                               and l["x0"]<f[2] and l["x1"]>f[0]
                               and not re.match(r"^(?:doi\s*:|https?://doi\.)",l["text"],re.I)
                               for l in lines if l is not cap)]
            if above:
                anchor=max(above,key=lambda f:f[3])
        separators = [r for r in rules if r[0] <= cap["x0"]+body and r[2] >= cap["x1"]-body]
        near_rules = [r for r in separators if min(abs(r[1]-cap["top"]),abs(r[1]-cap["bottom"])) <= 2*body]
        if near_rules:
            edge=min(near_rules,key=lambda r:min(abs(r[1]-cap["top"]),abs(r[1]-cap["bottom"])))
            if anchor is None or len(anchor)>4:
                anchor=[edge[0],edge[1],edge[2],edge[1],"caption_rule"]
        anchored_text = []
        if anchor is None and CAPTION_RE.match(cap["text"]):
            match = CAPTION_RE.match(cap["text"])
            prefix, indent = "", cap["x0"]
            for w in cap.get("words",[]):
                if prefix.strip()==cap["text"][:match.end()].strip():
                    indent = w["x0"]
                    break
                prefix = join_words(prefix,w["text"])
            for edge in sorted((r for r in separators if r[1]>cap["bottom"]),key=lambda r:r[1]):
                region=sorted([l for l in lines if cap["bottom"]<=l["top"] and l["bottom"]<edge[1]
                               and edge[0]-body<=l["x0"] and l["x1"]<=edge[2]+body],key=lambda l:l["top"])
                chain=[cap]+region
                if (region and all(abs(l["size"]-cap["size"])<=.5 and not caption_cells(l)
                                   and abs(l["x0"]-indent)<=.5*cap["size"] for l in region)
                        and all(0<=b["top"]-a["bottom"]<=body for a,b in zip(chain,chain[1:]))
                        and edge[1]-region[-1]["bottom"]<=2*body):
                    anchor=[edge[0],edge[1],edge[2],edge[1],"caption_rule"]
                    anchored_text=region
                    cap["caption_indent"]=region[0]["x0"]
                    break
        if anchor is None and CAPTION_RE.fullmatch(cap["text"].strip()):
            # A label can precede a multi-line title/source block. Reach its
            # ruling edge through that contiguous text block, not a page-sized
            # distance threshold or a table's contents.
            for edge in sorted((r for r in separators if r[1]>cap["bottom"]),key=lambda r:r[1]):
                region=sorted([l for l in lines if cap["bottom"]<=l["top"] and l["bottom"]<edge[1]
                               and edge[0]-body<=l["x0"] and l["x1"]<=edge[2]+body],key=lambda l:l["top"])
                chain=[cap]+region
                if (region and all(abs(l["size"]-cap["size"])<=.5 and not caption_cells(l)
                                   and not (CAPTION_RE.match(l["text"]) or CAPTION_TITLE_RE.match(l["text"])) for l in region)
                        and all(0<=b["top"]-a["bottom"]<=body for a,b in zip(chain,chain[1:]))
                        and edge[1]-region[-1]["bottom"]<=body):
                    anchor=[edge[0],edge[1],edge[2],edge[1],"caption_rule"]
                    anchored_text=region
                    break
        wrapped = any(l["x0"] <= cap["x0"]+body and l["x1"] >= cap["x0"]
                      and 0 <= cap["top"]-l["bottom"] <= body and l.get("font")==cap.get("font")
                      and abs(l["size"]-cap["size"]) <= .15*body and word_count(l["text"])>=6
                      and not end_terminal(l["text"]) and not any(l["bottom"] <= r[1] <= cap["top"] for r in separators)
                      for l in lines if l is not cap)
        group = (cap["x0"], cap["top"]) if anchor is not None and not wrapped else None
        if group is None:
            continue
        label = CAPTION_RE.match(cap["text"])
        if label and cap.get("caption_indent") is None:
            label_text = cap["text"][:label.end()].strip()
            prefix = ""
            for w in cap.get("words",[]):
                if prefix.strip()==label_text:
                    if any(0<=l["top"]-cap["bottom"]<=.5*body
                           and abs(l["x0"]-w["x0"])<=max(1,.15*body)
                           and abs(l["size"]-cap["size"])<=.5 and not caption_cells(l)
                           for l in lines):
                        cap["caption_indent"] = w["x0"]
                    break
                prefix = join_words(prefix,w["text"])
        left, measure = min(cap["x0"],anchor[0]), max(cap["x1"],anchor[2])
        if anchored_text:
            measure=max([cap["x1"]]+[l["x1"] for l in anchored_text])
        if cap["x1"] <= anchor[0]+body and abs(cap["top"]-anchor[1]) <= 2*body:
            side = [l for l in lines if l["x1"] <= anchor[0] and anchor[1]-body <= l["top"] <= anchor[3]
                    and abs(l["x0"]-cap["x0"]) <= max(1,.15*body) and abs(l["size"]-cap["size"]) <= .5]
            left, measure = cap["x0"], max([cap["x1"]]+[l["x1"] for l in side])
        if len(anchor)==4 and anchor[0] <= (cap["x0"]+cap["x1"])/2 <= anchor[2] and anchor[1] <= (cap["top"]+cap["bottom"])/2 <= anchor[3]:
            style=(cap.get("words") or [{}])[-1].get("font",cap.get("font"))
            aligned=[l for l in lines if abs(l["x0"]-cap["x0"]) <= max(1,.15*body)
                     and abs(l["size"]-cap["size"])<=.5 and anchor[1]-body <= l["top"] <= anchor[3]
                     and (l.get("words") or [{}])[0].get("font",l.get("font"))==style
                     and not caption_cells(l) and sum(c.isalpha() for c in l["text"])>len(l["text"])/2]
            left,measure=cap["x0"],max([cap["x1"]]+[l["x1"] for l in aligned])
        if abs((cap["x0"]+cap["x1"]-left-measure)/2) <= max(1,.15*cap["size"]) and cap["x0"]>left+body:
            cap["caption_center"]=(cap["x0"]+cap["x1"])/2
            measure=cap["x1"]
        below=[r[1] for r in separators if r[1]>cap["bottom"]]
        if below and min(below)-cap["bottom"]<=2*body and not CAPTION_RE.fullmatch(cap["text"].strip()):
            # The title's measure belongs to its text block, which can be
            # narrower than the grid. A ruling line bounds that title region.
            title_lines=[l for l in lines if cap["top"]<=l["top"] and l["bottom"]<min(below)
                         and abs(l["x0"]-cap["x0"])<=max(1,.15*body)
                         and abs(l["size"]-cap["size"])<=.5 and not caption_cells(l)
                         and l["x1"]<=measure+max(1,.15*body)]
            measure=max([cap["x1"]]+[l["x1"] for l in title_lines])
        if not CAPTION_RE.fullmatch(cap["text"].strip()) and not cap.get("caption_center"):
            # The caption's first text line establishes its measure, rather
            # than a graphic spanning several text columns.
            measure=min(measure,cap["x1"])
        def portion(ln):
            if abs(ln["x0"]-cap["x0"])<=max(1,.15*body) and not caption_cells(ln):
                return ln
            ws = [w for w in ln.get("words",[]) if left-max(1,.15*body) <= w["x0"] and w["x1"] <= measure+max(1,.15*body)]
            return line_from_words(ws) if ws else None
        def in_float(ln):
            return (any(cap["bottom"] < r[1] <= ln["top"] for r in separators)
                    or any(f[0] <= (ln["x0"]+ln["x1"])/2 <= f[2] and f[1] <= (ln["top"]+ln["bottom"])/2 <= f[3]
                           and not (f[0] <= (cap["x0"]+cap["x1"])/2 <= f[2] and f[1] <= (cap["top"]+cap["bottom"])/2 <= f[3]) for f in floats))
        if len(anchor) == 4:
            # Caption-adjacent prose outside a vector drawing is not plot ink.
            # Protect it from graphic expansion without assuming it is a wrap.
            for ln in lines:
                if (0 <= ln["top"]-cap["bottom"] <= body and not in_float(ln)
                        and abs(ln["x0"]-cap["x0"]) <= max(1,.15*body)
                        and abs(ln["size"]-cap["size"]) <= .5
                        and (ln.get("words") or [{}])[0].get("font",ln.get("font")) == (cap.get("words") or [{}])[-1].get("font",cap.get("font"))
                        and sum(c.isalpha() for c in ln["text"]) > len(ln["text"])/2):
                    caption_text.append(ln)
        # A label and its title may be separate text runs on one baseline.
        # Their row must be outside the table, with no interior cell gaps.
        if CAPTION_RE.fullmatch(cap["text"].strip()):
            titles = [p for ln in lines if ln is not cap and (p:=portion(ln))
                      and p["x0"] >= cap["x1"] and min(p["bottom"],cap["bottom"])-max(p["top"],cap["top"]) >= .5*min(p["size"],cap["size"])
                      and not in_float(p) and not caption_cells(p) and abs(p["size"]-cap["size"]) <= .15*cap["size"]
                      and sum(c.isalpha() for c in p["text"]) > len(p["text"])/2]
            if titles:
                title = min(titles,key=lambda l:l["x0"])
                cap.update(line_from_words(cap["words"]+title["words"]))
                cap["caption_indent"] = title["x0"]
                caption_text.append(title)
        for w in caption_word_sources(cap.get("words", [])):
            w["caption_group"], w["caption_measure"], w["caption_indent"],w["caption_center"] = group, measure, cap.get("caption_indent"),cap.get("caption_center")
        tail = cap
        caption_spacing = []
        for ln in lines:
            ln = portion(ln)
            if ln is None or ln["top"] <= cap["top"] or ln["top"] < tail["bottom"]:
                continue
            label_title = (CAPTION_RE.fullmatch(tail["text"].strip()) and not caption_cells(ln)
                           and abs(ln["size"]-cap["size"]) <= .15*cap["size"]
                           and abs(ln["x0"]-cap["x0"]) <= max(1,.15*body))
            # A figure legend/source note is a caption paragraph, not a line
            # wrap of its short title. Require the same bounded caption region
            # and smaller-than-body typography; never cross into table cells.
            wrap = caption_wrap(tail,ln,cap.get("caption_indent") or cap["x0"],measure)
            component = (not caption_cells(ln) and abs(ln["x0"]-cap["x0"])<=max(1,.15*body)
                         and (ln["size"]<=body-.5 or TABLE_NOTE_RE.match(ln["text"]) and ln["size"]<=body)
                         and abs(ln["size"]-tail["size"])<=.5
                         and (TABLE_NOTE_RE.match(ln["text"])
                              or caption_spacing and ln["top"]-tail["bottom"]>statistics.median(caption_spacing)
                              and not NOTE_MARK_RE.match(ln["text"])
                              and ln.get("font") in {w.get("font") for w in tail.get("words",[])}))
            if (ln["top"]-tail["bottom"]>body or in_float(ln)
                    or CAPTION_RE.match(ln["text"]) or CAPTION_TITLE_RE.match(ln["text"])
                    or not (label_title or component or wrap)):
                break
            if wrap and not component:
                caption_spacing.append(ln["top"]-tail["bottom"])
            if component:
                cap["caption_indent"]=ln["x0"]
                measure=ln["x1"]
            else:
                measure=max(measure,ln["x1"])
            caption_text.append(ln)
            for w in caption_word_sources(ln.get("words", [])):
                w["caption_group"], w["caption_measure"], w["caption_indent"],w["caption_center"] = group, measure, cap.get("caption_indent"),cap.get("caption_center")
            ln["caption_center"],ln["caption_indent"],ln["caption_measure"]=cap.get("caption_center"),cap.get("caption_indent"),measure
            tail=ln
    ox, oy = map(float, getattr(page,"bbox",(0,0))[:2])
    bands = []
    for r in getattr(page, "rects", []):
        x0, x1 = float(r["x0"])-ox, float(r["x1"])-ox
        top, bottom = float(r["top"])-oy, float(r["bottom"])-oy
        if x1-x0 > 0.5 * page.width and bottom-top > body:
            bands.append([x0, top, x1, bottom])
    # Adjacent shaded cells are one row band, just as joined rule segments
    # are one edge in pdfplumber's table finder. Use the connected drawing
    # extents already computed above rather than demanding a single wide rect.
    bands += [list(f[:4]) for f in boxes if len(f)==4 and f[2]-f[0]>0.5*page.width and f[3]-f[1]>body]
    for cap in captions:
        if not re.match(r"^(?:table|tab\.)\s", cap["text"], re.I):
            continue
        following = [r for r in bands if r[1] >= cap["bottom"] and r[1]-cap["bottom"] <= 2*body]
        if not following:
            continue
        first = max(following, key=lambda r:r[2]-r[0])
        aligned = [r for r in bands if r[1] >= first[1] and abs(r[0]-first[0]) <= 0.15*body
                   and abs(r[2]-first[2]) <= 0.15*body]
        boundary = min((l["top"] for l in lines if l["top"] > first[3]
                        and (CAPTION_RE.match(l["text"]) or NUM_HEAD_RE.match(l["text"]) and l.get("bold",0)>=.85
                             or l["size"] >= body-.5 and word_count(l["text"])>=6
                             and not any(r[1]<=l["top"] and l["bottom"]<=r[3] for r in aligned))),
                       default=float("inf"))
        aligned = [r for r in aligned if r[1] < boundary]
        # Multiple row bands, or a header band followed by aligned numeric cells.
        below = [l for l in lines if l["top"] >= first[1] and l["x0"] >= first[0]-body
                 and l["x1"] <= first[2]+body]
        if len(aligned) < 2 and sum(bool(re.search(r"\d.*\d", l["text"])) for l in below) < 3:
            continue
        bottom = max(r[3] for r in aligned)
        if len(aligned) == 1:
            for ln in below:
                if ln["size"] >= body - 0.5 and word_count(ln["text"]) >= 6:
                    break
                if ln["top"] > bottom + 2*body and not re.search(r"\d|\bYES\b|\bNO\b",ln["text"],re.I):
                    break
                bottom = max(bottom, ln["bottom"])
        floats.append([first[0], first[1], first[2], bottom, "table"])
    for box in floats:
        drawing_bounds = box[:4]
        if len(box)>4 and box[4]=="table":
            # A final unshaded row can follow the last shaded/ruling band.
            # Use repeated cell starts, as in pdfplumber's text table strategy;
            # one full-width prose run cannot establish another table row.
            inside=[l for l in lines if box[1]<=l["top"] and l["bottom"]<=box[3]
                    and box[0]<=l["x0"] and l["x1"]<=box[2]]
            below=sorted([l for l in lines if 0<=l["top"]-box[3]<=body
                          and box[0]<=l["x0"] and l["x1"]<=box[2]],key=lambda l:l["top"])
            if below:
                row=[l for l in below if min(l["bottom"],below[0]["bottom"])-max(l["top"],below[0]["top"])>=.5*min(l["size"],below[0]["size"])]
                aligned=[l for l in row if any(abs(l["x0"]-p["x0"])<=.3*body for p in inside)]
                if (len(aligned)>=2 and any(a["x1"]+body<b["x0"] for a in aligned for b in aligned)):
                    box[3]=max(l["bottom"] for l in row)
                    cells=[(l["x0"],l["x1"]) for l in row]
                    for l in sorted(lines,key=lambda l:l["top"]):
                        if (0<=l["top"]-box[3]<=body and any(a-body<=l["x0"] and l["x1"]<=b+body for a,b in cells)
                                and abs(l["size"]-row[0]["size"])<=.5):
                            box[3]=max(box[3],l["bottom"])
        if len(box)==4:
            def family(font):
                font=re.sub(r"^[A-Z]{6}\+","",font)
                return re.sub(r"[-,.](?:bold|italic|oblique|regular|roman|medium|bolditalic|boldoblique)(?:MT)?$","",font,flags=re.I)
            label_fonts={family(w.get("font","")) for w in words if w["size"]<body-.5
                         and box[0]<=w["x0"] and w["x1"]<=box[2]
                         and box[1]<=w["top"] and w["bottom"]<=box[3]}
            prose_fonts={family(l.get("font","")) for l in lines if word_count(l["text"])>=6
                         and abs(l["size"]-body)<=.5}
            # Plot titles can be larger than body type. Their font family and
            # immediate placement above the panel connect them to its labels;
            # they must not become section barriers during paragraph joining.
            for ln in lines:
                if (ln["size"]>body+.5 and 0<=box[1]-ln["bottom"]<=body and box[0]<=ln["x0"] and ln["x1"]<=box[2]
                        and word_count(ln["text"])<=12 and not end_terminal(ln["text"])
                        and family(ln.get("font","")) in label_fonts-prose_fonts
                        and not (CAPTION_RE.match(ln["text"]) or CAPTION_TITLE_RE.match(ln["text"]))):
                    for w in ln.get("words",[]):
                        w["graphic"]=True
            # Disconnected panels may be far from their shared caption. Nearby
            # small lettering is evidence against a heading, without hiding any
            # prose in the gaps between panels or treating the union as a box.
            for w in words:
                if (w["size"]<body-0.5 and box[0]-body<=(w["x0"]+w["x1"])/2<=box[2]+body
                        and box[1]-body<=(w["top"]+w["bottom"])/2<=box[3]+body):
                    w["graphic_label"]=True
        if len(box)==4 and not any(
                (abs(l["top"]-box[3])<=2*body or abs(box[1]-l["bottom"])<=2*body)
                and l["x0"]<=box[2] and l["x1"]>=box[0] for l in captions):
            continue
        # A sparse vector plot's own title/axis labels can sit just outside its
        # drawing bbox. Do not extend a table across neighbouring paragraphs.
        if len(box) == 4:
            near = [l for l in lines if l["size"] < body - 0.5
                    and not (CAPTION_RE.match(l["text"]) or CAPTION_TITLE_RE.match(l["text"]))
                    and l["x0"] <= box[2]+body and l["x1"] >= box[0]-body
                    and l["top"] <= box[3]+body and l["bottom"] >= box[1]-body
                    and word_count(l["text"]) <= 12]
            if near:
                box[0]=min(box[0],*(l["x0"] for l in near));box[2]=max(box[2],*(l["x1"] for l in near))
                box[1]=min(box[1],*(l["top"] for l in near));box[3]=max(box[3],*(l["bottom"] for l in near))
        # Small prose immediately below the last rule is the table's note, not
        # a footnote or a continuation of the surrounding body.
        elif box[4] == "table" and any((CAPTION_RE.match(l["text"]) or CAPTION_TITLE_RE.match(l["text"])) and abs(l["bottom"]-box[1])<=2*body for l in captions):
            # Only a validated table owns the following note region. Candidate
            # rule spans must not move surrounding notes between layout bands.
            note = None
            for ln in sorted(lines,key=lambda l:l["top"]):
                if (0 <= ln["top"]-box[3] <= body and ln["size"] < body-0.5
                        and ln["x0"] >= box[0]-body and ln["x1"] <= box[2]+body
                        and not (CAPTION_RE.match(ln["text"]) or CAPTION_TITLE_RE.match(ln["text"]))
                        and (TABLE_NOTE_RE.match(ln["text"])
                             or note is None and ln["size"]<local_body-.5 and word_count(ln["text"])>=6
                             or note is not None and bool(
                                 {w.get("font") for w in ln.get("words",[]) if not re.search(r"math|symbol",w.get("font",""),re.I)}
                                 & {w.get("font") for w in note.get("words",[]) if not re.search(r"math|symbol",w.get("font",""),re.I)})
                             and abs(ln["size"]-note["size"])<=.5)):
                    box[3]=max(box[3],ln["bottom"])
                    note = ln
        for w in words:
            if len(box)>4 and box[4]!="table":
                continue  # rule spans are candidates; retain the line-level fallback, not authoritative word typing
            if any(l["top"]<=w["top"] and w["bottom"]<=l["bottom"] and l["x0"]<=w["x0"] and w["x1"]<=l["x1"] for l in caption_text):
                continue
            if (box[0] <= (w["x0"]+w["x1"])/2 <= box[2]
                    and box[1] <= (w["top"]+w["bottom"])/2 <= box[3]):
                w["tab" if len(box)>4 else "graphic"] = True
        if len(box)==4:
            box[:4] = drawing_bounds  # label expansion affects typing, not the body-column geometry
    body_boxes = [f for f in boxes if f not in containers and len(f)==4 and body_text_box(f)]
    return floats + containers + body_boxes


def document_gutters(pages, body):
    """Infer a repeated column template (Déjean's page-template principle).

    A strict majority of text pages must agree, on at least two pages. This is
    only a prior for sparse regions; local full-width prose always vetoes it.
    """
    layouts = []
    for p in pages:
        prose = [l for l in make_lines(p["words"], gap_split=True)
                 if abs(l["size"]-body) <= 0.5 and word_count(l["text"]) >= 6
                 and sum(c.isalpha() for c in l["text"]) > len(l["text"])/2]
        if len(prose) >= 10:  # the projection detector's minimum evidence
            layouts.append([g/p["w"] for g in column_gutters(prose,p["w"],body)])
    counts = Counter(len(gs) for gs in layouts)
    if not counts:
        return []
    size, support = counts.most_common(1)[0]
    if not size or support < 2 or support <= len(layouts)/2:
        return []
    matches = [gs for gs in layouts if len(gs)==size]
    return [statistics.median(gs[i] for gs in matches) for i in range(size)]


def regional_gutters(segs, width, body, prior=()):
    """XY-cut: learn columns in vertical regions before full-width front matter
    can dominate the page projection. Prefer evidence in ordinary body type.
    """
    candidates = []
    for region in slabs_by_gap(segs, max(3, 0.4 * body)):
        evidence = [l for l in region if not l.get("tab") and not l.get("graphic")
                    and word_count(l["text"]) >= 6
                    and sum(c.isalpha() for c in l["text"]) > len(l["text"])/2]
        gs = column_gutters(evidence, width, body)
        if not gs and prior:
            ordinary = [l for l in evidence if abs(l["size"]-body) <= 0.5]
            edges = [-float("inf")] + list(prior) + [float("inf")]
            fits = (ordinary and not any(l["x0"] < g-1 and l["x1"] > g+1 for l in ordinary for g in prior)
                    and all(sum(a <= l["x0"] and l["x1"] <= b for l in ordinary) >= 2
                            for a,b in zip(edges,edges[1:])))
            if fits:
                gs = list(prior)
        if gs:
            mass = sum(len(l["text"]) for l in region if abs(l["size"]-body) <= 0.5)
            candidates.append((mass, gs))
    return max(candidates, key=lambda x: x[0])[1] if candidates else []


def repeated_pull_quotes(segs, boxes, gutters, body):
    """Large boxed repetitions are pull quotes, independently of nearby syntax."""
    normalize = lambda t: "".join(c for c in unicodedata.normalize("NFKC", t).casefold() if c.isalnum())
    columns = defaultdict(list)
    for ln in segs:
        if ln["size"] < body + 2:
            columns[sum((ln["x0"]+ln["x1"])/2 > g for g in gutters)].append(ln)
    prose = [normalize(" ".join(l["text"] for l in sorted(ls,key=lambda l:l["top"]))) for ls in columns.values()]
    pull, matched = [], []
    for box in boxes:
        inside = [l for l in segs if box[0]-2 <= l["x0"] and l["x1"] <= box[2]+2
                  and box[1]-2 <= l["top"] and l["bottom"] <= box[3]+2 and l["size"] >= body + 2]
        text = " ".join(l["text"] for l in inside)
        if word_count(text) >= 6 and any(normalize(text) in t for t in prose):
            matched.append(box)
            for ln in inside:
                ln["pull"] = True
                pull.append(ln)
    return pull, matched


def contextual_openers(pages, body):
    """Carry continuation evidence into typing; page boundaries aren't headings."""
    previous = None
    for p in pages:
        ls = [l for l in p["lines"] if not l.get("tab") and not l.get("graphic")
              and not l.get("front_meta") and abs(l["size"]-body)<=max(1,0.15*body)]
        if ls and previous and p["pno"] == previous[0]+1:
            first = ls[0]
            if (not end_terminal(previous[1]["text"]) and
                    (starts_lower(first["text"]) or first["text"].startswith("("))):
                first["page_top_continuation"] = True
                first.pop("force_heading",None)
        if ls:
            previous = (p["pno"],ls[-1])


def mark_display_lines(lines, body_font, body=None):
    """Identify displays before grouping; variable names need not be single letters.

    Ordinary-font prose separates inline math from displays. Symbolic font
    evidence survives text layers that misdecode mathematical operators.
    """
    small_rows = set()
    for index, ln in enumerate(lines):
        ws = ln.get("words", [])
        if ln.get("caption_group") or re.search(r"https?://|www\.", ln["text"], re.I):
            continue
        symbols = sum(len(w["text"]) for w in ws if w.get("symbolic"))
        operator_ink = sum(1 for w in ws if w.get("symbolic") for c in w["text"]
                           if not c.isascii() or not c.isalnum())
        total = sum(len(w["text"]) for w in ws) or 1
        prose = any(w.get("font") == body_font and (body is None or w["size"] >= body-0.5)
                    and re.fullmatch(r"[A-Za-z]{3,}[.,;:!?]?", w["text"])
                    and not re.fullmatch(r"ln|log|exp|sin|cos|tan|min|max",w["text"]) for w in ws)
        math_font = any(w.get("symbolic") or re.search(r"math|symbol|cmsy|cmmi", w.get("font", ""), re.I) for w in ws)
        long_words = any(re.search(r"[A-Za-z]{3,}",w["text"]) for w in ws)
        # Sentence words remain prose in italic definitions and small notes too.
        # A mathematical font alone cannot distinguish inline from displayed math.
        ordinary = [w for w in ws if re.fullmatch(r"[a-z]{3,}[.,;:!?]?", w["text"])
                    and w["size"] >= ln["size"] - 0.5
                    and not re.search(r"math|symbol|cmsy|cmmi",w.get("font", ""), re.I)
                    and not re.fullmatch(r"(?:ln|log|exp|sin|cos|tan|min|max)[(.,]?",w["text"])]
        prose = prose or len(ordinary) >= 2
        ln["inline_math_prose"] = (body is not None and ln["size"]<body-.5 and len(ordinary)>=2
                                   and sum(w["text"].isalpha() and re.search(r"math|symbol",w.get("font",""),re.I) is not None for w in ws)>=2
                                   and not ln.get("display_region") and not ln.get("footnote"))
        previous = lines[index - 1] if index else None
        if ln.get("ocr_layer") and body is not None and not ln.get("tab") and not ln.get("graphic"):
            peers = [l for l in lines if l.get("band")==ln.get("band") and l.get("col")==ln.get("col")
                     and word_count(l["text"])>=3 and end_terminal(l["text"]) and "=" not in l["text"]]
            edge = min((l["x0"] for l in peers),default=ln["x0"])
            notation = len(re.findall(r"\b[A-Za-z]\b",ln["text"])) >= 3 and bool(re.search(r"[=+−-]",ln["text"]))
            if (notation and ln["x0"] > edge+body and not ordinary
                    and (previous is None or previous["text"].endswith(":")
                         or previous["bottom"] < ln["top"]-body)):
                ln["display_region"] = True
            elif (previous and previous.get("display_region") and "=" in ln["text"]
                  and 0<=ln["top"]-previous["bottom"]<=2*body
                  and not end_terminal(ln["text"])):
                ln["display_region"] = True  # a displayed word equation/gloss
            elif (previous and previous.get("display_region") and "=" in previous["text"]
                  and word_count(ln["text"])<=2 and not end_terminal(ln["text"])
                  and 0<=ln["top"]-previous["bottom"]<=body):
                ln["display_region"] = True
        if (previous and body is not None and not previous.get("display_region")
                and (previous.get("band"), previous.get("col")) == (ln.get("band"), ln.get("col"))
                and not end_terminal(previous["text"]) and word_count(previous["text"]) >= 6
                and re.search(r"[A-Za-z]{3,}", previous["text"])
                and 0 <= ln["top"] - previous["bottom"] <= max(0.45 * body, 2.5)):
            prose = True  # an uninterrupted prose line can wrap into inline notation
        variables = sum(len(w["text"]) == 1 and w["text"].isalpha() for w in ws)
        small_notation = bool(ws) and all(len(w["text"]) <= 2 or w["text"].isdigit() for w in ws)
        notation_part = small_notation and any(w.get("italic") for w in ws)
        if (body is not None and (ln["size"] < body-0.5 and math_font and (variables >= 2 or small_notation)
                                  or ln["size"] <= body+0.5 and notation_part) and not prose
                and not ln.get("tab") and not ln.get("graphic")):
            small_rows.add(index)
        if body is not None and ln["size"] > body+1 and long_words:
            continue
        if not ln.get("tab") and not ln.get("graphic") and not prose and (
                symbols > total / 2 and not long_words and variables >= 2
                or operator_ink >= 2 and variables >= 2
                or math_font and EQUATION_RE.search(ln["text"])):
            ln["display_region"] = True
    # A word equation still has a numbered display's indentation and whitespace.
    # Its vocabulary must not override that independent layout evidence.
    if body is not None:
        for i,ln in enumerate(lines):
            peers = [l for l in lines if l.get("key",(l.get("band"),l.get("col"))) == ln.get("key",(ln.get("band"),ln.get("col")))
                     and word_count(l["text"])>=6 and not l.get("tab") and not l.get("graphic")]
            left = min((l["x0"] for l in peers),default=ln["x0"])
            if (ln.get("display_region") or sum(bool(re.fullmatch(r"[A-Za-z]{3,}",w["text"])) and any(c.islower() for c in w["text"]) for w in ln.get("words",[]))<2
                    or "=" not in ln["text"] or not EQ_NUMBER_RE.search(ln["text"])
                    or ln["x0"]<=left+.8*body or ln.get("tab") or ln.get("graphic")):
                continue
            ln["display_region"] = True
            ln["inline_math_prose"] = False
            for direction in (-1,1):
                last = ln
                j = i+direction
                while 0<=j<len(lines):
                    other = lines[j]
                    upper,lower = sorted((last,other),key=lambda l:l["top"])
                    if (other.get("band")!=ln.get("band") or other.get("col")!=ln.get("col")
                            or other["x0"]<=left+.8*body or other.get("tab") or other.get("graphic")
                            or other.get("caption_candidate") or end_terminal(other["text"])
                            or not re.search(r"[=+\u2212\u2211\u222b\u23a1\u23a4\u23a3\u23a6]",other["text"]) and word_count(other["text"])>=6
                            or lower["top"]-upper["bottom"]>body):
                        break
                    other["display_region"] = True
                    other["inline_math_prose"] = False
                    last = other
                    j += direction
    # Subscripts and denominators may be a separate small-font row. Associate
    # them only with an adjacent established display in the same column.
    pending = set(small_rows)
    while pending:
        found = set()
        for i in pending:
            ln = lines[i]
            for j in (i-1,i+1):
                if not 0 <= j < len(lines):
                    continue
                other = lines[j]
                upper, lower = sorted((ln,other),key=lambda l:l["top"])
                if (other.get("display_region") and (ln.get("band"),ln.get("col")) == (other.get("band"),other.get("col"))
                        and -body <= lower["top"]-upper["bottom"] <= body
                        and ln["x0"] <= other["x1"] and ln["x1"] >= other["x0"]):
                    ln["display_region"] = True
                    found.add(i)
                    break
        if not found:
            break
        pending -= found


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
    for p in pages:
        pg=pdf.pages[p["pno"]-1]
        raster=any(i.get("width",0)>=p["w"]/2 and i.get("height",0)>=p["h"]/2 for i in getattr(pg,"images",[]))
        if raster:
            for w in p["words"]:
                w["ocr_layer"]=True
    two_col = multi_col = 0
    if "column_prior" not in cache:
        cache["column_prior"] = document_gutters(pages, body)
    for p in pages:
        p["figs"] = early_float_regions(pdf.pages[p["pno"]-1], p["words"], p["figs"], body)
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
        prior = [g*p["w"] for g in cache["column_prior"]]
        p["column_prior"] = prior
        local_gutters = regional_gutters(column_segs, p["w"], body, prior) if columns == "auto" else []
        template_match = (prior and len(local_gutters)==len(prior)
                          and all(abs(a-b)<=body for a,b in zip(local_gutters,prior)))
        if columns == "auto" and (not gutters or template_match):
            gutters = local_gutters
        pull, pull_boxes = repeated_pull_quotes(segs, layout_boxes, gutters, body)
        if pull:
            segs = [l for l in segs if not l.get("pull")]
            layout_boxes = [b for b in layout_boxes if b not in pull_boxes]
            p["figs"] = [b for b in p["figs"] if b not in pull_boxes]
        p["pull_lines"] = pull
        p["gutters"] = gutters
        if len(gutters) >= 2:  # three or more columns: cut the page at the gutters
            p["sidebar"] = None
            p["lines"] = order_columns(segs, gutters, body, layout_boxes, (p["w"], p["h"]))
            multi_col += 1
            continue
        if columns in ("auto", "2"):
            split = detect_split(column_segs, p["w"], body, force=(columns == "2"))
        unequal = False
        if len(gutters) == 1:
            lsize = [l["size"] for l in column_segs if l["x1"] <= gutters[0]]
            rsize = [l["size"] for l in column_segs if l["x0"] >= gutters[0]]
            unequal = bool(lsize and rsize and abs(statistics.median(lsize) - statistics.median(rsize)) > max(1, 0.15 * body))
        balanced_region = len(local_gutters) == 1 and len(gutters) == 1 and abs(local_gutters[0]-gutters[0]) <= body
        if columns == "auto" and split is None and len(gutters) == 1 and (unequal or balanced_region):
            # The projection detector includes smaller text. A narrow abstract
            # column beside the body must not be discarded by body-size voting.
            p["sidebar"] = None
            p["lines"] = order_columns(segs, gutters, body, layout_boxes, (p["w"], p["h"]))
            small_right = statistics.median(rsize) < statistics.median(lsize)
            for ln in p["lines"]:
                if unequal and ((small_right and ln["x0"] >= gutters[0]) or (not small_right and ln["x1"] <= gutters[0])):
                    ln["independent_text"] = True
            two_col += 1
            continue
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
    repair_front_regions(pages, body)
    for p in pages[:3]:
        for ln in p["lines"]:
            if re.fullmatch(r"abstract",ln["text"].strip(),re.I):
                ln["force_heading"] = True
    repair_ocr_openers(pages, body)
    mark_footnote_lines(pages, body)
    mark_roman_sections(pages, body)
    repair_ocr_linebreaks(pages)
    body_fonts = Counter(w["font"] for p in pages for w in p["words"]
                         if abs(w["size"]-body) <= 0.5 and re.search(r"[A-Za-z]{3,}",w["text"]))
    body_font = body_fonts.most_common(1)[0][0] if body_fonts else None
    for p in pages:
        for ln in p.get("pull_lines", []):
            ln["band"], ln["col"] = max((l["band"] for l in p["lines"]), default=0)+1, 0
            p["lines"].append(ln)
        mark_numeric_regions(p["lines"], body)
        mark_graphic_labels(p["lines"], body)
        mark_contents_page(p["lines"])
        mark_display_lines(p["lines"], body_font, body)
        for ln in p["lines"]:
            ln["body_font"] = ln.get("font") == body_font
        audit_gutters = p.get("gutters") or regional_gutters(make_lines(p["words"], gap_split=True), p["w"], body, p.get("column_prior", []))
        for ln in p["lines"]:
            ln["gutter_crossing"] = any(
                a["x1"] <= g <= b["x0"] and b["x0"]-a["x1"] > max(0.9*body,7)
                for a,b in zip(ln.get("words", []),ln.get("words", [])[1:]) for g in audit_gutters)
    for p in pages:  # text between the rules of a table is table content, whatever its size
        tabs = [f for f in p["figs"] if len(f) > 4]
        for ln in p["lines"]:
            cx, cy = (ln["x0"] + ln["x1"]) / 2, (ln["top"] + ln["bottom"]) / 2
            if not ln.get("abstract") and ln.get("caption_group") is None and any(f[0] <= cx <= f[2] and f[1] <= cy <= f[3] for f in tabs):
                ln["tab"] = True
    labels = []
    removed = strip_margins(pages, lambda p: p["lines"], lambda p, v: p.__setitem__("lines", v), labels)
    contextual_openers(pages, body)
    blocks = []
    for p in pages:
        page_blocks = build_blocks(p["lines"], p["pno"], body) if p["lines"] else []
        page_blocks = restore_drop_caps(page_blocks, p["caps"], body)
        for b in page_blocks:
            b["pw"], b["ph"] = p["w"], p["h"]
            b["unmapped_sources"]=[dict(source,page=p["pno"]) for source in
                                    (p["words"][0].get("unmapped_sources",[]) if p["words"] else [])
                                    if b["top"]-b["size"]<=source["bbox"][3]*p["h"]
                                    and b["bottom"]+b["size"]>=source["bbox"][1]*p["h"]
                                    and b.get("column_x0",0)<=sum(source["bbox"][::2])*p["w"]/2<=b.get("column_x1",float("inf"))]
            if p.get("sidebar") is not None and b["x1"] <= p["sidebar"] + 2 and b["top"] <= p.get("sidebar_bottom", 0):
                b["sidebar"] = True
        # An operator can occupy a line on its own. Associate every unresolved
        # code with the nearest block even when it supplied no readable word.
        for codes, box, raw in p["words"][0].get("unmapped_marks", []) if p["words"] else []:
            if page_blocks:
                cx, cy = (box[0] + box[1]) / 2, (box[2] + box[3]) / 2
                target = min(page_blocks, key=lambda b: (not (b["x0"] <= cx <= b["x1"]),
                                                        max(b["top"] - cy, cy - b["bottom"], 0)))
                target["unmapped_glyphs"] = sorted(set(target.get("unmapped_glyphs", [])) | {f"⟦cid:{cid}⟧" for cid in codes})
                target.setdefault("unmapped_text", []).append(re.sub(r"\(cid:(\d+)\)", r"⟦cid:\1⟧", raw))
                for source in p["words"][0].get("unmapped_sources",[]):
                    if source["raw"]==re.sub(r"\(cid:(\d+)\)",r"⟦cid:\1⟧",raw) and all(
                            abs(a-b)<1e-6 for a,b in zip(source["bbox"],(box[0]/p["w"],box[2]/p["h"],box[1]/p["w"],box[3]/p["h"]))):
                        mark=dict(source,page=p["pno"])
                        if mark not in target.setdefault("unmapped_sources",[]):
                            target["unmapped_sources"].append(mark)
        blocks += page_blocks
    blocks = combine_caption_groups(blocks)
    blocks = join_chapter_openers(blocks, body)
    info = {p["pno"]: {"h": p["h"], "w": p["w"], "figs": p["figs"], "text_overflow": bool(
                any(c["x1"] > pdf.pages[p["pno"] - 1].bbox[2] for c in getattr(pdf.pages[p["pno"] - 1], "chars", []))
                and any(i.get("width", 0) >= p["w"] / 2 and i.get("height", 0) >= p["h"] / 2
                        for i in getattr(pdf.pages[p["pno"] - 1], "images", [])))} for p in pages}
    if pages and cache.get("cover_text"):
        info[pages[0]["pno"]]["cover_titles"] = cover_title_candidates(cache["cover_text"])
    return blocks, body, info, {"two_col": two_col, "multi_col": multi_col, "removed": removed, "labels": labels}


FRONT_META_LABEL_RE = re.compile(r"^(?:key\s*words?|JEL\s+(?:codes?|classification)|article\s+history\b|history\s*:?\s*$|"
                                 r"received\b|accepted\b|revised\b|creative commons licen[cs]e|"
                                 r"(?:selection\s+and/or\s+)?peer[- ]review\b|this (?:work|article) is (?:licensed|available))", re.I)
SCHOLAR_META_RE = re.compile(r"^(?:article\s*(?:info|history)|received\b|revised\b|accepted\b|published\b|available online\b|keywords?\b|history\s*:|supplemental material\b|copyright\b|ISSN\b|doi\s*:|https?://doi\.)|©|\ball rights reserved\b", re.I)


def mark_contents_page(lines):
    entries = [l for l in lines if toc_entry(l["text"])]
    if len(entries) >= 3 and len(entries) > len(lines) / 2:
        for ln in lines:
            ln["contents_page"] = True


def repair_front_regions(pages, body):
    """Segment scholarly headers independently of body columns (GROBID's front/body cascade)."""
    for p in pages:
        segs = make_lines(p["words"], gap_split=True)
        abstracts = [l for l in segs if re.sub(r"\s+", "", l["text"]).lower().startswith("abstract")]
        for abstract in abstracts:
            sections = [l for l in segs if l["top"] > abstract["bottom"] and NUM_HEAD_RE.match(l["text"])
                        and l["bold"] >= 0.85 and l["size"] >= body - 0.5]
            if not sections:
                continue
            end = min(l["top"] for l in sections)
            start = abstract["top"] - 0.5 * body
            region = [l for l in segs if start <= l["top"] < end]
            metadata = [l for l in region if SCHOLAR_META_RE.search(l["text"])]
            left = [l for l in metadata if l["x1"] < abstract["x0"]]
            right = [l for l in metadata if l["x0"] > abstract["x1"]]
            right_meta = not left and len(right) >= 3
            if not left and not right_meta:
                continue  # a normal single-column abstract needs no new layout cut
            if right_meta:
                edge = min(l["x0"] for l in right)
                peers = [l for l in region if l["x1"] < edge and word_count(l["text"]) >= 3]
                if len(peers) < 3:
                    continue
                gutter = (max(l["x1"] for l in peers)+edge)/2
            else:
                gutter = (max(l["x1"] for l in left) + abstract["x0"]) / 2
            trailing = [l["top"] for l in metadata if (l["x1"] < gutter if right_meta else l["x0"] >= gutter)
                        and l["top"] > abstract["bottom"]]
            abstract_end = min(trailing, default=end)
            words = [w for w in p["words"] if start <= w["top"] < end]
            before = [l for l in p["lines"] if l["top"] < start]
            after = [l for l in p["lines"] if l["top"] >= end]
            groups = [[w for w in words if (w["x0"] + w["x1"]) / 2 < gutter],
                      [w for w in words if (w["x0"] + w["x1"]) / 2 >= gutter]]
            ordered = []
            for k, ws in enumerate(groups):
                for ln in make_lines(ws):
                    ln.update(band=-2 + k, col=0)
                    ln["front_meta"] = k == (1 if right_meta else 0) or ln["top"] >= abstract_end or bool(SCHOLAR_META_RE.search(ln["text"]))
                    ln["abstract"] = not ln["front_meta"]
                    ordered.append(ln)
            p["lines"] = before + ordered + after
            titles = [l for l in before if l["size"] >= body + 2.5 and word_count(l["text"]) >= 3
                      and not re.search(r"https?://|www\.|\bISSN\b", l["text"], re.I)]
            if titles:
                title = max(titles, key=lambda l: l["top"])
                title["article_title"] = True
                norm = lambda t: re.sub(r"\W+", "", t).casefold()
                for earlier in pages:
                    if earlier["pno"] >= p["pno"]:
                        break
                    if any(norm(l["text"]) == norm(title["text"]) for l in earlier["lines"]):
                        for ln in earlier["lines"]:
                            ln["front_meta"] = True  # redundant publisher cover sheet
            # Bibliographical footer text belongs to the header, not the argument.
            for ln in p["lines"]:
                if SCHOLAR_META_RE.search(ln["text"]) and ln["size"] < body:
                    ln["front_meta"] = True


def repair_ocr_openers(pages, body):
    """Separate centred title/subtitle/byline rows before prose assembly.

    OCR proxy fonts often give every row the same weight. Relative size,
    a shared centre axis and a gap before the first paragraph survive this.
    """
    for p in pages[:3]:
        lines = p["lines"]
        candidates = [l for l in lines if l.get("ocr_layer") and l["size"] >= body+1
                      and l["top"] < .45*p["h"] and l["text"].isupper()
                      and 3 <= word_count(l["text"]) <= 20
                      and not re.search(r"https?://|www\.|\b(?:ISSN|DOI|VOL)\b",l["text"],re.I)]
        if not candidates:
            continue
        first = min(candidates,key=lambda l:l["top"])
        centre = (first["x0"]+first["x1"])/2
        reach = first["bottom"]
        title_rows = [first]
        for l in sorted((l for l in lines if l["top"] > first["top"]),key=lambda l:l["top"]):
            aligned = abs((l["x0"]+l["x1"])/2-centre) <= body
            if not aligned or l["top"]-reach > 2*body:
                break
            if l["size"] >= first["size"]-.5 and l["text"].isupper():
                l["article_title"] = True
                title_rows.append(l)
            elif l["text"].isupper() and word_count(l["text"]) >= 3 and l["size"] >= body-.5 and not any(x.get("byline") for x in lines):
                l["subtitle"] = True
            elif (re.match(r"^by\s",l["text"],re.I) or any(x.get("byline") for x in lines)) and word_count(l["text"]) >= 2 and not end_terminal(l["text"]) and l["size"] < body:
                l["byline"] = True
            else:
                break
            reach = l["bottom"]
        first["article_title"] = True
        # Leave rows separate for geometry, but make their title evidence agree.
        for l in title_rows:
            l["force_heading"] = True


def title_key(text):
    return re.sub(r"\W+", "", unicodedata.normalize("NFKC",text)).casefold()


def block_title_text(block):
    text = block["text"]
    suffix = block.get("title_suffix")
    if suffix and text.endswith(suffix):
        text = text[:-len(suffix)].rstrip()
    return text


def block_title_key(block):
    return title_key(block_title_text(block))


def cover_title_candidates(text):
    """Title rows immediately precede a labelled author/source cover record.

    Keep possible wrapped rows; the repeated article block disambiguates them.
    Unlabelled covers use the existing repeated-block detection in classify.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i,line in enumerate(lines):
        if (re.match(r"^authors?(?:\(s\))?\s*:",line,re.I)
                and any(re.match(r"^source\s*:",l,re.I) for l in lines[i+1:])):
            return [" ".join(lines[max(0,i-n):i]) for n in range(1,min(3,i)+1)]
    return []


def mark_footnote_lines(pages, body):
    """A raised leading reference mark identifies a note even at body size."""
    for p in pages:
        active = None
        for index,ln in enumerate(p["lines"]):
            ws = ln.get("words", [])
            raised = (len(ws)>=2 and ws[0]["text"].isdigit()
                      and ws[0]["size"]<ws[1]["size"] and ws[0]["bottom"]<ws[1]["bottom"])
            if (raised and ln["size"]>=min(body-.8,.92*body) and ln["size"]<=body+.5
                    and ln["top"]>.6*p["h"] and word_count(ln["text"])>=6
                    and not ln.get("tab") and not ln.get("graphic")):
                ln["footnote"] = True
                active = ln
                # Author/contact notes can precede the numbered disclaimer.
                # Associate only a contiguous italic contact group, not prose.
                contact, reach = [], ln["top"]
                for previous in reversed(p["lines"][:index]):
                    if (previous["top"]<=.6*p["h"] or previous.get("italic",0)<.85
                            or not 0<=reach-previous["bottom"]<=body
                            or abs(previous["size"]-ln["size"])>.5):
                        break
                    contact.append(previous)
                    reach = previous["top"]
                if any("@" in l["text"] for l in contact):
                    for l in contact:
                        l["footnote"] = True
            elif (active and (ln.get("words") or [{}])[-1].get("font")== (active.get("words") or [{}])[-1].get("font")
                  and abs(ln["size"]-active["size"])<=.5
                  and 0<=ln["top"]-active["bottom"]<=body):
                ln["footnote"] = True
                active = ln
            else:
                active = None


def mark_roman_sections(pages, body):
    for p in pages:
        lines = p["lines"]
        for i,line in enumerate(lines[:-1]):
            following = lines[i+1]
            previous = lines[i-1] if i else None
            if (re.fullmatch(r"[IVXLCDM]+",line["text"])
                    and line.get("italic",0) < .5 and not any(w.get("symbolic") for w in line.get("words",[]))
                    and .15*p["h"] <= line["top"] < .85*p["h"]
                    and abs(line["x0"]+line["x1"]-p["w"]) <= 2*body
                    and abs(line["size"]-body) <= max(1,.15*body)
                    and previous and line["top"]-previous["bottom"] > .45*body
                    and word_count(following["text"]) >= 6 and not starts_lower(following["text"])
                    and not any(following.get(k) for k in ("tab","graphic","byline"))):
                line["roman_section"], line["force_heading"] = True, True


def repair_ocr_linebreaks(pages):
    """Join only OCR line-edge fragments attested as a closed word elsewhere.

    Never use absence alone as spelling evidence: two real words can both be
    rare. This is the document-vocabulary evidence used by resolve_hyphens.
    """
    words = Counter(w.lower() for p in pages for l in p["lines"] for w in re.findall(r"[A-Za-z]+",l["text"]))
    streams = []
    for p in pages:
        groups = defaultdict(list)
        for l in p["lines"]:
            groups[(l["band"],l["col"])].append(l)
        streams.extend(groups.values())
    edges = Counter()
    for ls in streams:
        for a,b in zip(ls,ls[1:]):
            left=re.search(r"([a-z]+)$",a["text"])
            right=re.match(r"([a-z]+)\b",b["text"])
            if left and right:
                edges[left.group(1)] += 1
                edges[right.group(1)] += 1
    for ls in streams:
        for a,b in zip(ls,ls[1:]):
            left=re.search(r"([a-z]+)$",a["text"])
            right=re.match(r"([a-z]+)\b",b["text"])
            if (a.get("ocr_layer") and b.get("ocr_layer") and left and right
                    and left.group(1) not in SMALL_WORDS | STOP_END
                    and a.get("font")==b.get("font") and abs(a["size"]-b["size"])<=.5
                    and 0<=b["top"]-a["bottom"]<=a["size"]
                    and (words[left.group(1)+right.group(1)]
                         or right.group(1).endswith("s") and words[(left.group(1)+right.group(1))[:-1]])
                    and not (words[left.group(1)]>edges[left.group(1)] and words[right.group(1)]>edges[right.group(1)])):
                a["ocr_join_next"]=True


def mark_numeric_regions(lines, body):
    """Borderless tables: repeated numeric alignments, snapped at the page's word-gap scale.

    Like pdfplumber's text strategy, use either left or right word edges. Requiring
    multiple numeric columns across three rows keeps prose lists out of tables.
    """
    gaps = [w.get("word_gap", 0.15) * w["size"] for l in lines for w in l.get("words", [])]
    tolerance = statistics.median(gaps) if gaps else 0.15 * body
    candidates = []
    for l in lines:
        ws = l.get("words", [])
        nums = [w for w in ws if re.search(r"\d", w["text"])]
        if len(nums) >= 2 and len(nums) >= len(ws) / 2:
            candidates.append((l, nums))
    hits = set()
    for l, nums in candidates:
        matched = 0
        for w in nums:
            peers = {id(r) for r, ns in candidates if abs(r["top"] - l["top"]) <= 6 * body
                     and any(min(abs(v["x0"] - w["x0"]), abs(v["x1"] - w["x1"])) <= tolerance for v in ns)}
            matched += len(peers) >= 3
        if matched >= 2:
            hits.add(id(l))
    runs, run = [], []
    for l in sorted(lines, key=lambda l: l["top"]):
        if id(l) in hits:
            if run and l["top"] - run[-1]["bottom"] > 2 * body:
                runs.append(run); run = []
            run.append(l)
    if run:
        runs.append(run)
    captions = [l for l in lines if re.match(r"^table\s*\d", l["text"], re.I)]
    for run in runs:
        top, bottom = run[0]["top"], run[-1]["bottom"]
        left, right = min(l["x0"] for l in run) - body, max(l["x1"] for l in run) + body
        # Column labels can be text-only. Include adjacent, spatially separated
        # cells above the numeric rows, without sweeping in a prose lead-in.
        headers = [l for l in lines if 0 <= top - l["bottom"] <= 2 * body
                   and left <= (l["x0"] + l["x1"]) / 2 <= right
                   and not end_terminal(l["text"])
                   and any(b["x0"] - a["x1"] >= body for a, b in zip(l.get("words", []), l.get("words", [])[1:]))]
        if headers:
            top = min(l["top"] for l in headers)
        above = [l for l in captions if l["bottom"] <= top and top - l["bottom"] <= 6 * body]
        if above:
            top = max(above, key=lambda l: l["top"])["bottom"]
        for l in lines:
            if top <= l["top"] <= bottom and left <= (l["x0"] + l["x1"]) / 2 <= right and not CAPTION_RE.match(l["text"]):
                l["tab"] = True
                l.pop("list_start", None)


def mark_graphic_labels(lines, body):
    """A caption can delimit sparse chart lettering even on a page-sized scan."""
    ordered = sorted(lines, key=lambda l: l["top"])
    for i, caption in enumerate(ordered):
        if not (re.match(r"^fig(?:ure)?\.?\s*\d", caption["text"], re.I)
                and (CAPTION_RE.match(caption["text"]) or CAPTION_TITLE_RE.match(caption["text"]))):
            continue
        j = i - 1
        while j >= 0 and word_count(ordered[j]["text"]) < 10 and not end_terminal(ordered[j]["text"]):
            if ordered[j].get("tab"):
                break
            if j == 0 or ordered[j]["top"] - ordered[j - 1]["bottom"] > 2 * body:
                if caption["top"] - ordered[i - 1]["bottom"] <= 2 * body:
                    for ln in ordered[j:i]:
                        ln["graphic"] = True
                break
            j -= 1


# ---------- Text-layer coverage ----------


def scan_page_numbers(pdf, pnos, text_counts=None):
    """Identify low-text pages with a central page-sized raster.

    Keep blank versos and sparse vector pages out of the scan list. A logo or
    small illustration does not span both page midlines.
    """
    counts = {} if text_counts is None else text_counts
    for p in pnos:
        counts[p] = sum(len(w["text"]) for w in get_words(pdf.pages[p - 1]))
    out = []
    for p in pnos:
        page = pdf.pages[p - 1]
        if counts[p] >= 30:
            continue
        if not hasattr(page, "images"):
            out.append(p)  # unknown raster coverage: conservatively treat it as a scan
            continue
        ox, oy = page.bbox[:2]
        if any(i["x0"] <= ox + page.width / 4 and i["x1"] >= ox + 3 * page.width / 4
               and i["top"] <= oy + page.height / 4 and i["bottom"] >= oy + 3 * page.height / 4
               for i in getattr(page, "images", [])):
            out.append(p)
    return out


SCAN_ONLY_MESSAGE = "给执行的 agent（不是给用户的）：基础版无法读取扫描 PDF。已安装 MinerU 时请用 --engine mineru 重试；否则按 SKILL.md 第 0 步向用户提供 MinerU 选项，用户同意后由 agent 安装。"


def basic_text_pages(pdf, pnos):
    """Keep readable and blank pages; report scans once, or stop a scan-only run."""
    counts = {}
    scans = scan_page_numbers(pdf, pnos, counts)
    if not any(n >= 30 for n in counts.values()):
        sys.exit(SCAN_ONLY_MESSAGE)
    messages = ([f"给执行的 agent（不是给用户的）：已跳过扫描页 {scans}；这些页是扫描件，MinerU 可以读取。"]
                if scans else [])
    return [p for p in pnos if p not in scans], messages


def is_heading_block(b, body):
    if b.get("runin_para"):
        return False
    b = dict(b, size=round(b["size"]*2)/2)  # match the precision of the body-size estimate
    body = max(body,b.get("local_body") or body)
    t = b["text"]
    if (b["size"] <= body + 0.5 and b["bold"] < 0.85
            and re.match(r"^[A-Za-z]\s*\d+\s*:\s+", unicodedata.normalize("NFKC",t))):
        return False  # a variable-labelled statement is prose without heading typography
    if (b.get("heading_boundary") is False and b["size"] < body + 1.0 and b["bold"] < 0.85
            and not KNOWN_HEAD_RE.fullmatch(t.strip()) and not b.get("runin")):
        return False
    if re.search(r"https?://|www\.", t, re.I):
        return False
    if b.get("force_heading") or READING_RE.fullmatch(t.strip()):
        return True
    if b["n_lines"] > 3 or len(t) > 160:
        return False
    words = word_count(t)
    if words > 20:
        return False
    numbered = NUM_HEAD_RE.match(t)
    if re.match(r"^(?:19|20)\d{2}\s", t):
        numbered = None  # a citation year is not section numbering
        if b["bold"] < 0.85 and b["size"] < body + 2.5:
            return False  # OCR size jitter alone cannot promote a year-led body line
    run_in = t.endswith(".") and words <= 8 and b["bold"] >= 0.85  # 单独成行的粗体小标题，如 "Type specialization."
    question = t.endswith("?") and words <= (20 if numbered else 12) and (b["size"] >= body + 1.0 or b["bold"] >= 0.85)  # a heading that asks
    if t.rstrip().endswith((",", ";")):
        return False  # a line that stops at a comma is the start of a sentence, whatever its number or size
    if end_terminal(t) and not (numbered and words <= 12) and not run_in and not question:
        return False
    label = NUM_PREFIX_RE.sub("", t)
    letters = sum(1 for c in label if c.isalpha() or is_cjk(c))
    if KNOWN_HEAD_RE.fullmatch(t.strip()) and b["n_lines"] == 1:
        return True
    if letters < 3 or letters / max(1, len(label.replace(" ", ""))) < 0.6:
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
    cover_titles = info.get(first_page,{}).get("cover_titles",[])
    repeated = [b for b in blocks if b["page"] == first_page and b["n_lines"] <= 3
                and word_count(b["text"]) >= 3 and any(block_title_key(b) == title_key(t) for t in cover_titles)]
    if repeated:
        named = max(repeated,key=lambda b:len(b["text"]))
        for b in blocks:
            if b["page"] == first_page:
                b["article_title"] = b is named
                if b is named:
                    b["subtitle"] = False
                    b["front_meta"] = False
                elif b["bottom"] <= named["top"] and b["size"] > named["size"] and b["n_lines"] <= 3:
                    b["front_meta"] = True  # session/section label above a named article
    article_title = next((b for b in blocks if b.get("article_title")), None)
    if article_title:
        first_page = article_title["page"]
    if not article_title or any(b["page"] < first_page for b in blocks):
        cover_pages = sorted({b["page"] for b in blocks})[:3]
        for pg in cover_pages[1:]:
            candidates = [b for b in blocks if b["page"] == pg and b["size"] >= body-.5
                          and (b["bold"] >= 0.85 or b["size"] >= body + .5 or b["text"].isupper()) and 3 <= word_count(b["text"]) <= 30
                          and not re.search(r"https?://|www\.",b["text"],re.I)]
            found = next((b for b in candidates if any(
                old["page"] < pg and block_title_key(b) == block_title_key(old)
                for old in blocks)),None)
            if found:
                prior = [b for b in blocks if b["page"] < pg]
                cover_only = not any(b["n_lines"] >= 3 and b["size"] <= body + 1
                                     and word_count(b["text"]) > 20 for b in prior)
                if cover_only or any(re.search(r"\bcitation\b|\brepository\b|\bpublished version\b|\bterms (?:of use|& conditions)\b|\baccessed\b|\bstable url\b|\bto cite this article\b",b["text"],re.I) for b in prior):
                    first_page = pg
                    found["article_title"] = True
                    article_title = found
                    info[pg]["cover_titles"] = [block_title_text(found)]
                    for old in prior:
                        old["front_meta"] = True
                        old["type"] = "frag"
                        old["cover_sheet"] = True
                    break
    blocks[:] = [b for b in blocks if not b.get("cover_sheet")]
    if article_title and info[first_page].get("cover_titles"):
        article_title["subtitle"] = False
        for b in blocks:
            if (b["page"] == first_page and b["bottom"] <= article_title["top"]
                    and b["size"] > article_title["size"] and b["n_lines"] <= 3):
                b["front_meta"] = True
    title_done = False
    tol = max(1.0, 0.15 * body)
    # the title is the largest type at the top of the first page, not a smaller label above it ("Essay", "Open access")
    # a masthead (journal name, then a "Vol. / Issue" line) is never the title, however large its type
    first = [b for b in blocks if b["page"] == first_page]
    abstract_open = False
    for b in first:
        if re.match(r"^abstract\b",b["text"],re.I):
            abstract_open = True
        elif re.match(r"^(?:key\s*words?|JEL\b|creative commons|licen[cs]e)\b",b["text"],re.I) or NUM_HEAD_RE.match(b["text"]):
            abstract_open = False
        if abstract_open and not re.fullmatch(r"abstract",b["text"].strip(),re.I):
            b["abstract"] = True
    # Header roles precede footnote inference. Editorial dates and wrapped
    # keyword/licence records do not become notes because the header uses small
    # type. GROBID likewise separates the header before full-text labelling.
    for i,b in enumerate(first):
        t = b["text"]
        label = FRONT_META_LABEL_RE.match(t)
        if label:
            b["front_meta"] = True
            for o in first[i+1:]:
                if (o["top"] < b["bottom"] or o["top"]-b["bottom"] > b["size"]
                        or o.get("font") != b.get("end_font",b.get("font"))
                        or abs(o["size"]-b["size"])>.5 or is_heading_block(o,body)
                        or end_terminal(b["text"])):
                    break
                o["front_meta"] = True
                b = o
    metadata = re.compile(r"https?://|www\.|\bdoi\s*[:/]|\bISSN\b", re.I)
    mast = [k for k, b in enumerate(first[:8]) if b["top"] < .45*info[b["page"]]["h"] and len(b["text"]) < 160 and (
        MASTHEAD_RE.search(b["text"]) or (
            metadata.search(b["text"]) and b["top"] < 0.45 * info[b["page"]]["h"]
            and any(o["top"] >= b["bottom"] and o["size"] > b["size"]
                    and o["top"] < 0.45 * info[o["page"]]["h"]
                    and o["size"] >= body + 2.5 and len(o["text"]) < 250
                    and o["n_lines"] <= 3 for o in first[k + 1:])))]
    for b in first[:mast[-1] + 1 if mast else 0]:
        b["_mast"] = True
    cands = [b["size"] for b in first if b["size"] >= body + 2.5 and not b.get("_mast") and not metadata.search(b["text"])
             and not (CAPTION_RE.match(b["text"]) or CAPTION_TITLE_RE.match(b["text"]))
             and b["top"] < 0.45 * info[b["page"]]["h"] and len(b["text"]) < 250]
    title_size = max(cands) if cands else 0.0
    title_block = article_title
    if not cands and title_block is None:  # a title set no larger than the text (small capitals): the first heading-like block under the masthead
        title_block = next((b for b in first if not b.get("_mast") and b["top"] < 0.45 * info[b["page"]]["h"]
                            and b["n_lines"] <= 3 and word_count(b["text"]) >= 3 and is_heading_block(b, body)
                            and not (CAPTION_RE.match(b["text"]) or CAPTION_TITLE_RE.match(b["text"]))
                            and not KNOWN_HEAD_RE.match(NUM_PREFIX_RE.sub("", b["text"]).strip())
                            and not re.match(r"^(\d+(\.\d+)*|[IVXLC]+)[.)]?\s", b["text"])), None)
    opening_title = title_block or next((b for b in first if b["size"]==title_size and not b.get("_mast")),None)
    if opening_title:
        prior = [b for b in first if b["bottom"]<=opening_title["top"] and not b.get("_mast")]
        for names, affiliation in zip(prior,prior[1:]):
            words = re.findall(r"[A-Za-z]+",names["text"])
            if (2<=len(words)<=12 and all(w[:1].isupper() or w.lower() in SMALL_WORDS for w in words)
                    and not end_terminal(names["text"]) and not metadata.search(names["text"])
                    and re.search(r"\b(?:university|department|institute|faculty)\b|[\w.+-]+@[\w.-]+",affiliation["text"],re.I)
                    and 0<=affiliation["top"]-names["bottom"]<=2*names["size"]):
                names["byline"] = affiliation["byline"] = True
    lowest = defaultdict(float)  # 每页每栏正文的最低位置；脚注在它下面
    last_body = defaultdict(float)
    for b in blocks:
        if abs(b["size"] - body) <= tol and len(b["text"]) > 80:
            k = (b["page"], b.get("key"))
            lowest[k] = max(lowest[k], b["bottom"])
            if b["size"] > min(body - 0.8, 0.92 * body):
                last_body[k] = max(last_body[k], b["bottom"])
    for b in blocks:
        t0 = b["text"]
        small = b["size"] <= min(body - 0.8, 0.92 * body)
        below = b["top"] >= lowest[(b["page"], b.get("key"))] - 1
        h0 = info[b["page"]]["h"]
        ref_head = len(t0) < 40 and REF_RE.match(NUM_PREFIX_RE.sub("", t0).strip().rstrip(":：").strip())
        gap = b.get("line_gap") or 0.25 * body
        end_body = last_body[(b["page"], b.get("key"))]
        unmarked_foot = (end_body > 0 and b["top"] > 0.6 * h0
                         and b["top"] - end_body > gap + max(0.45 * body, 2.5)
                         and not any(o["page"] == b["page"] and o.get("key") == b.get("key")
                                     and end_body <= o["top"] < b["top"] and is_heading_block(o, body) for o in blocks))
        previous = next((o for o in reversed(blocks[:blocks.index(b)]) if o["page"]==b["page"]
                         and o.get("key")==b.get("key")),None)
        quotation = (previous and previous["text"].rstrip().endswith(":" ) and b["n_lines"]>=2
                     and b["x0"]>previous["x0"]+.8*body and not NOTE_MARK_RE.match(t0)
                     and b["size"] >= .85*body)
        b["quotation"] = bool(quotation)
        b["_note"] = not quotation and (small or b.get("footnote")) and not b.get("abstract") and (not b.get("inline_math_prose") or FOOT_MARK_RE.match(t0)) and not b.get("front_meta") and not b.get("independent_text") and not b.get("text_box") and not ref_head and not re.fullmatch(r"abstract",t0.strip(),re.I) and not CAPTION_RE.match(t0) and (
            below or unmarked_foot or b.get("footnote") or (NOTE_MARK_RE.match(t0) and b["top"] > 0.6 * h0))
    for bi, b in enumerate(blocks):
        t = b["text"]
        h = info[b["page"]]["h"]
        previous = blocks[bi - 1] if bi else None
        front_end = min((o["top"] for o in first if KNOWN_HEAD_RE.fullmatch(NUM_PREFIX_RE.sub("",o["text"]).strip().rstrip(":"))), default=0)
        if (b["page"] == first_page and b["top"] < min((o["top"] for o in first if NUM_HEAD_RE.match(o["text"]) and o["size"]>=body-.5),default=front_end)
                and re.match(r"^(?:JEL\s+(?:codes?|classification)|key\s*words?)\b", t, re.I)):
            b["front_meta"] = True
        letters = sum(1 for ch in t if ch.isalpha() or is_cjk(ch)) / max(1, len(t))
        identity_words = re.findall(r"[A-Za-z]+",re.sub(r"https?://\S+", "",t))
        identifier_meta = (bool(re.search(r"\b\d{4}-\d{4}-\d{4}-[\dX]{4}\b",t))
                           and bool(identity_words)
                           and all(w[:1].isupper() or w.lower() in SMALL_WORDS for w in identity_words))
        # A DOI following the author's contact note belongs to that note group,
        # rather than to a journal's freestanding bibliographic footer.
        contact_note = b.get("_note") and any(
            o["page"] == b["page"] and o.get("key") == b.get("key")
            and o["bottom"] <= b["top"] and (o.get("_note") or o.get("type") == "note")
            and re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", o["text"])
            for o in blocks)
        copyright_footer = ((b["top"] > 0.6 * h or b["page"] == first_page) and b["size"] < body and (
            (re.match(r"^\s*(?:©|copyright\s*(?:©|\(c\)|\d{4}))", t, re.I)
             or len(t) < 160 and b["n_lines"] <= 2 and not end_terminal(t)
             and re.search(r"©|\bcopyright\b", t, re.I))
            or (b["page"] == first_page and (re.search(r"\blicen[cs]e\b|\blicen[cs]ed\b|\ball rights reserved\b",t,re.I)
                or re.search(r"\b(?:19|20)\d{2}\s*;\s*\d+\s*:\s*\d+",t)
                or re.match(r"^(?:doi|ISSN)\s*[:/]",t,re.I) and not contact_note
                or re.match(r"^\d{4}-\d{3}[\dX]\s*©",t)
                or b["top"] < front_end and len(t) < 160 and not end_terminal(t) and re.search(r"\b(?:19|20)\d{2}\b",t)
                or re.match(r"^(?:published|printed|distributed)\s+by\b",t,re.I)
                or re.fullmatch(r"(?:https?://|www\.)?[\w.-]+\.[A-Za-z]{2,}(?:/\S*)?\s*[|–—-]?\s*\d+",t,re.I)))))
        if b.get("byline"):
            b["type"] = "frag"
        elif b.get("subtitle"):
            b["type"] = "para"
        elif b.get("front_meta") or b.get("contents_page") or b.get("graphic") or b.get("pull") or copyright_footer or identifier_meta:
            b["type"] = "frag"
            if copyright_footer:
                b["front_meta"] = True
        elif b.get("abstract"):
            b["type"] = "para"
            b["abstract_label"] = t.strip().rstrip(".:").casefold() == "abstract"
        elif b.get("roman_section"):
            b["type"], b["level"] = "heading", 1
        elif b.get("toc"):
            b["type"] = "para"
        elif b.get("list") and not b.get("_note") and not b.get("tab"):
            b["type"] = "para"
        elif b.get("sidebar"):
            b["type"] = "frag"
        elif b.get("display_region"):
            b["type"], b["equation"] = "frag", True
            # New crop evidence must not broaden the established colon/display
            # continuation rule. Preserve the former typography evidence for it.
            b["join_equation"] = bool(b.get("math_style") or (b["n_lines"] <= 2 and symbolic_display(t)))
        elif (b.get("tab") and b.get("aside") and b.get("_note")
              and letters > 0.5 and end_terminal(t) and not TABLE_NOTE_RE.match(t)):
            # Complete explanatory sentences at the page foot remain readable
            # notes, even when a broad table region includes their baselines.
            b["type"], b["table_prose_note"] = "note", True
        elif b.get("tab") and not b.get("caption_candidate") and not CAPTION_RE.match(t):
            b["type"], b["table"] = "frag", True
        elif TABLE_NOTE_RE.match(t) and b["top"] > 0.1 * h:  # "Notes: ..." under a table or figure
            b["type"], b["table"] = "frag", True
        elif b.get("_mast"):
            b["type"] = "frag"
        elif not title_done and b["page"] == first_page and (b is title_block or (
                b["size"] >= body + 2.5 and b["size"] >= title_size - 0.5 and not metadata.search(t) and b["top"] < 0.45 * h and len(t) < 250)):
            b["type"], b["level"], title_done = "heading", 0, True
            b["text"] = re.sub(r"\s*[*†‡§¶]+$", "", b.get("title_text", t))  # the footnote mark after a title is not part of it
            suffix = b.get("title_suffix")
            if suffix and b["text"].endswith(suffix):
                b["text"] = b["text"][:-len(suffix)].rstrip()
            for o in blocks:  # a journal line above the title (name, volume, DOI) is not part of the reading
                if o is b:
                    break
                if o["page"] == first_page and o["type"] in ("para", "note", "heading") and o.get("level") != 0 and not o.get("byline"):
                    o["type"] = "frag"
        elif b.get("caption_candidate") if b.get("caption_candidate") is not None else (CAPTION_RE.match(t) or (CAPTION_TITLE_RE.match(t) and word_count(t) <= 25)):
            b["type"] = "caption"
        elif b.pop("_note", False) or (re.match(r"^[*■]\s", t) and b["top"] > 0.55 * h and len(t) < 700):
            b["type"] = "note"
        elif (b.get("math_style") or (b["n_lines"] <= 2 and symbolic_display(t))) and not b.get("table"):
            b["type"], b["equation"] = "frag", True
        elif b.get("mono", 0) >= 0.6:
            b["type"] = "frag"  # 代码清单
        elif b.get("page_top_continuation") or b.get("runin_para") or b.get("quotation") or b.get("inline_math_prose") or bracket_wrap(previous, b):
            b["type"] = "para"
        elif b.get("cell_sentence"):
            b["type"] = "para"
        elif is_heading_block(b, body):
            if (b.get("graphic_label") and b["size"]<body-0.5 and not NUM_HEAD_RE.match(t)
                    and not KNOWN_HEAD_RE.fullmatch(t.strip().rstrip(":"))):
                b["type"],b["graphic"]="frag",True
            else:
                b["type"] = "heading"
        elif b.get("text_box") and letters > 0.5:
            b["type"] = "para"
        elif (word_count(t) < 6 and not end_terminal(t)) or (letters < 0.5 and len(t) < 160) \
                or (b["size"] <= body - 2.5 and b["n_lines"] <= 3):  # small type set into the text: an equation annotation
            b["type"] = "frag"
        else:
            b["type"] = "para"
    page_caption = {}
    for i,b in enumerate(blocks):
        if b.get("type")=="caption":
            page_caption[b["page"]]=b["text"]
        previous = blocks[i-1] if i else None
        if (b.get("type")=="note" and previous and previous.get("table")
                and re.match(r"^(?:table|tab\.|exhibit)\s",page_caption.get(b["page"],""),re.I)
                and b["page"]==previous["page"] and b.get("key")==previous.get("key")
                and b["size"]<=min(body-.8,.92*body) and not FOOT_MARK_RE.match(b["text"])
                and not b.get("footnote") and 0<=b["top"]-previous["bottom"]<=2*body):
            b["type"],b["table"],b["table_note"]="frag",True,True
        if re.match(r"^notes?\s+\S",b["text"],re.I) and b["size"]<body:
            previous=blocks[i-1] if i else None
            if (previous and previous["page"]==b["page"] and (previous.get("table") or previous.get("tab") or previous.get("graphic"))
                    and 0<=b["top"]-previous["bottom"]<=2*body):
                b["type"],b["table"]="frag",True
        previous = blocks[i-1] if i else None
        if b.get("table") and re.match(r"^notes?\b", b["text"], re.I):
            b["table_note"] = True
        elif (previous and previous.get("table_note") and b["page"] == previous["page"]
              and b.get("key") == previous.get("key") and b.get("font") == previous.get("font")
              and b["size"] < body - 0.5 and abs(b["x0"] - previous["x0"]) <= 0.5 * body
              and not end_terminal(previous["text"]) and continuation_gap(previous, b)):
            b["type"], b["table"], b["table_note"] = "frag", True, True
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
        if b["type"] in ("note", "para", "heading", "frag") and not b.get("abstract") and not b.get("table_prose_note") and b.get("level") != 0 and b["size"] <= body - 0.5:
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
            captioned_table = (i > 0 and blocks[i-1]["type"] == "caption"
                               and re.match(r"^(?:table|tab\.)\s",blocks[i-1]["text"],re.I)
                               and aligned_cells(run))
            if captioned_table:
                # Numbered table columns such as (1), (2), (3) are not equation
                # numbers. Keep the aligned rows in one table crop, including
                # rows that used to be protected accidentally as contents text.
                for b in run:
                    b["type"], b["table"] = "frag", True
                    b.pop("equation",None)
                    b.pop("display_region",None)
            elif any(EQ_NUMBER_RE.search(b["text"]) for b in run) or (
                    numeric < len(run) / 2 and any(EQUATION_RE.search(b["text"]) for b in run)):
                # a display equation set over several short lines (fraction parts, the equation, its number)
                for b in run:
                    if b["type"] == "para" and word_count(b["text"]) < 6 and not end_terminal(b["text"]):
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
    join_wrapped_blocks(blocks, body)
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
        candidates = [b for b in blocks if b is not title and b["page"] == first_page and b["top"] >= title["bottom"]-.15*title["size"]]
        for b in sorted(candidates,key=lambda b:b["top"]):
            if ((b.get("font") != title.get("font") and not b.get("article_title")) or b["size"] < title["size"] - max(1,0.15*title["size"])
                    or b["top"]-title["bottom"] > title["size"] or b["n_lines"] > 3 or b.get("subtitle") or b.get("byline")
                    or KNOWN_HEAD_RE.fullmatch(b["text"]) or end_terminal(b["text"])):
                break
            title["text"] = join_marked(title["text"], b["text"])
            title["bottom"]=b["bottom"];title["x0"]=min(title["x0"],b["x0"]);title["x1"]=max(title["x1"],b["x1"])
            b["title_piece"]=True
        blocks[:] = [b for b in blocks if not b.get("title_piece")]
    if title:
        after = sorted((b for b in blocks if b["page"] == first_page and b["top"] >= title["bottom"]), key=lambda b: b["top"])
        reach, previous_size = title["bottom"], title["size"]
        name_size, previous_byline = None, None
        for index,b in enumerate(after):
            if b.get("subtitle") or b.get("byline"):
                reach, previous_size = max(reach,b["bottom"]), b["size"]
                continue
            if (b["size"] >= title["size"] - 0.5 and b["n_lines"] <= 3
                    and b["top"] - reach <= title["size"]):
                reach, previous_size = max(reach, b["bottom"]), b["size"]
                continue  # a subtitle belongs to the title region, not the byline
            marked = bool(re.search(r"[†‡∗*]", b["text"]))
            names = [w for w in re.findall(r"[^\W\d_]+", b["text"], re.UNICODE) if len(w) > 1 and w.lower() not in SMALL_WORDS]
            affiliation = (previous_byline is not None and name_size is not None
                           and b["size"] < min(body,name_size-.5)
                           and 0 <= b["top"]-reach <= 2*previous_size
                           and b["x0"] < previous_byline["x1"] and b["x1"] > previous_byline["x0"]
                           and not re.search(r"[a-z][.!?]\s+[A-Z][a-z]",b["text"]))
            following = after[index+1] if index+1 < len(after) else None
            affiliation_follows = (following is not None and following["size"] < b["size"]-.5
                                   and 0 <= following["top"]-b["bottom"] <= 2*b["size"]
                                   and following["x0"] < b["x1"] and following["x1"] > b["x0"]
                                   and not KNOWN_HEAD_RE.fullmatch(following["text"]))
            stacked_names = b["n_lines"] <= 3 and word_count(b["text"]) <= 12
            if (b["n_lines"] > 2 and not affiliation and not stacked_names or len(names) < 2
                    or (sum(w[0].isupper() for w in names) < 0.8 * len(names) and not affiliation)
                    or (end_terminal(b["text"]) and not any(x.get("byline") for x in after)
                         and not affiliation_follows)
                    or (NUM_HEAD_RE.match(b["text"]) and not marked and not re.match(r"^\d{1,2}\s+[A-Z]",b["text"]))
                    or re.search(r"©|\bcopyright\b|\b(?:19|20)\d{2}\b", b["text"], re.I)
                    or KNOWN_HEAD_RE.fullmatch(b["text"])):
                break
            b["type"], b["byline"] = "frag", True
            if name_size is None:
                name_size = b["size"]
            previous_byline = b
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
    # In raster-backed text, size and proxy font family are recognition
    # estimates. Weight, slant and alignment supply independent style evidence.
    # When sections are explicitly numbered, keep that hierarchy's existing
    # style ranks; a shared body-size subheading style cannot outrank it.
    style_only = not any(NUM_HEAD_RE.match(b["text"]) for b in heads)
    ocr_styles = defaultdict(list)
    for b in heads:
        if style_only and b.get("ocr_layer") and not NUM_HEAD_RE.match(b["text"]):
            centred = abs(b["x0"]+b["x1"]-b["pw"]) <= 2*b["size"]
            ocr_styles[(b["bold"] >= .85, b.get("italic",0) >= .85, centred)].append(b)
    for group in ocr_styles.values():
        bands = []
        for b in sorted(group,key=lambda b:b["size"],reverse=True):
            # Reuse the size neighbourhood used for baseline peers, rather
            # than collapsing genuinely different display-size style bands.
            if not bands or b["size"] < .8*bands[-1][0]["size"]:
                bands.append([])
            bands[-1].append(b)
        for band in bands:
            ranks = [rank.get(round(b["size"],1),0)+1 for b in band]
            for b in band:
                b["style_level"] = min(ranks)
    for b in heads:
        m = NUM_HEAD_RE.match(b["text"])
        if b.get("roman_section"):
            b["level"] = 1
        elif m and re.match(r"^\d", b["text"]):
            b["level"] = min(4, m.group(1).count(".") + 1)
        elif deepest == 0:
            b["level"] = min(3, b.get("style_level", rank.get(round(b["size"], 1), 0) + 1))
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
        # Contact material is a local block group, never a property of its
        # whole page: a bibliography commonly ends above this footer.
        anchors = [b for b in tail if re.match(r"^(?:author\s+contact|contact(?:\s+(?:details|information))?|suggested\s+citation)\b", b["text"].lstrip("_ "), re.I)]
        if anchors:
            start = min(b["top"] for b in anchors)
            for b in tail:
                if b["top"] >= start:
                    b["backmatter"], b["contact_footer"], b["type"] = True, True, "frag"
        elif not any(reference_entry_evidence(b["text"]) for b in tail):
            for b in tail:
                b["backmatter"], b["type"] = True, "para"
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


def combine_caption_groups(blocks):
    """A caption beside a table is one text region, before cell-column ordering."""
    groups = defaultdict(list)
    for b in blocks:
        if b.get("caption_group") is not None:
            groups[(b["page"],tuple(b["caption_group"]))].append(b)
    out, used = [], set()
    for b in blocks:
        if b.get("caption_group") is None:
            out.append(b)
            continue
        key = (b["page"],tuple(b["caption_group"]))
        if key in used:
            continue
        used.add(key)
        pieces = sorted(groups[key],key=lambda x:(x["top"],x["x0"]))
        a = dict(pieces[0], caption_candidate=True, force_heading=False)
        for tail in pieces[1:]:
            a["text"] = join_marked(a["text"],tail["text"])
            a["x0"],a["x1"] = min(a["x0"],tail["x0"]),max(a["x1"],tail["x1"])
            a["bottom"] = max(a["bottom"],tail["bottom"])
            a["n_lines"] += tail["n_lines"]
            a["end_font"] = tail.get("end_font",tail.get("font"))
            a["fonts"] = sorted(set(a.get("fonts",[])) | set(tail.get("fonts",[])))
            a["last_x1"] = tail.get("last_x1", tail["x1"])
            a.setdefault("superscripts",[]).extend(tail.get("superscripts",[]))
            retain_unmapped(a,tail)
        out.append(a)
        if (len(out)>1 and out[-2].get("caption_group") is not None
                and out[-2]["page"]==a["page"] and out[-2]["x0"]>a["x1"]
                and min(out[-2]["bottom"],a["bottom"])>max(out[-2]["top"],a["top"])):
            out[-2:]=[a,out[-2]]  # simultaneous caption columns read left to right
    return out


def join_wrapped_blocks(blocks, body):
    """Keep same-style heading/caption continuations regardless of initial case."""
    out = []
    for b in blocks:
        a = out[-1] if out else None
        if (a and a["type"] in ("heading", "caption") and a.get("level") != 0
                and (a["type"] == "caption" or not KNOWN_HEAD_RE.fullmatch(NUM_PREFIX_RE.sub("",a["text"]).strip().rstrip(":")))
                and (a["type"] == "caption" or a["size"] > body + 0.5 or a.get("bold",0) >= 0.85 or a.get("body_font") is False)
                and a["page"] == b["page"] and not b.get("table") and not b.get("tab")
                and not b.get("graphic") and not b.get("display_region")
                and not CAPTION_RE.match(b["text"]) and not CAPTION_TITLE_RE.match(b["text"])
                and not NUM_HEAD_RE.match(b["text"]) and not KNOWN_HEAD_RE.fullmatch(b["text"].strip())
                and (a["type"] == "caption" or a.get("font") == b.get("font"))
                and (a["type"] != "heading" or (a.get("font") == b.get("font") and not b.get("runin_para")
                     and (b["size"] > body+.5 or b.get("bold",0) >= .85 or b.get("italic",0) >= .85 or b.get("body_font") is False)))
                and (a["type"] != "caption" or caption_wrap(a,b))
                and abs(a["size"]-b["size"]) <= 0.5 and continuation_gap(a,b)
                and b["top"] >= a["bottom"]
                and (not end_terminal(a["text"]) or a["type"] == "caption")
                and any(abs(b["x0"]-x) <= max(1,0.15*body)
                        for x in (a["x0"], a.get("lead_text_x0")) if x is not None)):
            a["text"] = join_marked(a["text"], b["text"])
            a["bottom"], a["x1"] = b["bottom"], max(a["x1"], b["x1"])
            a["n_lines"] += b["n_lines"]
            a["end_font"] = b.get("end_font", b.get("font"))
            a["fonts"] = sorted(set(a.get("fonts",[])) | set(b.get("fonts",[])))
            a["last_x1"] = b.get("last_x1", b["x1"])
            a.setdefault("superscripts", []).extend(b.get("superscripts", []))
            retain_unmapped(a,b)
        else:
            out.append(b)
    blocks[:] = out


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
        if j - i >= 2 and any(b.get("math_style") or b.get("display_region") for b in blocks[i:j]):
            run = blocks[i:j]
            display = dict(run[0], type="frag", equation=True,
                           join_equation=any(b.get("math_style") or b.get("join_equation", b.get("equation", False)) for b in run),
                           display_region=any(b.get("display_region") for b in run),
                           text="\n".join(b["text"] for b in run),
                           n_lines=sum(b["n_lines"] for b in run),
                           x0=min(b["x0"] for b in run), x1=max(b["x1"] for b in run),
                           top=min(b["top"] for b in run), bottom=max(b["bottom"] for b in run))
            retain_unmapped(display, *run)
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


def reference_entry_evidence(text):
    """Author/year evidence within a bibliography, including full given names."""
    author = REF_ENTRY_RE.match(text) or re.match(r"^\W{0,2}[A-Z][\w’'-]+,\s+[A-Z]", text)
    numbered = re.match(r"^\s*(?:\[\d{1,4}\]|\d{1,4}[.)])\s*[A-Z]",text)
    return bool((author or numbered) and (re.search(r"\b(?:18|19|20)\d{2}[a-z]?\b",text)
                or (numbered and re.search(r"https?://|\barxiv\b|\bdoi\b",text,re.I))))


def mark_sections(blocks):
    mode, n_refs, refs_level = "body", 0, 1
    for b in blocks:
        if mode == "refs" and "page" in b:
            # Keep bibliography subdivisions only when the following material
            # still has entry evidence. Captions and graphic regions are body
            # material even when they follow the last reference on a new page.
            same_page = [x for x in blocks if x.get("page") == b["page"]]
            entries = (any(reference_entry_evidence(x["text"]) or REF_TAIL_RE.search(x["text"]) for x in same_page)
                       or (any(re.search(r"\b(?:18|19|20)\d{2}[a-z]?\b",x["text"]) for x in same_page)
                           and any(REF_ENTRY_RE.match(x["text"]) or re.match(r"^\W{0,2}[A-Z][\w’\'-]+,\s+[A-Z]",x["text"]) for x in same_page)))
            boundary = bool(b["type"] == "caption" or ((b.get("table") or b.get("graphic")) and not entries))
            boundary |= (b["type"] == "heading" and not entries)
            boundary |= (not entries and b["type"] == "para" and b["text"][:1].isupper()
                         and word_count(b["text"]) >= 20 and not REF_TAIL_RE.search(b["text"]))
            if boundary:
                mode = "body"
        label = NUM_PREFIX_RE.sub("", b["text"]).strip().rstrip(":：").strip()
        if READING_RE.fullmatch(label):
            b["type"], b["level"], mode = "heading", 1, "reading"
            continue
        if b.get("backmatter") and not reference_entry_evidence(b["text"]):
            if b.get("contact_footer"):
                b["type"] = "frag"
            else:
                mode = "body"
            continue
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
            b.pop("table", None)
            n_refs += 1
        elif mode == "notes" and b["type"] in ("para", "note"):
            b["type"] = "note"
            b["endnote"] = True
    # Floating exhibits can interrupt a bibliography whose final continuation
    # has no repeated heading. A terminal page made of a run of author/year/title
    # entries resumes the known reference region, rather than becoming prose.
    if mode=="body" and any(x["type"]=="ref" for x in blocks) and any(x.get("page") is not None for x in blocks):
        last=max(x.get("page") or 0 for x in blocks)
        tail=[x for x in blocks if x.get("page")==last and not x.get("front_meta")]
        text=" ".join(x["text"] for x in tail)
        entries=re.findall(r"\b(?:18|19|20)\d{2}[a-z]?\.\s*[\"“]",text)
        if (tail and len(entries)>=2 and (starts_lower(tail[0]["text"]) or reference_entry_evidence(tail[0]["text"]))
                and not any(x["type"] in ("heading","caption") or x.get("table") or x.get("graphic") or x.get("equation") for x in tail)):
            for x in tail:
                if x["type"]!="ref":
                    x["type"]="ref"
                    n_refs+=1
    # Count entry starts, not extraction blocks: one entry can wrap across blocks,
    # and several numbered entries can occupy one block. References stay hidden.
    numbered = sum(bool(re.match(r"^\s*(?:\[\d{1,4}\]|\d{1,4}[.)]?\s+)\s*[A-Z]", line))
                   and not REF_RE.fullmatch(NUM_PREFIX_RE.sub("",line).strip().rstrip(":"))
                   for b in blocks if b["type"] == "ref" for line in b.get("line_texts", [b["text"]]))
    return numbered or n_refs


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


def closes_open_delimiter(a, b):
    """The next text closes an outstanding delimiter before starting another."""
    return any(a.count(left) > a.count(right) and right in b
               and (left not in b or b.index(right) < b.index(left))
               for left, right in (("(", ")"), ("[", "]")))


def bracket_wrap(a, b):
    """An aligned citation tail can cross a layout band, not a prose boundary."""
    if not a or a.get("type") != "para" or a["page"] != b["page"] or not closes_open_delimiter(a["text"], b["text"]):
        return False
    needed = ("top", "bottom", "size", "x0", "font")
    if not all(k in a and k in b for k in needed):
        return False
    size = max(a["size"], b["size"])
    gap = a.get("line_gap")
    return (a["font"] == b["font"] and abs(a["size"] - b["size"]) <= .5
            and abs(a["x0"] - b["x0"]) <= .15 * size
            and 0 <= b["top"] - a["bottom"] <= (gap if gap is not None else .25 * size) + max(.45 * size, 2.5))


def paragraph_continues(a, b, across_breaks=True, after_display=False):
    """Does paragraph b carry on from paragraph a? One rule for both engines.

    a is open (no full stop, or a hyphenated word) and b starts like a continuation: lower case, a comma, a joined CJK
    run, or a after-a-function-word. With across_breaks, a b that merely starts in another column or on another page
    also counts, provided the geometry (when known) says a ran to the bottom and b opens the next column or page."""
    a = dict(a, page=a.get("_end_page", a["page"]), bbox=a.get("_end_bbox",a.get("bbox")))
    if a.get("byline") or b.get("byline") or a.get("abstract") != b.get("abstract"):
        return False
    if b.get("list") or (a.get("list") and a["page"] == b["page"] and a.get("key") == b.get("key")) or a.get("toc") or b.get("toc") or a.get("backmatter") or b.get("backmatter"):
        return False
    marks = a.get("superscripts", []) if "first_x0" in a else None
    # A colon can introduce a display within the same sentence. Lowercase
    # prose after that display continues its lead-in, including a raised mark.
    display_continuation = (after_display and starts_lower(b["text"])
                            and terminal_text(a["text"], marks).endswith(":"))
    if a.get("closed") or (end_terminal(a["text"], marks) and not display_continuation):
        return False
    if bracket_wrap(a, b):
        return True
    skipped_pages = b["page"] > a["page"] + 1
    # A citation or parenthetical split at the page foot can resume with a
    # year or capital letter. It must close the outstanding delimiter before
    # opening another, and still needs adjacent-page foot/head geometry.
    sa, sb = block_span(a), block_span(b)
    if (b["page"] == a["page"] + 1 and sa and sb and sa[1] >= 0.55 and sb[0] <= 0.45
            and closes_open_delimiter(a["text"], b["text"])):
        return True
    if (starts_lower(b["text"]) or a["text"].endswith("-") or a["text"].rstrip().endswith(",")
            or (is_cjk(a["text"][-1]) and is_cjk(b["text"][0]))
            or last_word(a["text"]) in STOP_END or b["text"][:1] in ",;)("):
        if not skipped_pages:
            return True
    if (not across_breaks and not skipped_pages) or not (b["page"] != a["page"] or b.get("key") != a.get("key")):
        return False
    if skipped_pages and (block_span(a) is None or block_span(b) is None):
        return False  # an intervening float page is not itself continuation evidence
    if b["page"] != a["page"] and (a.get("column_x1") is not None or b.get("column_x0") is not None):
        needed = (a.get("last_x1"), a.get("column_x1"), b.get("first_x0"), b.get("column_x0"))
        if any(v is None for v in needed):
            return False
        tol = max(1, 0.15 * max(a.get("size", 10), b.get("size", 10)))
        if a["last_x1"] < a["column_x1"] - tol or b["first_x0"] > b["column_x0"] + tol:
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
                a.setdefault("pages", {a["page"]}).update(b.get("pages",{b["page"]}))
                a["_end_page"] = b.get("_end_page",b["page"])
                if b.get("bbox"):
                    a["_end_bbox"] = b.get("_end_bbox",b["bbox"])
                for field in ("last_x1","column_x0","column_x1","bottom","ph"):
                    if field in b:
                        a[field]=b[field]
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


def retain_unmapped(target, *pieces):
    """Keep uncertainty evidence when layout pieces are grouped or continued."""
    for key in ("unmapped_glyphs", "unmapped_text"):
        values = set(target.get(key, []))
        for p in pieces:
            values.update(p.get(key, []))
        if values:
            target[key] = sorted(values)
    for piece in pieces:
        for source in piece.get("unmapped_sources",[]):
            if source not in target.setdefault("unmapped_sources",[]):
                target["unmapped_sources"].append(source)


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
        if (b["type"] in ("para", "note") and out and out[-1]["type"] == "caption" and starts_lower(b["text"])
                and not end_terminal(out[-1]["text"]) and continuation_gap(out[-1], b)):
            retain_unmapped(out[-1], b)
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
                after_display = any(x.get("join_equation", x.get("equation")) for x in out[j + 1:])
                between = out[j + 1:]
                displays = [x for x in between if x.get("display_region")]
                tight_display = bool(displays and not end_terminal(a["text"], a.get("superscripts"))
                                     and last_word(a["text"]) in STOP_END | {"have", "has", "had", "do", "does", "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must"}
                                     and a["page"] == b["page"] and a.get("key") == b.get("key")
                                     and all(x["type"] == "frag" and not any(x.get(k) for k in ("table", "graphic", "pull", "front_meta")) for x in between)
                                     and continuation_gap(a, displays[0]) and continuation_gap(displays[-1], b))
                display_boundary = (after_display
                                    and not starts_lower(b["text"]) and not tight_display)
                if tight_display or (not display_boundary and paragraph_continues(a, b, after_display=after_display)):
                    retain_unmapped(a, b)
                    tail = dict(a, page=a.get("_end_page", a["page"]))
                    if b["page"] != tail["page"] or b.get("key") != tail.get("key"):
                        a["breaks"] = a.get("breaks", 0) + 1
                    text = a["text"]
                    between = out[j + 1:]
                    kept = []
                    for x in between:
                        if (x["type"] == "frag" and x["page"] == tail["page"] and x.get("key") == tail.get("key")
                                and x.get("mono", 0) < 0.5 and not x.get("pull") and not x.get("table") and not x.get("equation")
                                and not x.get("front_meta") and not x.get("contents_page") and not x.get("graphic")):
                            if (x.get("top", float("inf")) < a.get("bottom", float("-inf"))
                                    and re.search(r"[A-Za-z]{3,}", x["text"])):
                                kept.append(x)
                                continue  # prose above the last piece is not its tail; detached math symbols can have separate baselines
                            retain_unmapped(a, x)
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
                    geometry = ("page", "key", "x0", "x1", "top", "bottom", "pw", "ph", "bbox", "last_x1", "column_x0", "column_x1")
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
        geometric = it.pop("note_marks", [])
        found = [int(mark) for previous, mark in geometric]
        found += [(int(m.group(1)) if m.group(1) else 1) for m in marker.finditer(it["text"].translate(SUP_DIGITS))]
        found += [ord(ch) - 0x245F for ch in CIRCLED_RE.findall(it["text"])]
        for n in found:
            note = by_num.get(n)
            pages = it.get("pages") or [it["page"]]
            if note and not note.get("ref") and note["page"] in pages:  # 脚注和引用它的段落在同一页
                note["ref"] = it["id"]
                if note["id"] not in it.setdefault("notes", []):
                    it["notes"].append(note["id"])
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
    # Byline fragments are excluded from section inference and paragraph joins,
    # then emitted as a single visible paragraph beneath the title.
    visible = []
    for b in blocks:
        if b.get("abstract_label"):
            b = dict(b, type="heading", level=1)
        if b.get("byline"):
            b = dict(b, type="para")
            if visible and visible[-1].get("byline") and visible[-1]["page"] == b["page"]:
                a = visible[-1]
                retain_unmapped(a, b)
                a["text"] = a["text"] + " " + b["text"]
                a["x0"], a["x1"] = min(a["x0"], b["x0"]), max(a["x1"], b["x1"])
                a["bottom"] = max(a["bottom"], b["bottom"])
                continue
        visible.append(b)
    blocks = visible
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
        note_marks = []
        for previous, mark in b.get("superscripts", []):
            if any(mark in note_numbers[p] for p in b.get("pages", {b["page"]})):
                note_marks.append((previous, mark))
                text = re.sub(re.escape(previous) + r"\s+" + re.escape(mark) + r"(?!\d)",
                              lambda _: previous + mark, text, count=1)
        if not roman:
            text, n = OCR_LABEL_RE.subn(lambda m: f"{m.group(1)} 1{m.group(2)}", text)
            counters["roman_rewrites"] += n
        origin = dict(b, **b.get("_origin", {}))
        it = {"id": f"{k}{counters[k]}", "type": b["type"], "text": text, "page": origin["page"]}
        if note_marks:
            it["note_marks"] = note_marks
        # Missing glyphs may have been dropped completely from the text. Keep
        # their codes and source boxes until actual equation crops are known.
        own_codes=set(re.findall(r"⟦cid:\d+⟧",text)) | set(b.get("unmapped_glyphs",[]))
        if own_codes:
            it["unmapped_glyphs"] = sorted(own_codes)
        if b.get("unmapped_text"):
            it["unmapped_text"] = b["unmapped_text"]
        if b.get("unmapped_sources"):
            it["unmapped_sources"]=[dict(source) for source in b["unmapped_sources"]]
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
REF_TAIL_RE = re.compile(r"\b(?:19|20)\d\d\b[^.]{0,30}[;:,]\s*\d+\s*[(:]?\s*\d*|\b\d+(?:\s*\(\d+\))?\s*:\s*\d+\s*[-–]\s*\d+")


def looks_like_reference(text):
    """An author-year or numbered bibliography entry: leading surname and initials, a year, volume and pages."""
    return len(text) < 600 and bool(REF_ENTRY_RE.match(text)) and bool(REF_TAIL_RE.search(text))


def layout_signals(blocks, n_pages, info=None):
    """Simple signals that a split went wrong. Returns (score, reasons); a lower score is a better split."""
    paras = [b for b in blocks if b["type"] == "para"]
    if not paras:
        return 99.0, ["no paragraphs"]
    n = len(paras)
    joined_refs = []
    for b in blocks:
        m = re.match(r"^(references?|bibliography)\s+(.+)$", b["text"], re.I)
        if b["type"] in ("para", "note") and m and REF_ENTRY_RE.match(m.group(2)) and REF_TAIL_RE.search(m.group(2)):
            joined_refs.append(b["page"])
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
    metadata_heads = sorted({b["page"] for b in blocks if b["type"]=="heading"
                             and re.fullmatch(r"article history|key\s*words?|JEL\s+(?:codes?|classification)",
                                              b["text"].strip().rstrip(":"),re.I)})
    if metadata_heads:
        reasons.append(f"给执行的 agent（不是给用户的）：metadata labels entered the outline on pages {metadata_heads}; inspect the front-matter region")
    titles = [b for b in blocks if b["type"] == "heading" and b.get("level") == 0]
    if info and (not titles or any(re.search(r"https?://|www\.",b["text"],re.I) for b in titles)):
        reasons.append("给执行的 agent（不是给用户的）：missing or implausible article title; inspect the opening page and front matter")
    expected_titles = [t for p in (info or {}).values() for t in p.get("cover_titles",[])]
    if expected_titles and titles and not any(title_key(b["text"]) == title_key(t) for b in titles for t in expected_titles):
        reasons.append("给执行的 agent（不是给用户的）：article title disagrees with the detected cover; inspect the title and front matter")
    crossing_pages = sorted({b["page"] for b in paras if b.get("gutter_crossings", 0) >= 3})
    if crossing_pages:
        reasons.append(f"body lines cross a column gutter on pages {crossing_pages}")
    ref_pages = defaultdict(list)
    for b in blocks:
        if b["type"] == "ref":
            ref_pages[b.get("page")].append(b)
    suspect_refs = [p for p, bs in ref_pages.items() if p is not None
                    and not any(reference_entry_evidence(b["text"]) for b in bs)
                    and any(CAPTION_RE.match(b["text"]) or b.get("table") or b.get("graphic")
                            or word_count(b["text"])>=20 for b in bs)]
    if suspect_refs:
        reasons.append(f"给执行的 agent（不是给用户的）：references contain non-reference material on pages {sorted(suspect_refs)}; inspect the region boundary")
    duplicates = sorted({b.get("page") for b in blocks if b["type"]=="para" and re.search(r"\b([A-Za-z]{3,})\s+\1\s+([A-Za-z]{3,})\s+\2\b|\b([A-Za-z]{4,})\3\b",b["text"],re.I)})
    duplicates = sorted(set(duplicates) | {b["page"] for b in blocks if b.get("overprinted")
                        and not any(b.get(k) for k in ("front_meta","contents_page","table","graphic","equation"))})
    if duplicates:
        reasons.append(f"duplicated-word runs on pages {duplicates}")
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
    if joined_refs:
        reasons.append(f"bibliography heading merged with entries on pages {sorted(set(joined_refs))}")
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
                 and not b.get("front_meta") and not b.get("contents_page")
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
    score = (4 * lower + 2 * open_end + 4 * zigzag + 4 * len(crossing_pages) + 0.4 * max(0.0, heads_pp - 2.0)
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
    cache = {"cover_text": getattr(pdf,"_segment_cover_text","")}
    first = segment_text_layer(pdf, pnos, columns, cache)
    msgs = []
    best = first
    if columns == "auto":
        layout_reasons = [r for r in first["reasons"] if not any(label in r for label in
                          ("most page text", "dominate page text", "length outliers", "raster-backed", "list markers hidden", "duplicated-word runs", "references contain", "article title"))]
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


def unmapped_equation_regions(items):
    """Snapshot actual display regions before crop rendering widens their boxes."""
    return [dict(id=it["id"],page=it["page"],bbox=list(it["bbox"])) for it in items
            if it["type"]=="frag" and it.get("equation") and it.get("bbox")]


def filter_cropped_unmapped(doc, regions):
    """Only source marks proven to lie inside an equation crop may lose their warning codes."""
    def contains(outer,inner):
        # Output region coordinates have four decimal places.
        return all(a<=b+1e-4 for a,b in zip(outer[:2],inner[:2])) and all(
            a+1e-4>=b for a,b in zip(outer[2:],inner[2:]))
    crops=[it for it in doc["items"] if it["id"] in doc.get("crops",{}) and it.get("equation")]
    covered=[dict(region,crop_id=crop["id"],crop_bbox=crop.get("crop_bbox",crop["bbox"])) for region in regions for crop in crops
             if crop["page"]==region["page"] and contains(crop["bbox"],region["bbox"])]
    def cropped(source,region):
        if source["page"]!=region["page"]:
            return False
        box=source.get("ink_bbox",source["bbox"])
        return contains(region["bbox"],box) or (source.get("ink_bbox")
            and max(region["bbox"][0],box[0])<min(region["bbox"][2],box[2])
            and max(region["bbox"][1],box[1])<min(region["bbox"][3],box[3])
            and contains(region["crop_bbox"],box))
    for it in doc["items"]:
        if it["type"] not in ("para","heading","note","caption"):
            continue
        sources=it.get("unmapped_sources",[])
        for source in sources:
            source["crop_coverage"]=[dict(crop=region["crop_id"],display_bbox=region["bbox"])
                                     for region in covered if cropped(source,region)]
        remove=set()
        for code in it.get("unmapped_glyphs",[]):
            owners=[source for source in sources if code in source["codes"]]
            if owners and all(source.get("crop_coverage") for source in owners):
                remove.add(code)
        if remove:
            kept=set(it["unmapped_glyphs"])-remove
            if kept:it["unmapped_glyphs"]=sorted(kept)
            else:it.pop("unmapped_glyphs",None)
            excerpts=[re.sub(r"⟦cid:\d+⟧",lambda m:"" if m.group() in remove else m.group(),t).strip()
                      for t in it.get("unmapped_text",[])]
            if any(excerpts):it["unmapped_text"]=[t for t in excerpts if t]
            else:it.pop("unmapped_text",None)


def write_outputs(doc, out, chunk_chars):
    its = [i for i in doc["items"] if isinstance(i.get("text"), str)]
    resolved, doc_decisions = resolve_hyphens([i["text"] for i in its])
    for i, t in zip(its, resolved):
        i["text"] = t
    if HY in (doc.get("title_guess") or ""):
        doc["title_guess"] = resolve_hyphens([doc["title_guess"]] + resolved)[0][0]
    write_outputs.decisions = doc_decisions
    for i, t in zip(its, fix_split_ligatures([i["text"] for i in its])):
        i["text"] = t
    for it in its:
        codes=set(it.get("unmapped_glyphs",[])) | set(re.findall(r"⟦cid:\d+⟧",it["text"]))
        if codes:it["unmapped_glyphs"]=sorted(codes)
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
    ap.add_argument("--chunk-chars", type=int, default=12000)
    ap.add_argument("--engine", choices=["auto", "pdfplumber", "mineru"], default="auto",
                    help="auto uses MinerU when it is installed (see requirements.txt), otherwise pdfplumber")
    args = ap.parse_args()
    src = Path(args.input)
    out = Path(args.out)
    if not src.exists():
        sys.exit(f"找不到文件：{src}")

    report = []
    raster_cover = False
    is_text = args.text or src.suffix.lower() in (".txt", ".md")
    engine = args.engine
    if engine == "auto" and not is_text:
        from mineru_backend import available
        engine = "mineru" if available() else "pdfplumber"
    doc = None
    if engine == "mineru" and not is_text:
        from mineru_backend import convert, run
        if args.columns != "auto":
            print("注意：MinerU 引擎自己判断分栏，--columns 在这里不起作用")
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
        regions=unmapped_equation_regions(doc["items"])
        made = crop_regions(src, doc["items"], out / "crops")
        if made:
            doc["crops"] = {k: str(Path(v).relative_to(out)) for k, v in made.items()}
        filter_cropped_unmapped(doc,regions)
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
            cover_text = ""
            if not pnos:
                sys.exit("--pages 选出的页为空")
            first = pdf.pages[pnos[0] - 1]
            raster_cover = any(i.get("width", 0) >= first.width / 2 and i.get("height", 0) >= first.height / 2
                               for i in first.images)
            if pnos and not args.pages:
                first_text = pdf.pages[pnos[0] - 1].extract_text() or ""
                if JSTOR_RE.search(first_text) and len(pnos) > 1:
                    cover_text = first_text
                    report.append(f"第 {pnos[0]} 页是 JSTOR 封面，已跳过")
                    pnos = pnos[1:]
            text_pnos, scan_messages = basic_text_pages(pdf, pnos)
            report.extend(scan_messages)
            mode = "PDF 文字层"
            if cover_text:
                pdf._segment_cover_text = cover_text
            res, check_msgs = choose_columns(pdf, text_pnos, args.columns)
            blocks, body, info, stats = res["blocks"], res["body"], res["info"], res["stats"]
            n_refs, merges = res["n_refs"], res["merges"]
            report.extend(check_msgs)

    items, counters = finalize(blocks)
    labels = page_labels_from(stats["labels"], pnos) if pnos else {}
    title = next((i["text"] for i in items if i["type"] == "heading" and i.get("level") == 0), "")
    if not title and raster_cover:
        report.append("给执行的 agent（不是给用户的）：封面可能含图片标题，文字层未识别到标题；请用 --engine mineru 读取封面，不要用页眉猜标题。")
    doc = {"version": 2, "source": src.name, "source_path": str(src.resolve()), "mode": mode, "page_count": page_count,
           "pages_processed": [pnos[0], pnos[-1]] if pnos else None,
           "page_labels": labels, "title_guess": title, "items": items}
    if counters["P"] == 0:
        sys.exit("给执行的 agent（不是给用户的）：没有切出任何段落。请检查版式并尝试 --engine mineru，或自行整理正文后用 --text 重试。")
    names = write_outputs(doc, out, args.chunk_chars)
    title = doc.get("title_guess", title)
    made = {}
    regions=unmapped_equation_regions(items)
    if pnos:
        from crops import crop_regions
        made = crop_regions(src, items, out / "crops")
        if made:
            doc["crops"] = {k: str(Path(v).relative_to(out)) for k, v in made.items()}
    filter_cropped_unmapped(doc,regions)
    (out / "paragraphs.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    unknown_pages = sorted({i["page"] for i in items if i.get("unmapped_glyphs") and i["type"]!="frag"})
    if unknown_pages:
        report.append(f"给执行的 agent（不是给用户的）：页 {unknown_pages} 有未映射字形，已保留代码和来源位置；请对照原页或用 MinerU 补全。")

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
