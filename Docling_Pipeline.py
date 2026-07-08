"""
Docling Complete Page Chunker — Handles ALL Nested Heading Scenarios
====================================================================

Handles:
✅ H1 on page 1, H2/H3 on later pages — sticky context
✅ Multiple headings on same page at different levels
✅ Mid-page heading change (text before + after heading on same page)
✅ Deeply nested H1 > H2 > H3 > H4 stack
✅ New H2 resets H3/H4 but keeps H1 (correct level trimming)
✅ New H1 resets entire stack
✅ Text-only pages carry correct full breadcrumb
✅ Same page has H2 then H3 then H2 again (multiple switches)

Output per sub-chunk:
  - heading_path  : full breadcrumb at that exact point
  - page_number   : which page
  - is_continuation: whether heading came from a previous page
  - segment_index : position within the page (handles mid-page heading changes)

Install:
    pip install docling

Usage:
    python docling_full_nested_chunker.py --pdf file.pdf
    python docling_full_nested_chunker.py --pdf file.pdf --merge-same-section
    python docling_full_nested_chunker.py --pdf file.pdf --split-on-heading-change
"""

import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────
# Label helpers
# ──────────────────────────────────────────────────────────

try:
    from docling_core.types.doc import DocItemLabel
    _HEADING_LABELS = {DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE}
    _TEXT_LABELS = {
        DocItemLabel.TEXT, DocItemLabel.PARAGRAPH,
        DocItemLabel.LIST_ITEM, DocItemLabel.CAPTION,
        DocItemLabel.FOOTNOTE, DocItemLabel.TABLE,
    }
    _LABELS_ENUM = True
except ImportError:
    _HEADING_LABELS = {"section_header", "title"}
    _TEXT_LABELS = {"text", "paragraph", "list_item", "caption", "footnote", "table"}
    _LABELS_ENUM = False


def _lbl(item):
    l = getattr(item, "label", None)
    return l.value if hasattr(l, "value") else str(l) if l else "unknown"


def _is_heading(item) -> bool:
    l = getattr(item, "label", None)
    if l is None:
        return False
    return (l in _HEADING_LABELS) if _LABELS_ENUM else (_lbl(item) in _HEADING_LABELS)


def _is_text(item) -> bool:
    l = getattr(item, "label", None)
    if l is None:
        return False
    return (l in _TEXT_LABELS) if _LABELS_ENUM else (_lbl(item) in _TEXT_LABELS)


def _heading_level(item) -> int:
    """Return 1-based heading level. 1=H1, 2=H2, etc."""
    lbl = _lbl(item)
    if lbl == "title":
        return 1
    lv = getattr(item, "level", None)
    if lv is not None:
        return max(1, int(lv))
    return 2   # default SECTION_HEADER → H2


def _page(item) -> Optional[int]:
    prov = getattr(item, "prov", None)
    if prov is None:
        return None
    if isinstance(prov, list):
        if prov:
            return getattr(prov[0], "page_no", None)
        return None
    return getattr(prov, "page_no", None)


def _text(item) -> str:
    txt = getattr(item, "text", None)
    if txt:
        return txt.strip()
    if hasattr(item, "export_to_text"):
        return item.export_to_text().strip()
    return ""

def iterate_doc_items(doc):
    try:
        yield from doc.iterate_items()
    except AttributeError:
        for item in doc.items:
            yield item, None


# ──────────────────────────────────────────────────────────
# HeadingStack — the core state machine
# ──────────────────────────────────────────────────────────

class HeadingStack:
    """
    Maintains heading hierarchy across the entire document.

    Rules:
    - New H1  → clears entire stack, sets H1
    - New H2  → pops everything H2 and deeper, keeps H1, appends H2
    - New H3  → pops everything H3 and deeper, keeps H1+H2, appends H3
    - etc.

    This means:
      H1:Chapter1 → H2:Sec1.1 → H3:Sub1.1.1
      Then H2:Sec1.2 arrives → stack becomes [Chapter1, Sec1.2]  ✅
      Then H3:Sub1.2.1 arrives → stack becomes [Chapter1, Sec1.2, Sub1.2.1]  ✅
    """

    def __init__(self):
        # internal: list of (level, text) tuples
        self._stack: list[tuple[int, str]] = []

    def update(self, level: int, text: str):
        # Remove all entries at this level or deeper
        self._stack = [(l, t) for l, t in self._stack if l < level]
        self._stack.append((level, text))

    @property
    def path(self) -> list[str]:
        """Return current heading breadcrumb as list of strings."""
        return [t for _, t in self._stack]

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def current_level(self) -> int:
        return self._stack[-1][0] if self._stack else 0

    @property
    def current_title(self) -> str:
        return self._stack[-1][1] if self._stack else ""

    def snapshot(self) -> list[str]:
        return list(self.path)

    def __repr__(self):
        return " > ".join(self.path) or "(empty)"


