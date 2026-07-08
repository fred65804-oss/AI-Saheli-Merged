#!/usr/bin/env python3
"""
Semantic, hierarchy-aware PDF chunker for messy (scanned) government documents.

Standalone tool. Free & local — no API keys.
Pipeline:
    render page image (pypdfium2)
      -> OCR the CLEAN image (RapidOCR)          # ignores the corrupt text layer
      -> repair spacing (wordninja)
      -> strip header/footer/stamp boilerplate
      -> detect headings (numbering / colon / caps / size cascade)
      -> MERGE multi-line (wrapped) headings      # fixes "half headings"
      -> build H1>H2>H3>H4 hierarchy
      -> pack into ~target-token, sentence-aligned chunks with overlap
      -> write ONE <name>.chunks.json per PDF

Why OCR? Scanned govt PDFs have a garbage embedded text layer but a clean visible
page. We read the page the way a human does, then chunk the clean text.

USAGE
    python chunk_pdfs.py file.pdf [more.pdf ...] --out ./out
    python chunk_pdfs.py --input-dir ./pdfs --out ./out --dpi 200 -v
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from ocr import Line, extract_pages_ocr, get_ocr_backend


# =========================================================================== #
# 0. Native text-layer extraction + scanned/digital auto-detect
# =========================================================================== #
def extract_pages_text(pdf_path: str) -> tuple[list[list[Line]], float]:
    """Extract clean born-digital text via pdfplumber (fast, no OCR).

    Used when a PDF has a good text layer (incl. proper-Unicode Hindi). Returns
    Line objects compatible with the OCR path (height = median char size).
    """
    import statistics

    import pdfplumber

    pages: list[list[Line]] = []
    page_h = 792.0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_h = page.height or page_h
            lines: list[Line] = []
            try:
                raw = page.extract_text_lines(strip=True, return_chars=True)
            except TypeError:
                raw = page.extract_text_lines(strip=True)
            for rl in raw:
                text = re.sub(r"\s+", " ", rl["text"]).strip()
                if not text:
                    continue
                sizes = [c["size"] for c in rl.get("chars", []) if c.get("size")]
                h = round(statistics.median(sizes), 1) if sizes else 10.0
                lines.append(Line(text=text, x0=round(rl["x0"], 1), x1=round(rl["x1"], 1),
                                  top=round(rl["top"], 1), bottom=round(rl["bottom"], 1),
                                  height=h, conf=1.0, page=i))
            pages.append(lines)
    return pages, page_h


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ']+")


def _load_dict() -> set[str]:
    try:
        import wordninja

        return set(wordninja.DEFAULT_LANGUAGE_MODEL._wordcost.keys())
    except Exception:
        return set()


_ENGLISH_WORDS = _load_dict()


def _text_quality(pages: list[list[Line]]) -> tuple[float, int]:
    """Dictionary-hit ratio over a sample. A clean text layer scores high; a
    garbled/font-mangled/OCR-noisy layer (e.g. 'matnutrition', 'MMininisistrtry')
    scores low and should be OCR'd. Devanagari tokens count as valid.
    Returns (quality, avg_chars_per_page)."""
    words: list[str] = []
    chars = 0
    sample = pages[:8]
    for lines in sample:
        for ln in lines:
            chars += len(ln.text)
            words += _WORD_RE.findall(ln.text)
    checkable = [w for w in words if len(w) >= 3]
    if len(checkable) < 30:
        return 0.0, chars // max(1, len(sample))
    good = sum(
        1 for w in checkable
        if _DEVANAGARI.search(w) or w.lower() in _ENGLISH_WORDS
    )
    return good / len(checkable), chars // max(1, len(sample))


def choose_source(pdf_path: str) -> tuple[str, list[list[Line]] | None, float]:
    """Decide 'text' vs 'ocr' for a document. Returns (source, text_pages, page_h)
    — text_pages is reused if we pick text (avoids a second extraction)."""
    try:
        pages, page_h = extract_pages_text(pdf_path)
    except Exception:
        return "ocr", None, 792.0
    quality, cpp = _text_quality(pages)
    if cpp >= 150 and quality >= 0.80:
        return "text", pages, page_h
    return "ocr", None, page_h


# =========================================================================== #
# 1. Boilerplate / noise removal
# =========================================================================== #
_NOISE_RE = [
    re.compile(r"^\d+\s*/\s*\d+$"),                 # 1/18
    re.compile(r"\d{4,}/\d{4}"),                    # 573479/2021 doc-id stamps
    re.compile(r"under\s*secre", re.I),            # "...O/o Under Secreatry" footer
    re.compile(r"//"),                              # garbled barcode stamps
    re.compile(r"^\d{6,}"),                         # long leading digit runs
    re.compile(r"^page\s+\d+$", re.I),
]


def _is_junk(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    if letters < 2:
        return True
    if len(text) >= 3 and letters / len(text) < 0.35:
        return True
    return False


def _norm_key(text: str) -> str:
    t = re.sub(r"\d", "#", text.lower())
    return re.sub(r"[^a-z#]", "", t)


def strip_boilerplate(pages_lines: list[list[Line]], page_height: float) -> list[list[Line]]:
    n_pages = len(pages_lines)
    header_zone = page_height * 0.08
    footer_zone = page_height * 0.92

    band_counts: Counter[str] = Counter()
    for lines in pages_lines:
        for ln in lines:
            if ln.top < header_zone or ln.bottom > footer_zone:
                key = _norm_key(ln.text)
                if key:
                    band_counts[key] += 1
    threshold = max(2, round(0.30 * n_pages))
    repeating = {k for k, c in band_counts.items() if c >= threshold and len(k) >= 3}

    cleaned: list[list[Line]] = []
    for lines in pages_lines:
        keep: list[Line] = []
        for ln in lines:
            if any(rx.search(ln.text) for rx in _NOISE_RE):
                continue
            in_band = ln.top < header_zone or ln.bottom > footer_zone
            if in_band and _norm_key(ln.text) in repeating:
                continue
            if _is_junk(ln.text):
                continue
            keep.append(ln)
        cleaned.append(keep)
    return cleaned


# =========================================================================== #
# 2. Heading detection (signal cascade)
# =========================================================================== #
_ROMAN = r"(?:ix|iv|v?i{1,3}|x)"
_NUM_PATTERNS = [
    ("annexure",    re.compile(r"^\s*annex(?:ure)?\b", re.I),                1),
    ("subject",     re.compile(r"^\s*sub[ij]ect\b\s*[:\-]?", re.I),         1),
    ("num_multi",   re.compile(r"^\s*\d+(?:\.\d+)+\s"),                      2),
    ("num_dot",     re.compile(r"^\s*\d+\s*[\.\)]\s*\S"),                    2),
    ("paren_upper", re.compile(r"^\s*\(\s*[A-Z]\s*\)\s*"),                   3),
    ("alpha_upper", re.compile(r"^\s*[A-Z]\s*[\.\)]\s*[A-Z]"),               3),
    ("paren_lower", re.compile(rf"^\s*\(\s*(?:[a-z]|{_ROMAN})\s*\)", re.I),  4),
    ("alpha_lower", re.compile(r"^\s*[a-z]\s*[\.\)]\s+\S"),                  4),
]
_ORDINAL_GUARD = re.compile(r"^\s*\d+(st|nd|rd|th)\b", re.I)
# Internal sentence break => the line is prose (a numbered paragraph), not a
# heading. Covers both "concept. While" and OCR-merged "concept.While".
_INTERNAL_SENTENCE = re.compile(r"[a-z]\.\s+[A-Z]|[a-z]{3}\.[A-Z][a-z]")


def numbering_type(text: str) -> tuple[str, int] | None:
    if _ORDINAL_GUARD.match(text):
        return None
    for name, rx, level in _NUM_PATTERNS:
        if rx.match(text):
            if name in ("num_dot", "num_multi"):
                lead = re.match(r"^\s*(\d+)", text)
                if lead and int(lead.group(1)) > 99:      # years, not sections
                    return None
            if name == "num_multi":
                depth = text.strip().split()[0].count(".")
                return name, 2 + max(0, depth - 1)
            return name, level
    return None


def _ends_like_sentence(text: str) -> bool:
    t = text.rstrip()
    return t.endswith((".", "!", "?")) and not t.endswith("...")


def _is_prose(text: str) -> bool:
    return bool(_INTERNAL_SENTENCE.search(text))


def classify_headings(all_lines: list[Line]) -> None:
    if not all_lines:
        return
    import statistics

    long_h = [ln.height for ln in all_lines if len(ln.text) >= 60 and ln.height]
    if long_h:
        baseline = statistics.median(long_h)
        mean = statistics.mean(long_h)
        cv = (statistics.pstdev(long_h) / mean) if mean else 1.0
    else:
        baseline, cv = 0.0, 1.0
    height_reliable = cv < 0.08          # OCR box heights are usually noisy

    for ln in all_lines:
        num = numbering_type(ln.text)
        ln.num_type = num[0] if num else None
        n_words = len(ln.text.split())
        short = len(ln.text) <= 90 and n_words <= 14
        caps = ln.text.isupper() and len(ln.text) > 3 and n_words <= 12
        num_head = (
            bool(num)
            and n_words <= 10
            and len(ln.text) <= 80
            and not _ends_like_sentence(ln.text)
            and not _is_prose(ln.text)
        )
        colon_head = (
            ln.text.rstrip().endswith(":")
            and len(ln.text) <= 75
            and 1 <= n_words <= 10
            and not _ends_like_sentence(ln.text)
        )
        big = height_reliable and ln.height >= baseline * 1.15
        prose = _is_prose(ln.text)

        is_heading = False
        if num_head:
            is_heading = True
        elif colon_head:
            is_heading = True
        elif caps and short and not prose:
            is_heading = True
        elif big and short and not _ends_like_sentence(ln.text) and not prose:
            is_heading = True

        if is_heading:
            if re.match(r"^\s*[•▪◦‣●·]\s", ln.text):
                is_heading = False
            if sum(c.isalpha() for c in ln.text) < 3:
                is_heading = False
        ln.is_heading = is_heading

    _assign_levels(all_lines)


def _assign_levels(all_lines: list[Line]) -> None:
    headings = [ln for ln in all_lines if ln.is_heading]
    styled = [ln for ln in headings if not ln.num_type]
    xs = sorted({round(ln.x0) for ln in styled})
    clusters: list[float] = []
    for x in xs:
        if not clusters or x - clusters[-1] > 12:
            clusters.append(x)

    def tier(x0: float) -> int:
        for i, c in enumerate(clusters):
            if abs(round(x0) - c) <= 12:
                return i
        return 0

    for ln in headings:
        num = numbering_type(ln.text)
        if num:
            ln.level = num[1]
        else:
            ln.level = min(3 + tier(ln.x0), 4)


# =========================================================================== #
# 3. Multi-line (wrapped) heading merge — fixes "half headings"
# =========================================================================== #
def merge_heading_runs(lines: list[Line]) -> list[Line]:
    """Absorb tightly-wrapped continuation lines into a heading.

    A heading that does not end with terminal punctuation and is followed by
    very tightly spaced lines at the same indent (a wrapped title like the
    multi-line 'Subject:' block) is merged into one heading.
    """
    if not lines:
        return lines
    import statistics

    med_h = statistics.median([ln.height for ln in lines if ln.height]) or 20.0
    tight = 0.4 * med_h

    out: list[Line] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.is_heading:
            out.append(ln)
            i += 1
            continue
        text = ln.text
        bottom = ln.bottom
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if nxt.page != ln.page:
                break
            if text.rstrip().endswith((":", ".", "!", "?")):
                break
            if len(text) > 400:
                break
            gap = nxt.top - lines[j - 1].bottom
            if gap > tight:
                break
            if abs(nxt.x0 - ln.x0) > 45:
                break
            if nxt.num_type or re.match(r"^\s*[•▪◦‣●·]", nxt.text):
                break
            text = text + " " + nxt.text
            bottom = nxt.bottom
            j += 1
        ln.text = text
        ln.bottom = bottom
        out.append(ln)
        i = j if j > i + 1 else i + 1
    return out


# =========================================================================== #
# 4. Build hierarchical sections
# =========================================================================== #
class Section:
    def __init__(self, path: list[Line], body: list[Line]):
        self.path = path
        self.body = body


def build_sections(all_lines: list[Line]) -> list[Section]:
    sections: list[Section] = []
    stack: list[Line] = []
    body: list[Line] = []

    def flush():
        nonlocal body
        if body:
            sections.append(Section(list(stack), list(body)))
        body = []

    for ln in all_lines:
        if ln.is_heading:
            flush()
            while stack and stack[-1].level >= ln.level:
                stack.pop()
            stack.append(ln)
        else:
            body.append(ln)
    flush()
    return sections


# =========================================================================== #
# 5. Semantic packing
# =========================================================================== #
def _get_token_counter(mode: str):
    if mode == "tiktoken":
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            return lambda t: len(enc.encode(t))
        except Exception:
            print("  (tiktoken unavailable — heuristic token count)", file=sys.stderr)
    return lambda t: max(1, round(len(re.findall(r"\S+", t)) / 0.75))


_BULLET_RE = re.compile(r"^\s*[•▪◦‣●·\-\*]\s+")


def body_to_units(body: list[Line]) -> list[str]:
    parts: list[str] = []
    for ln in body:
        t = ln.text
        if parts and parts[-1].endswith("-"):
            parts[-1] = parts[-1][:-1] + t
        elif _BULLET_RE.match(t):
            parts.append("\n" + t)
        else:
            parts.append(t)
    blob = re.sub(r"[ \t]+", " ", " ".join(parts)).strip()

    units: list[str] = []
    for seg in blob.split("\n"):
        seg = seg.strip()
        if not seg:
            continue
        for s in re.split(r"(?<=[.!?;:])\s+(?=[A-Z0-9(ऀ-ॿ])", seg):
            s = s.strip()
            if s:
                units.append(s)
    return units


def _split_long_unit(unit: str, target: int, count) -> list[str]:
    words = unit.split()
    pieces, cur, ct = [], [], 0
    for w in words:
        wt = count(w)
        if cur and ct + wt > target:
            pieces.append(" ".join(cur))
            cur, ct = [], 0
        cur.append(w)
        ct += wt
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def pack_units(units: list[str], target: int, overlap: float, count, min_tokens: int) -> list[str]:
    expanded: list[str] = []
    for u in units:
        expanded.extend(_split_long_unit(u, target, count) if count(u) > target else [u])
    units = expanded

    chunks, cur, cur_tok = [], [], 0
    for u in units:
        ut = count(u)
        if cur and cur_tok + ut > target:
            chunks.append(" ".join(cur))
            tail, tail_tok = [], 0
            for prev in reversed(cur):
                pt = count(prev)
                if tail_tok + pt > overlap * target:
                    break
                tail.insert(0, prev)
                tail_tok += pt
            cur, cur_tok = tail, tail_tok
        cur.append(u)
        cur_tok += ut
    if cur:
        chunks.append(" ".join(cur))
    if len(chunks) >= 2 and count(chunks[-1]) < min_tokens:
        last = chunks.pop()
        chunks[-1] = chunks[-1] + " " + last
    return chunks


# =========================================================================== #
# 6. Orchestrate one PDF
# =========================================================================== #
def _common_prefix(a: list, b: list) -> list:
    out = []
    for x, y in zip(a, b):
        if x == y:
            out.append(x)
        else:
            break
    return out


def merge_small_chunks(chunks: list[dict], min_tokens: int, count) -> list[dict]:
    """Fold sub-min-token chunks into a neighbour so the KB has no useless
    fragments. Merges into the previous chunk (or the next, for a tiny first
    chunk); the merged heading_path collapses to the two chunks' common ancestor.
    """
    if not chunks:
        return chunks

    def fold(dst: dict, src: dict) -> None:
        dst["text"] = (dst["text"] + " " + src["text"]).strip()
        dst["token_estimate"] = count(dst["text"])
        dst["char_count"] = len(dst["text"])
        if src.get("page_start"):
            dst["page_start"] = min(dst.get("page_start") or src["page_start"], src["page_start"])
        if src.get("page_end"):
            dst["page_end"] = max(dst.get("page_end") or src["page_end"], src["page_end"])
        cp = _common_prefix(dst["heading_path"], src["heading_path"])
        dst["heading_path"] = cp
        dst["heading_path_str"] = " > ".join(cp)
        dst["heading"] = cp[-1] if cp else None
        dst["level"] = len(cp)
        dst["contextualized_text"] = (dst["heading_path_str"] + "\n\n" + dst["text"]) if cp else dst["text"]

    out: list[dict] = []
    for c in chunks:
        if out and c["token_estimate"] < min_tokens:
            fold(out[-1], c)
        else:
            out.append(c)
    # tiny leading chunk: fold forward into the next
    if len(out) >= 2 and out[0]["token_estimate"] < min_tokens:
        fold(out[1], out[0])
        out.pop(0)
    # renumber chunk_ids to stay contiguous
    for i, c in enumerate(out, start=1):
        stem = c["chunk_id"].rsplit("_", 1)[0]
        c["chunk_id"] = f"{stem}_{i:04d}"
    return out


def chunk_pdf(path: Path, backend_getter, args) -> dict:
    count = _get_token_counter(args.tokenizer)

    # Decide extraction source (native text vs OCR).
    source = args.source
    text_pages = None
    page_h = 792.0
    if source == "auto":
        source, text_pages, page_h = choose_source(str(path))
    if source == "text":
        pages_lines, page_h = (text_pages, page_h) if text_pages is not None else extract_pages_text(str(path))
    else:
        pages_lines, page_h = extract_pages_ocr(str(path), backend_getter(), dpi=args.dpi)

    pages_lines = strip_boilerplate(pages_lines, page_h)
    all_lines = [ln for lines in pages_lines for ln in lines]

    classify_headings(all_lines)
    all_lines = merge_heading_runs(all_lines)
    # levels were assigned pre-merge; re-run only level assignment on merged set
    _assign_levels(all_lines)
    sections = build_sections(all_lines)

    chunks: list[dict] = []
    seq = 0
    for sec in sections:
        units = body_to_units(sec.body)
        if not units:
            continue
        path_texts = [h.text for h in sec.path]
        immediate = sec.path[-1] if sec.path else None
        ctx = " > ".join(path_texts)
        for t in pack_units(units, args.target_tokens, args.overlap, count, args.min_tokens):
            seq += 1
            pg = [ln.page for ln in sec.body]
            chunks.append({
                "chunk_id": f"{path.stem}_{seq:04d}",
                "doc": path.name,
                "scheme": args.scheme,
                "page_start": min(pg) if pg else None,
                "page_end": max(pg) if pg else None,
                "heading": immediate.text if immediate else None,
                "heading_path": path_texts,
                "heading_path_str": ctx,
                "level": immediate.level if immediate else 0,
                "heading_x0": immediate.x0 if immediate else None,
                "heading_conf": immediate.conf if immediate else None,
                "text": t,
                "contextualized_text": (ctx + "\n\n" + t) if ctx else t,
                "token_estimate": count(t),
                "char_count": len(t),
            })

    chunks = merge_small_chunks(chunks, args.min_tokens, count)

    outline = [
        {"level": ln.level, "num_type": ln.num_type, "text": ln.text,
         "x0": ln.x0, "conf": ln.conf, "page": ln.page}
        for ln in all_lines if ln.is_heading
    ]
    return {
        "doc": path.name,
        "scheme": args.scheme,
        "source": source,
        "pages": len(pages_lines),
        "n_headings": len(outline),
        "n_chunks": len(chunks),
        "outline": outline,
        "chunks": chunks,
    }


# =========================================================================== #
# CLI
# =========================================================================== #
def main() -> None:
    ap = argparse.ArgumentParser(description="Free, local, hierarchy-aware PDF chunker (OCR-based).")
    ap.add_argument("pdfs", nargs="*")
    ap.add_argument("--input-dir")
    ap.add_argument("--out", default="chunks_out")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI for OCR")
    ap.add_argument("--target-tokens", type=int, default=256)
    ap.add_argument("--overlap", type=float, default=0.15)
    ap.add_argument("--min-tokens", type=int, default=40)
    ap.add_argument("--tokenizer", choices=["heuristic", "tiktoken"], default="heuristic")
    ap.add_argument("--source", default="auto", choices=["auto", "text", "ocr"],
                    help="auto = native text if clean else OCR (default)")
    ap.add_argument("--scheme", default=None, help="tag chunks with this scheme (else inferred from parent folder)")
    ap.add_argument("--ocr", default="rapidocr", choices=["rapidocr", "tesseract"], help="OCR backend")
    ap.add_argument("--lang", default="eng", help="Tesseract language(s), e.g. eng or eng+hin")
    ap.add_argument("--tesseract-path", default=None, help="path to tesseract.exe if not on PATH")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    targets = [Path(p) for p in args.pdfs]
    if args.input_dir:
        targets += sorted(Path(args.input_dir).glob("*.pdf"))
    targets = [p for p in targets if p.suffix.lower() == ".pdf"]
    if not targets:
        ap.error("no PDF inputs (pass files or --input-dir)")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # OCR backend is loaded lazily — only if a document actually needs OCR.
    _backend = {}

    def backend_getter():
        if "b" not in _backend:
            print(f"Loading OCR backend '{args.ocr}'…", file=sys.stderr)
            try:
                _backend["b"] = get_ocr_backend(
                    args.ocr, lang=args.lang, tesseract_path=args.tesseract_path
                )
            except RuntimeError as exc:
                sys.exit(str(exc))
        return _backend["b"]

    explicit_scheme = args.scheme
    total = 0
    for pdf in targets:
        if not pdf.exists():
            print(f"! missing: {pdf}", file=sys.stderr)
            continue
        # scheme: explicit flag, else parent folder name (per document)
        args.scheme = explicit_scheme or pdf.parent.name
        result = chunk_pdf(pdf, backend_getter, args)
        (out_dir / f"{pdf.stem}.chunks.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total += result["n_chunks"]
        toks = [c["token_estimate"] for c in result["chunks"]] or [0]
        print(f"[{result['scheme']}/{pdf.name}] src={result['source']} "
              f"{result['n_chunks']} chunks | "
              f"tok {min(toks)}/{round(sum(toks)/len(toks))}/{max(toks)} | "
              f"{result['n_headings']} headings")
        if args.verbose:
            for h in result["outline"]:
                print(f"    {'  ' * (h['level'] - 1)}L{h['level']} [x0={h['x0']} c={h['conf']}] {h['text'][:75]}")

    print(f"\nDone. {total} chunks across {len(targets)} file(s) -> {out_dir}/")


if __name__ == "__main__":
    main()
