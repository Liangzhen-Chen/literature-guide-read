#!/usr/bin/env python3
"""Validate guide data. Fix every error; make a judgment call on each warning.

Usage:
  python check.py WORK/paragraphs.json WORK/guide.json [WORK/paras_*.json]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DENSITY, DENSITY_ALIASES, LANGS, TIER_ALIASES, TIERS, as_lang, compress,  # noqa: E402
                    find_anchor, fmt_num, load_elements, load_guide, load_json, numbers_in,
                    parse_range, pnum, source_numbers, suggest_anchor)

DESCRIPTIVE = {
    "zh": re.compile(r"^(本段|这段|该段|此段|作者在这段|作者在本段|介绍|描述|说明|讨论|定义|给出|提出|分析|总结|列出|阐述)"),
    "en": re.compile(r"^(?:(?:this|the) (?:paragraph|section|passage)s?\b|(?:describes|discusses|introduces|explains|"
                     r"presents|defines|outlines|summari[sz]es|lists|talks about)\b)", re.I),
}
ZH_STYLE = [
    (re.compile(r"对[^，。；：]{1,20}进行"), "“对……进行……”: use a direct verb"),
    (re.compile(r"值得注意的是|需要指出的是|不难发现|众所周知"), "filler opener"),
    (re.compile(r"总而言之|总的来说|综上所述"), "summary filler"),
    (re.compile(r"不仅[^。；]{0,30}而且"), "“不仅……而且……”"),
    (re.compile(r"起到[^。，；]{0,12}作用"), "“起到……作用”: say what it does"),
    (re.compile(r"深刻|精彩|巧妙|有力地|极具"), "evaluative adjective; the guide does not grade the authors"),
]
EN_STYLE = [
    (re.compile(r"\b(?:it is worth noting|importantly|interestingly|notably)\b", re.I), "filler phrase"),
    (re.compile(r"\b(?:brilliant|compelling|powerful|elegant|insightful)\b", re.I), "evaluative adjective"),
]
LIMITS = {"role": {"zh": 16, "en": 60}, "read": {"zh": 90, "en": 240},
          "claim": {"zh": 80, "en": 220}, "thesis": {"zh": 100, "en": 280}}
SHORT_NOTE = {"zh": 40, "en": 25}
PART_RELS = {"supports", "explains", "qualifies", "extends", "frames", "challenges", "answers", "concludes"}
STEP_RELS = PART_RELS | {"rules out", "implies", "names", "raises"}  # zh characters / en words for a skim note on a long paragraph


def run_checks(doc, guide, density=None):
    errors, warns = [], []
    types = load_elements()
    meta = guide.get("meta") or {}
    langs = meta.get("notes_lang") or ["zh"]
    if isinstance(langs, str):
        langs = [langs]
    if [x for x in langs if x not in LANGS]:
        errors.append(f"meta.notes_lang may only contain zh and en; got {langs}")
        langs = [x for x in langs if x in LANGS] or ["zh"]
    primary = langs[0]
    items = {i["id"]: i for i in doc["items"]}
    pids = [i["id"] for i in doc["items"] if i["type"] == "para"]
    n = len(pids)
    entries = guide.get("paras") or {}

    def need(where, value, field):
        d = as_lang(value, primary)
        for lang in langs:
            if not d.get(lang, "").strip():
                errors.append(f"{where}: {field} is missing ({lang})")
        return d

    def nums_ok(where, d, allowed):
        for lang, txt in d.items():
            extra = sorted(x for x in numbers_in(txt) if x not in allowed)
            if extra:
                errors.append(f"{where} ({lang}): numbers not in the source text: {', '.join(fmt_num(x) for x in extra)}")

    def style(where, d, restating=True):
        for lang, txt in d.items():
            if restating and DESCRIPTIVE[lang].search(txt.strip()):
                warns.append(f"{where} ({lang}) describes the paragraph instead of restating it: «{txt[:40]}»")
            for rx, msg in (ZH_STYLE if lang == "zh" else EN_STYLE):
                if rx.search(txt):
                    warns.append(f"{where} ({lang}): {msg}")

    def longer(where, d, key):
        for lang, txt in d.items():
            size = len(txt) if lang == "zh" else len(txt)
            if size > LIMITS[key][lang]:
                warns.append(f"{where} ({lang}): {key} is {size} characters; keep it under {LIMITS[key][lang]}")

    if not str(meta.get("title", "")).strip():
        errors.append("meta.title is missing")
    whole = set()
    for it in doc["items"]:
        if it["type"] in ("para", "note", "caption", "heading"):
            whole |= source_numbers(it["text"])
    if not str(meta.get("purpose", "")).strip():
        warns.append("meta.purpose is missing: ask the reader what they read for before writing (SKILL.md, step 0)")
    questions = guide.get("questions")
    if questions is not None:
        if not isinstance(questions, list) or any(not isinstance(q, dict) or not q.get("q") or not q.get("a") for q in questions):
            errors.append("questions must be a list of objects with 'q' (the reader's question), 'a' (the answer) and 'p' (paragraph ids)")
            questions = []
    thesis = need("guide", guide.get("thesis"), "thesis")
    overview = need("guide", guide.get("overview"), "overview")
    nums_ok("thesis", thesis, whole)
    nums_ok("overview", overview, whole)
    longer("thesis", thesis, "thesis")

    # text that belongs to a paragraph's region: table rows, figure labels and captions up to the next paragraph
    region, cur = {}, None
    for it in doc["items"]:
        if it["type"] == "para":
            cur = it["id"]
        elif cur and it["type"] in ("frag", "caption"):
            region.setdefault(cur, []).append(it["text"])

    def text_nums(ids):
        out = set()
        for i in ids:
            it = items.get(i)
            if it:
                out |= source_numbers(it["text"])
                for nid in it.get("notes", []):
                    out |= source_numbers(items[nid]["text"])
                for t in region.get(i, []):
                    out |= source_numbers(t)
        return out

    for k, q in enumerate(questions or []):
        ids = q.get("p") or []
        if not isinstance(ids, list) or not ids:
            errors.append(f"question {k + 1}: 'p' must list the paragraph ids that answer it")
            ids = []
        bad = [i for i in ids if i not in items or items[i]["type"] not in ("para", "note")]
        if bad:
            errors.append(f"question {k + 1}: 'p' names ids that are not paragraphs: {', '.join(bad)}")
        for f in ("q", "a"):
            nums_ok(f"question {k + 1} {f}", need(f"question {k + 1}", q[f], f), text_nums([i for i in ids if i not in bad]))

    # parts: cover P1..Pn in order
    parts = guide.get("parts") or []
    if not parts:
        errors.append("parts is missing")
    pos, seen, part_of = 1, set(), {}
    for p in parts:
        pid = p.get("id") or "?"
        if pid in seen:
            errors.append(f"duplicate part id {pid}")
        seen.add(pid)
        try:
            a, b = parse_range(p.get("range", ""))
        except ValueError as e:
            errors.append(f"{pid}: {e}")
            continue
        if a != pos:
            errors.append(f"{pid} starts at P{a}; parts must cover P1-P{n} in order, so it should start at P{pos}")
        pos = b + 1
        ids = [f"P{i}" for i in range(a, b + 1)]
        for i in ids:
            part_of[i] = p
        need(pid, p.get("title"), "title")
        need(pid, p.get("role"), "role")
        if not p.get("skip"):
            claim = need(pid, p.get("claim"), "claim")
            longer(f"{pid} claim", claim, "claim")
            nums_ok(f"{pid} claim", claim, text_nums(ids))
            cp = pnum(p.get("claim_p"))
            if cp is None or not a <= cp <= b:
                errors.append(f"{pid}: claim_p must name a paragraph inside {p.get('range')}")
            recall = p.get("recall")
            if recall is None:
                warns.append(f"{pid}: no 'recall' questions; two or three per part let the reader test themselves (method.md section 12)")
            elif not isinstance(recall, list) or not recall or any(not isinstance(q, dict) or not q.get("q") or not q.get("a") for q in recall):
                errors.append(f"{pid}: recall must be a list of objects with 'q' (question) and 'a' (answer)")
            else:
                for k, q in enumerate(recall):
                    for f in ("q", "a"):
                        nums_ok(f"{pid} recall {k + 1} {f}", need(f"{pid} recall {k + 1}", q[f], f), text_nums(ids))
    if parts and pos - 1 != n:
        errors.append(f"parts end at P{pos - 1}; they must end at P{n}")

    # logic map: relations between parts, and the steps inside each part
    live = {p.get("id"): p for p in parts if not p.get("skip")}
    with_rel = [p for p in live.values() if p.get("rel")]
    if with_rel:
        concl = [p for p in live.values() if (p.get("rel") or [{}])[0].get("type") == "concludes"]
        if len(concl) > 1:
            warns.append(f"more than one part concludes: {', '.join(p['id'] for p in concl)}; the map shows the first")
        for pid, p in live.items():
            rels = p.get("rel") or []
            if not rels:
                errors.append(f"{pid}: needs 'rel' (what it does for the conclusion or for another part) once any part has one")
                continue
            for k, r in enumerate(rels):
                if r.get("type") not in PART_RELS:
                    errors.append(f"{pid} rel {k + 1}: type must be one of {', '.join(sorted(PART_RELS))}")
                to = r.get("to")
                if to != "T" and to not in live:
                    errors.append(f"{pid} rel {k + 1}: 'to' must be T (the conclusion) or the id of a part that is not skipped")
                if to == pid:
                    errors.append(f"{pid} rel {k + 1}: a part cannot point to itself")
                if r.get("label") is not None:
                    try:
                        a0, b0 = parse_range(p.get("range", ""))
                        nums_ok(f"{pid} rel {k + 1} label", as_lang(r["label"], primary), text_nums([f"P{i}" for i in range(a0, b0 + 1)]))
                    except ValueError:
                        pass
        for pid in live:  # the first relation of every part must lead to the conclusion without a cycle
            seen, cur = [], pid
            while cur != "T":
                if cur in seen or cur not in live or not live[cur].get("rel"):
                    errors.append(f"{pid}: its first relations ({' -> '.join(map(str, seen + [cur]))}) do not lead to the conclusion T")
                    break
                seen.append(cur)
                cur = live[cur]["rel"][0].get("to")
    for pid, p in live.items():
        flow = p.get("flow") or []
        if not flow:
            if with_rel:
                warns.append(f"{pid}: no 'flow'; clicking it on the map shows no steps")
            continue
        try:
            a0, b0 = parse_range(p.get("range", ""))
        except ValueError:
            continue
        inside = {f"P{i}" for i in range(a0, b0 + 1)}
        inside |= {n for i in list(inside) for n in (items.get(i) or {}).get("notes", [])}
        if not 2 <= len(flow) <= 7:
            warns.append(f"{pid}: flow has {len(flow)} steps; 3 to 6 is usual")
        for k, st in enumerate(flow):
            if st.get("p") not in inside:
                errors.append(f"{pid} flow step {k + 1}: 'p' must be a paragraph or footnote inside {p.get('range')}")
            if k and st.get("rel") not in STEP_RELS:
                errors.append(f"{pid} flow step {k + 1}: 'rel' must be one of {', '.join(sorted(STEP_RELS))}")
            x = need(f"{pid} flow step {k + 1}", st.get("x"), "x")
            nums_ok(f"{pid} flow step {k + 1}", x, text_nums(sorted(inside)))

    missing = [pnum(p) for p in pids if p not in entries]
    if missing:
        errors.append(f"no guide entry for {compress(missing)}")
    unknown = [k for k in entries if k not in items or items[k]["type"] not in ("para", "note")]
    if unknown:
        errors.append(f"guide entries for ids that are not paragraphs or footnotes: {', '.join(unknown[:20])}")

    hl, counts, mapped = {}, {t: 0 for t in TIERS}, set()
    for eid, g in entries.items():
        it = items.get(eid)
        if not it or it["type"] not in ("para", "note") or not isinstance(g, dict):
            continue
        tier = TIER_ALIASES.get(g.get("tier"), g.get("tier"))
        if tier not in TIERS:
            errors.append(f"{eid}: tier must be close, skim or skip")
            continue
        g["tier"] = tier
        if it["type"] == "para":
            counts[tier] += 1
        role = need(eid, g.get("role"), "role")
        longer(f"{eid} role", role, "role")
        base = [eid] if it["type"] == "para" else [it.get("ref") or eid]
        k = pnum(base[0])
        neighbours = [f"P{k - 1}", f"P{k + 1}"] if k else []
        allowed = text_nums(base + neighbours) | source_numbers(it["text"])
        if tier == "close":
            d = need(eid, g.get("read"), "read")
            longer(f"{eid} read", d, "read")
        else:
            d = need(eid, g.get("note"), "note")
            if tier == "skim" and len(it["text"]) >= 600:
                for lang, txt in d.items():
                    size = len(txt) if lang == "zh" else len(txt.split())
                    if size < SHORT_NOTE[lang]:
                        warns.append(f"{eid} ({lang}): the note is short for a {len(it['text'])}-character paragraph; "
                                     f"a skim note should let the reader move on without the original")
            if tier == "skip":
                why = need(eid, g.get("why"), "why")
                nums_ok(f"{eid} why", why, allowed)
        nums_ok(f"{eid} {'read' if tier == 'close' else 'note'}", d, allowed)
        style(f"{eid} {'read' if tier == 'close' else 'note'}", d, restating=tier != "close")
        spans = []
        for i, e in enumerate(g.get("els") or []):
            t = e.get("t")
            if t not in types:
                errors.append(f"{eid} element {i + 1}: unknown type {t!r} (see references/elements.md)")
                continue
            a = str(e.get("a", "")).strip()
            if types[t]["level"] >= 2 and not a:
                errors.append(f"{eid} element {i + 1} ({t}): needs an anchor 'a' copied verbatim from the paragraph")
            if a:
                found = find_anchor(it["text"], a)
                if found is None:
                    errors.append(f"{eid} element {i + 1}: anchor not found in the original: «{a[:70]}»\n"
                                  f"      closest sentence: «{suggest_anchor(it['text'], a)}»")
                else:
                    spans.append((found[0], found[1], i))
            for f in ("s", "x", "term"):
                if e.get(f) is not None:
                    nums_ok(f"{eid} element {i + 1} {f}", as_lang(e.get(f), primary), allowed)
            if t == "formula":
                if "tex" in e and not str(e.get("tex") or "").strip():
                    errors.append(f"{eid} element {i + 1}: tex is empty; write the LaTeX or drop the field")
                elif e.get("tex"):
                    tex = str(e["tex"])
                    depth = 0
                    for ch in re.sub(r"\\[{}]", "", tex):  # escaped braces are literal
                        depth += ch == "{"
                        depth -= ch == "}"
                        if depth < 0:
                            break
                    if depth != 0:
                        errors.append(f"{eid} element {i + 1}: tex has unbalanced braces: «{tex[:60]}»")
                elif not e.get("tex"):
                    warns.append(f"{eid} element {i + 1}: formula without tex; transcribe it from WORK/crops/ or the open version")
                syms = e.get("syms")
                if syms is not None:
                    if not isinstance(syms, list) or any(not isinstance(y, dict) or not y.get("s") or not y.get("m") for y in syms):
                        errors.append(f"{eid} element {i + 1}: syms must be a list of objects with 's' (symbol) and 'm' (meaning)")
                    else:
                        for k, y in enumerate(syms):
                            nums_ok(f"{eid} element {i + 1} sym {k + 1}", as_lang(y["m"], primary), allowed)
                if e.get("why") is not None:
                    nums_ok(f"{eid} element {i + 1} why", as_lang(e["why"], primary), allowed)
            if e.get("s") is not None:
                need(f"{eid} element {i + 1}", e.get("s"), "s")
                mapped.add(eid if it["type"] == "para" else it.get("ref"))
            if t == "def" and not e.get("term"):
                warns.append(f"{eid} element {i + 1}: a definition should name its term in 'term'")
        spans.sort()
        if len(spans) > 4:
            warns.append(f"{eid}: {len(spans)} highlights; more than four in one paragraph stops being a signal (keep two to four)")
        for (s1, e1, i1), (s2, e2, i2) in zip(spans, spans[1:]):
            if s2 < e1:
                warns.append(f"{eid}: anchors of elements {i1 + 1} and {i2 + 1} overlap; only the first is highlighted")
        hl[eid] = spans

    role_count, role_text = {}, {}
    for eid, g in entries.items():
        if isinstance(g, dict) and items.get(eid, {}).get("type") == "para":
            for lang, txt in as_lang(g.get("role"), primary).items():
                key = (lang, txt.strip().lower())
                role_count.setdefault(key, []).append(eid)
                role_text.setdefault(key, txt.strip())
    for key, ids in sorted(role_count.items(), key=lambda kv: -len(kv[1])):
        lang, txt = key
        if len(ids) >= 4 and txt:
            warns.append(f"{len(ids)} paragraphs ({compress([pnum(i) for i in ids])}) carry the same role «{role_text[key]}» ({lang}); "
                         f"a role says what that paragraph does (\"Experiment 2 results\"), not its kind")
    for p in parts:
        if p.get("skip") or "_skip" in p:
            continue
        try:
            a, b = parse_range(p.get("range", ""))
        except ValueError:
            continue
        if not any(f"P{i}" in mapped for i in range(a, b + 1)):
            warns.append(f"{p.get('id')}: no element has a map label 's', so this part shows only its claim on the map")

    dens = DENSITY_ALIASES.get(density or meta.get("density") or "medium", density or meta.get("density") or "medium")
    cap = DENSITY.get(dens)
    if cap is None:
        warns.append(f"meta.density should be low, medium or high; got {dens!r}, using medium")
        dens, cap = "medium", DENSITY["medium"]
    if n and counts["close"] / n > cap + 1e-9:
        warns.append(f"{counts['close']} close reads = {counts['close'] / n:.0%} of paragraphs, above the {dens} cap of {cap:.0%}")
    if n and counts["close"] == 0:
        warns.append("no close-read paragraphs")
    stats = {"n": n, "counts": counts, "density": dens, "langs": langs, "parts": len(parts)}
    return errors, warns, {"hl": hl, "stats": stats, "primary": primary}


def report(errors, warns, computed):
    st = computed["stats"]
    n, c = st["n"], st["counts"]
    share = f"{c['close'] / n:.0%}" if n else "-"
    print(f"{n} paragraphs: {c['close']} close ({share}), {c['skim']} skim, {c['skip']} skip; "
          f"{st['parts']} parts; notes in {'+'.join(st['langs'])}; density {st['density']}")
    print(f"{len(errors)} errors" + (":" if errors else ""))
    for e in errors:
        print(f"  - {e}")
    print(f"{len(warns)} warnings" + (":" if warns else ""))
    for w in warns:
        print(f"  - {w}")


def main():
    ap = argparse.ArgumentParser(description="Validate guide data")
    ap.add_argument("paragraphs")
    ap.add_argument("guide", nargs="+")
    ap.add_argument("--density", choices=list(DENSITY))
    args = ap.parse_args()
    errors, warns, computed = run_checks(load_json(args.paragraphs), load_guide(args.guide), args.density)
    report(errors, warns, computed)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