# ──────────────────────────────────────────────────────────
# Raw item collection
# ──────────────────────────────────────────────────────────

@dataclass
class RawItem:
    text: str
    page: int
    is_heading: bool
    level: int                      # 0 if not heading
    heading_path: list[str]         # path AFTER this item updates the stack
    item_index: int                 # global reading order


def collect_raw_items(doc) -> list[RawItem]:
    """
    Walk all doc items in reading order.
    Apply HeadingStack updates immediately so every item
    knows the exact heading context active after it was seen.
    """
    stack = HeadingStack()
    raw: list[RawItem] = []
    idx = 0

    for item, _ in iterate_doc_items(doc):
        t = _text(item)
        if not t:
            continue

        pg = _page(item) or (raw[-1].page if raw else 1)
        heading = _is_heading(item)
        level = _heading_level(item) if heading else 0

        if heading:
            stack.update(level, t)

        raw.append(RawItem(
            text=t,
            page=pg,
            is_heading=heading,
            level=level,
            heading_path=stack.snapshot(),
            item_index=idx,
        ))
        idx += 1

    return raw


# ──────────────────────────────────────────────────────────
# Chunk dataclass
# ──────────────────────────────────────────────────────────

@dataclass
class Chunk:
    chunk_id: str
    page_number: int
    segment_index: int              # 0-based position within page (for mid-page splits)
    heading_path: list[str]         # full breadcrumb at this point
    section_title: str
    heading_level: int
    active_headings_on_page: list[str]   # headings that START on this page
    is_continuation: bool           # heading came from a previous page
    continued_from_page: Optional[int]
    content: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id":               self.chunk_id,
            "page_number":            self.page_number,
            "segment_index":          self.segment_index,
            "heading_path":           self.heading_path,
            "section_title":          self.section_title,
            "heading_level":          self.heading_level,
            "active_headings_on_page":self.active_headings_on_page,
            "is_continuation":        self.is_continuation,
            "continued_from_page":    self.continued_from_page,
            "content":                self.content,
            "metadata":               self.metadata,
        }


# ──────────────────────────────────────────────────────────
# Build chunks: TWO modes
# ──────────────────────────────────────────────────────────

