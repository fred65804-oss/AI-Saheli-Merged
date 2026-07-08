# PDF Chunker — hierarchy-aware semantic chunking for scanned government PDFs

A **standalone, free, fully-local** tool (no API keys). It turns scanned/OCR'd
government PDFs into retrieval-ready JSON chunks with a **hierarchical heading
path** (`H1 > H2 > H3 > H4`), page spans, and clean text.

> Not linked to any other project in this repo — copy the folder anywhere.

## The key idea
Scanned government PDFs have a **corrupt embedded text layer** (you get
`Subiect`, `matnutrition`) but a **clean visible page**. So we ignore the text
layer, **render each page to an image and re-OCR it**, then chunk the clean text.

```
render page (pypdfium2) → OCR clean image (RapidOCR) → repair spacing
  → strip header/footer/stamps → detect headings → MERGE wrapped headings
  → build H1..H4 hierarchy → sentence-pack to ~256 tokens → ONE JSON file
```

## Install & run
```bash
pip install -r requirements.txt          # all pip, no system install (Windows incl.)

python chunk_pdfs.py doc.pdf --out ./out          # one file
python chunk_pdfs.py --input-dir ./pdfs --out ./out --dpi 200 -v
```
First run downloads the small RapidOCR models (~15 MB), then works offline.
Output: **one** `<name>.chunks.json` per PDF (with `outline` + `chunks` inside).

## OCR backends (pluggable)
| Backend | Flag | Notes |
|---|---|---|
| **RapidOCR** (default) | `--ocr rapidocr` | Free, pip-only, no system install, offline. Occasionally drops spaces (repaired below). |
| **Tesseract** (recommended for production) | `--ocr tesseract` | Best accuracy + proper spacing + **Hindi**. One-time free binary install + `pip install pytesseract`. |

### Space repair (RapidOCR path)
RapidOCR sometimes glues words (`coordinateandevaluate`). We repair this with:
- **wordninja**, but **guarded**: a domain glossary keeps `POSHAN/AYUSH/Anganwadi/PMMVY…`
  intact, and low-confidence splits are refused so unknown words are never
  mangled (`mandatorily` stays `mandatorily`, not `m and a tori ly`).
- **Deterministic punctuation spacing** (no ML): `Assurance,Roles → Assurance, Roles`,
  `standards.The → standards. The`, `Officer(CDPO)who → Officer (CDPO) who`.

For flawless spacing and Hindi, use Tesseract.

## Heading detection — the signal cascade
On clean OCR text no single signal is enough, so headings use a cascade:
1. **Numbering** (most reliable): `Subject:`, `Annexure`, `1.`, `2.3`, `A.`, `(C)`, `(a)`.
   Years (`2021.`), ordinals (`2nd`), and numbered *paragraphs* (full sentences) are rejected.
2. **Colon-terminated** short lines (`At District Level:`).
3. **ALL-CAPS** short lines.
4. **Box height** (font-size proxy) — only when its variance is low.

**Multi-line headings are merged** (fixes "half headings"): a wrapped title like the
multi-line `Subject:` block is joined into one heading. Levels nest by numbering,
then by indentation (x0) for un-numbered headings.

## Output schema
```json
{
  "doc": "aaaaa.pdf", "pages": 18, "n_headings": 24, "n_chunks": 36,
  "outline": [ {"level":2,"text":"1. Quality Assurance:","x0":239.6,"conf":0.97,"page":1}, ... ],
  "chunks": [
    {
      "chunk_id": "aaaaa_0006", "doc": "aaaaa.pdf",
      "page_start": 2, "page_end": 3,
      "heading": "A. At District Level:",
      "heading_path": ["Subject: Streamlining Guidelines ...", "2. Supply-Chain Management:", "A. At District Level:"],
      "heading_path_str": "Subject: ... > 2. Supply-Chain Management: > A. At District Level:",
      "level": 3, "heading_x0": 230.2, "heading_conf": 0.941,
      "text": "The District Magistrate shall be the Nodal Point ...",
      "contextualized_text": "Subject: ... > A. At District Level:\n\nThe District ...",
      "token_estimate": 60, "char_count": 327
    }
  ]
}
```
Use `contextualized_text` for embeddings (prepends the heading path — contextual
retrieval); use `text` if you store metadata separately.

## Options
| Flag | Default | Meaning |
|---|---|---|
| `--out` | `chunks_out` | output directory |
| `--dpi` | `200` | render DPI for OCR |
| `--ocr` | `rapidocr` | `rapidocr` or `tesseract` |
| `--target-tokens` | `256` | target chunk size |
| `--overlap` | `0.15` | overlap as fraction of target |
| `--min-tokens` | `40` | merge a smaller trailing chunk into the previous |
| `--tokenizer` | `heuristic` | `heuristic` (no deps) or `tiktoken` (exact) |
| `-v/--verbose` | off | print the heading outline |

## Limitations (honest)
- OCR text is only as good as the engine. RapidOCR (default) has occasional
  residual spacing/character quirks (`nutrition al`, `ICDs`); **Tesseract** or a
  future vision backend fixes most of these.
- Signature/stamp fragments on the last page can occasionally register as short
  headings.
- Complex tables are read as text, not reconstructed as tables.
