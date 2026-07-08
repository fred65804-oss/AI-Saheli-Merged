"""Clean the scheme chunk corpus before indexing.

Two operations, both aimed at retrieval quality:

  1. QUARANTINE non-authoritative documents — press releases and website
     scrapes that are event news / page chrome, not scheme guidance. They
     pollute retrieval (an inauguration announcement outranking a nutrition
     passage) and their scraped chunks are mostly navigation boilerplate.

  2. CLEAN every surviving chunk's text — strip private-use-area icon glyphs
     (Font Awesome from web scrapes), website nav/chrome tokens, and normalise
     the OCR habit of using "©" as a bullet marker; then drop chunks that are
     too short or too non-textual to carry an answer.

Both ``text`` (reranked + shown) and ``contextualized_text`` (embedded) are
cleaned, so the embedding, the reranker, and the displayed citation all see
the same clean prose.

Reads   rag/chunks/<scheme>/*.chunks.json
Writes  rag/chunks_clean/<scheme>/*.chunks.json   (review, then swap in)

Run:  python -m rag.clean_chunks
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent
SRC_GLOB = str(_ROOT / "chunks" / "*" / "*.chunks.json")
OUT_DIR = _ROOT / "chunks_clean"

# Documents dropped wholesale: press releases, a scraped website page, and the
# POSHAN e-Bulletins (magazine/newsletter prose — "Dear Readers…", event write-
# ups, Jan Andolan narrative — not scheme guidance; they polluted Poshan
# retrieval, e.g. an inauguration write-up outranking nutrition passages).
QUARANTINE_DOCS = {
    "Press Release_Press Information Bureau.pdf",
    "Press Release_Press_Mission_Shakti.pdf",
    "Short_Website_info_Mission_Shakti.pdf",
    "Poshan_1.pdf",
    "Poshan_2.pdf",
}

# CID font-extraction artifacts: some PDFs embed fonts without a unicode map,
# so extraction interleaves each real character with its glyph id —
# "A(cid:65)B(cid:66)R(cid:82)..." is really "ABBR...". The real letters are
# already present; the (cid:NN) tokens are pure noise, so dropping them
# RECOVERS the text rather than us discarding the whole doc as garbage.
_CID = re.compile(r"\(cid:\d+\)")

# Private-use-area codepoints — Font Awesome / icon glyphs left by web scrapes.
_PUA = re.compile(
    "[-\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]"
)

# Website navigation / chrome fragments that ride along on scraped pages.
_NAV = re.compile(
    "|".join(
        [
            r"skip to main content",
            r"screen reader access",
            r"back to top",
            r"select language",
            r"font size",
            r"a\+\s*a-",
            r"National Cyber Crime WHL",
            r"Tele\s*Manas",
            r"Helpline For Emergency",
            r"\bLOGIN\b",
            r"Menu\s*☰",
            r"☰",
        ]
    ),
    re.IGNORECASE,
)


def clean_text(t: str) -> str:
    if not t:
        return t
    t = _CID.sub("", t)               # recover cid-interleaved text FIRST
    t = _PUA.sub(" ", t)
    t = t.replace("©", "•")          # OCR used © as a bullet; normalise it
    t = _NAV.sub(" ", t)
    t = t.replace(" : ", ". ")        # scrape colon-lists → sentence breaks
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_junk(t: str) -> bool:
    """A cleaned chunk with no answer value: too short, or too non-textual
    (menus, number soup, glyph residue)."""
    if len(t) < 80:
        return True
    textual = sum(c.isalpha() or c.isspace() for c in t)
    return textual / max(len(t), 1) < 0.65


def main() -> None:
    files = sorted(glob.glob(SRC_GLOB))
    kept_docs = dropped_docs = 0
    kept_chunks = dropped_junk = cleaned = 0

    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        doc = d["doc"]
        if doc in QUARANTINE_DOCS:
            dropped_docs += 1
            print(f"  QUARANTINE  {doc}  ({len(d['chunks'])} chunks dropped)")
            continue

        out_chunks = []
        for ch in d["chunks"]:
            raw = ch.get("text", "")
            ct = clean_text(raw)
            if is_junk(ct):
                dropped_junk += 1
                continue
            if ct != raw:
                cleaned += 1
            ch["text"] = ct
            ch["contextualized_text"] = clean_text(ch.get("contextualized_text", raw))
            out_chunks.append(ch)

        d["chunks"] = out_chunks
        d["n_chunks"] = len(out_chunks)
        kept_docs += 1
        kept_chunks += len(out_chunks)

        rel = Path(f).relative_to(_ROOT / "chunks")
        dest = OUT_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"\nDocs: kept {kept_docs}, quarantined {dropped_docs}\n"
        f"Chunks: kept {kept_chunks}, cleaned-text {cleaned}, dropped-junk {dropped_junk}\n"
        f"Wrote cleaned corpus to {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