def build_chunks_split_on_heading_change(
    raw: list[RawItem],
    source: str,
) -> list[Chunk]:
    """
    MODE A — Split on every heading change (most precise).

    Within a single page, if the heading_path changes mid-page
    (e.g. H2 appears after some text), we emit SEPARATE chunks
    for the text before and after the heading change.

    Result: each chunk has exactly ONE consistent heading_path.
    Best for RAG — no ambiguity about which section text belongs to.
    """
    chunks: list[Chunk] = []
    counter = [0]

    def nid():
        counter[0] += 1
        return f"chunk_{counter[0]:04d}"

    # Track what heading was active at END of previous page
    prev_page_end_path: list[str] = []
    # Track which page each heading title was first seen on
    heading_first_seen: dict[str, int] = {}

    # Group into (page, heading_path) segments
    # Each time heading_path changes → new segment, even mid-page

    @dataclass
    class Segment:
        page: int
        heading_path: list[str]
        heading_level: int
        items: list[RawItem] = field(default_factory=list)
        headings_introduced: list[str] = field(default_factory=list)

    segments: list[Segment] = []
    current_seg: Optional[Segment] = None

    for item in raw:
        # Register first-seen page for headings
        if item.is_heading:
            if item.text not in heading_first_seen:
                heading_first_seen[item.text] = item.page

        path_key = tuple(item.heading_path)

        if current_seg is None or tuple(current_seg.heading_path) != path_key or current_seg.page != item.page:
            # Start new segment
            seg = Segment(
                page=item.page,
                heading_path=item.heading_path,
                heading_level=item.level if item.is_heading else (
                    len(item.heading_path)  # depth = approximate level
                ),
            )
            segments.append(seg)
            current_seg = seg

        current_seg.items.append(item)
        if item.is_heading:
            current_seg.headings_introduced.append(item.text)

    # Convert segments → chunks
    seg_page_counter: dict[int, int] = {}  # page → how many segments so far

    for seg in segments:
        # Build content
        parts = []
        for it in seg.items:
            if it.is_heading:
                prefix = "#" * it.level
                parts.append(f"{prefix} {it.text}")
            else:
                parts.append(it.text)
        content = "\n\n".join(parts).strip()
        if not content:
            continue

        # Continuation detection: was this heading_path already active before this page?
        is_cont = False
        cont_from = None
        if seg.heading_path:
            deepest = seg.heading_path[-1]
            first_seen_page = heading_first_seen.get(deepest)
            if first_seen_page is not None and first_seen_page < seg.page:
                is_cont = True
                cont_from = first_seen_page

        seg_idx = seg_page_counter.get(seg.page, 0)
        seg_page_counter[seg.page] = seg_idx + 1

        # All headings visible anywhere on this page
        all_page_headings = [
            it.text for it in raw
            if it.page == seg.page and it.is_heading
        ]

        chunks.append(Chunk(
            chunk_id=nid(),
            page_number=seg.page,
            segment_index=seg_idx,
            heading_path=seg.heading_path,
            section_title=seg.heading_path[-1] if seg.heading_path else "",
            heading_level=seg.heading_level,
            active_headings_on_page=list(dict.fromkeys(all_page_headings)),  # deduped, ordered
            is_continuation=is_cont,
            continued_from_page=cont_from,
            content=content,
            metadata={"source": source, "segment_item_count": len(seg.items)},
        ))

    return chunks


def build_chunks_one_per_page(
    raw: list[RawItem],
    source: str,
) -> list[Chunk]:
    """
    MODE B — One chunk per page (simpler, standard page-wise).

    Uses the heading_path at END of page (most specific context).
    All text on the page merged into one chunk.
    Mid-page heading changes → noted in active_headings_on_page,
    but content is merged (heading_path = last active on page).
    """
    from collections import defaultdict

    page_items: dict[int, list[RawItem]] = defaultdict(list)
    for item in raw:
        page_items[item.page].append(item)

    heading_first_seen: dict[str, int] = {}
    for item in raw:
        if item.is_heading and item.text not in heading_first_seen:
            heading_first_seen[item.text] = item.page

    chunks: list[Chunk] = []
    counter = [0]
    prev_path: list[str] = []

    def nid():
        counter[0] += 1
        return f"page_{counter[0]:04d}"

    for pg in sorted(page_items.keys()):
        items = page_items[pg]

        # heading_path = path active at END of page
        end_path = items[-1].heading_path if items else prev_path
        heading_path = end_path if end_path else prev_path

        headings_on_page = [it.text for it in items if it.is_heading]
        heading_level = len(heading_path)

        # Continuation?
        is_cont = False
        cont_from = None
        if heading_path:
            deepest = heading_path[-1]
            fp = heading_first_seen.get(deepest)
            if fp is not None and fp < pg:
                is_cont = True
                cont_from = fp

        # Build content
        parts = []
        for it in items:
            if it.is_heading:
                prefix = "#" * it.level
                parts.append(f"{prefix} {it.text}")
            else:
                parts.append(it.text)
        content = "\n\n".join(parts).strip()
        if not content:
            continue

        chunks.append(Chunk(
            chunk_id=nid(),
            page_number=pg,
            segment_index=0,
            heading_path=heading_path,
            section_title=heading_path[-1] if heading_path else "",
            heading_level=heading_level,
            active_headings_on_page=headings_on_page,
            is_continuation=is_cont,
            continued_from_page=cont_from,
            content=content,
            metadata={"source": source, "item_count": len(items)},
        ))
        prev_path = end_path

    return chunks


# ──────────────────────────────────────────────────────────
# Optional: merge continuation chunks of same section
# ──────────────────────────────────────────────────────────

def merge_same_section(chunks: list[Chunk]) -> list[Chunk]:
    """
    Merge consecutive chunks that share the same heading_path
    (i.e. section spans multiple pages or mid-page segments).
    """
    if not chunks:
        return chunks

    merged = []
    buf = None

    for c in chunks:
        if buf is None:
            buf = c
            continue
        if c.heading_path == buf.heading_path:
            buf = Chunk(
                chunk_id=buf.chunk_id,
                page_number=buf.page_number,
                segment_index=buf.segment_index,
                heading_path=buf.heading_path,
                section_title=buf.section_title,
                heading_level=buf.heading_level,
                active_headings_on_page=list(dict.fromkeys(
                    buf.active_headings_on_page + c.active_headings_on_page
                )),
                is_continuation=buf.is_continuation,
                continued_from_page=buf.continued_from_page,
                content=buf.content + "\n\n" + c.content,
                metadata={
                    **buf.metadata,
                    "merged_pages": buf.metadata.get("merged_pages", [buf.page_number])
                                    + [c.page_number],
                },
            )
        else:
            merged.append(buf)
            buf = c

    if buf:
        merged.append(buf)
    return merged


# ──────────────────────────────────────────────────────────
# Load PDF
# ──────────────────────────────────────────────────────────

def load_doc(pdf_path: str):
    """Load a digital PDF using Docling 2.x with OCR disabled."""
    from docling.document_converter import (
        DocumentConverter,
        PdfFormatOption,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )

    result = converter.convert(source=pdf_path)
    return result.document


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def run(
    pdf_path: str,
    out_path: str,
    split_on_heading_change: bool = True,
    merge: bool = False,
):
    source = Path(pdf_path).name

    import docling
    #print(f"Docling version: {docling.__version__}")
    print(f"\n[1/4] Loading: {pdf_path}")
    doc = load_doc(pdf_path)

    print("[2/4] Collecting items (HeadingStack active)...")
    raw = collect_raw_items(doc)
    print(f"  Items: {len(raw)} | "
          f"Headings: {sum(1 for r in raw if r.is_heading)} | "
          f"Text blocks: {sum(1 for r in raw if not r.is_heading)}")

    print("[3/4] Building chunks...")
    if split_on_heading_change:
        print("  Mode: split on heading change (most precise)")
        chunks = build_chunks_split_on_heading_change(raw, source)
    else:
        print("  Mode: one chunk per page")
        chunks = build_chunks_one_per_page(raw, source)

    if merge:
        before = len(chunks)
        chunks = merge_same_section(chunks)
        print(f"  Merged: {before} → {len(chunks)} chunks")

    print(f"[4/4] Writing {len(chunks)} chunks → {out_path}")

    output = {
        "source": source,
        "total_chunks": len(chunks),
        "mode": "split_on_heading_change" if split_on_heading_change else "one_per_page",
        "merged": merge,
        "chunks": [c.to_dict() for c in chunks],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done → {out_path}\n")

    # Visual preview
    print("=" * 65)
    print("CHUNK PREVIEW")
    print("=" * 65)
    for c in chunks[:8]:
        flag = "⟳" if c.is_continuation else "▶"
        path = " > ".join(c.heading_path) if c.heading_path else "(no heading)"
        seg  = f" seg[{c.segment_index}]" if c.segment_index > 0 else ""
        cont = f" ← from pg {c.continued_from_page}" if c.continued_from_page else ""
        print(f"\n  {flag} Page {c.page_number}{seg}{cont}")
        print(f"     Path    : {path}")
        if c.active_headings_on_page:
            print(f"     Headings on page: {c.active_headings_on_page}")
        print(f"     Content : {c.content[:100].replace(chr(10),' ')}...")
    print("=" * 65)


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Full nested heading-aware page chunker for Docling"
    )
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", default="nested_chunks.json")
    parser.add_argument(
        "--split-on-heading-change", action="store_true", default=True,
        help="Split chunk when heading changes mid-page (default: True)"
    )
    parser.add_argument(
        "--one-per-page", action="store_true",
        help="One chunk per page (overrides --split-on-heading-change)"
    )
    parser.add_argument(
        "--merge-same-section", action="store_true",
        help="Merge consecutive chunks with same heading_path"
    )
    args = parser.parse_args()

    run(
        pdf_path=args.pdf,
        out_path=args.out,
        split_on_heading_change=not args.one_per_page,
        merge=args.merge_same_section,
    )
    