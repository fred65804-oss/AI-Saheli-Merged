"""OCR extraction — render each PDF page and read the CLEAN image.

Government PDFs are usually scans with a corrupt embedded OCR text layer (the
visible page is clean, the extractable text is garbage). So we ignore the text
layer, render the page to an image with pypdfium2, and re-OCR it.

The OCR backend is pluggable (``OCRBackend``): RapidOCR now (pip-only, free, no
system install), with Tesseract / a vision model easy to add later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import pypdfium2 as pdfium

try:
    import wordninja
except ImportError:  # optional space-repair
    wordninja = None


@dataclass
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    height: float          # OCR box height — a reliable font-size proxy
    conf: float
    page: int
    # filled during classification
    is_heading: bool = False
    level: int = 0
    num_type: str | None = None


# --------------------------------------------------------------------------- #
# Space repair (RapidOCR drops spaces: "coordinateandevaluatedeliveries")
# --------------------------------------------------------------------------- #
# Domain terms wordninja would otherwise mangle (AYUSH -> "AYU SH"). Kept whole.
_PROTECTED = sorted(
    {
        "poshan", "ayush", "vatika", "vatikas", "anganwadi", "vatsalya", "shakti",
        "pmmvy", "abhiyaan", "maah", "bhawan", "sidha", "unani", "nabl", "fssai",
        "icds", "mowcd", "vhsnc", "vhsnd", "cdpo", "asha", "awc", "awh", "cara",
        "dcpu", "cwc", "nrlm", "mgnrega", "kvks", "campa", "drda", "sakhi",
        "saksham", "niwas", "sambal", "samarthya", "bbbp", "nutri", "gardens",
        "streamlining", "supplementary", "nutrition", "beneficiaries",
        "responsibilities", "malnutrition", "convergence", "panchayat",
        "panchayats", "committee", "development", "guidelines", "monitoring",
        "management", "procurement", "accountability", "nourishment",
        "annexure", "director", "secretary", "government", "ministry",
    },
    key=len,
    reverse=True,
)


# Common short function words that are legitimate pieces of a split.
_COMMON = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "as", "is", "be",
    "by", "for", "its", "it", "we", "us", "are", "was", "per", "not", "may", "can",
    "has", "had", "will", "with", "from", "this", "that", "such", "who", "all",
    "no", "so", "up", "out", "our", "you", "he", "do", "if",
}


def _good_split(pieces: list[str]) -> bool:
    """Reject splits that produce junk fragments (indicates an unknown word was
    mangled, e.g. 'mandatorily' -> 'm and a tori ly')."""
    for p in pieces:
        if len(p) >= 4 or p.lower() in _COMMON:
            continue
        return False
    return True


def _ninja(s: str) -> str:
    pieces = wordninja.split(s)
    return " ".join(pieces) if len(pieces) > 1 and _good_split(pieces) else s


def _ninja_protected(s: str) -> str:
    """Split a run of glued words, keeping protected terms intact and refusing
    low-confidence splits (never mangle an unknown word into gibberish)."""
    low = s.lower()
    for term in _PROTECTED:
        idx = low.find(term)
        if idx != -1:
            before, mid, after = s[:idx], s[idx : idx + len(term)], s[idx + len(term) :]
            parts = []
            if before:
                parts.append(_ninja_protected(before))
            parts.append(mid)
            if after:
                parts.append(_ninja_protected(after))
            return " ".join(p for p in parts if p)
    return _ninja(s)


def _punct_space(text: str) -> str:
    """Deterministic (non-ML) fix for OCR punctuation-merges."""
    text = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", text)       # Assurance,Roles
    text = re.sub(r"(?<=[a-z])\.(?=[A-Z])", ". ", text)       # standards.The
    text = re.sub(r"(?<=[A-Za-z])\((?=[A-Za-z])", " (", text)  # Officer(CDPO
    text = re.sub(r"\)(?=[A-Za-z])", ") ", text)              # )who
    return re.sub(r"[ \t]{2,}", " ", text)


def repair_spacing(text: str) -> str:
    if wordninja is None:
        return _punct_space(text)
    out = []
    for tok in text.split():
        if len(tok) < 8:
            out.append(tok)
            continue
        rebuilt = []
        for m in re.finditer(r"[A-Za-z]+|[^A-Za-z]+", tok):
            s = m.group()
            if s.isalpha() and len(s) >= 8:      # short acronyms (<8) kept as-is
                rebuilt.append(_ninja_protected(s))
            else:
                rebuilt.append(s)
        out.append("".join(rebuilt))
    return _punct_space(" ".join(out))


# --------------------------------------------------------------------------- #
# OCR backend interface + RapidOCR implementation
# --------------------------------------------------------------------------- #
class OCRBackend(Protocol):
    def read(self, image) -> list[tuple[list, str, float]]:
        """Return list of (box[4 xy points], text, confidence)."""
        ...


class RapidOCRBackend:
    """Free, pip-only, offline OCR (ONNX). Good on printed English."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._ocr = RapidOCR()

    def read(self, image):
        results, _ = self._ocr(image)
        return results or []


_TESSERACT_HINT = (
    "Tesseract binary not found. Install it once (free):\n"
    "  Windows: download the installer from "
    "https://github.com/UB-Mannheim/tesseract/wiki  (or: choco install tesseract)\n"
    "           default path C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
    "  For Hindi: tick the 'Hindi' language during install, then use --lang eng+hin\n"
    "Then re-run with --ocr tesseract  (use --tesseract-path to point at the .exe)."
)


def _find_tesseract() -> str | None:
    import os
    import shutil

    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


class TesseractBackend:
    """Higher-accuracy OCR with proper word spacing + Hindi support.

    Requires the free Tesseract binary (one-time install) + ``pytesseract``.
    Produces one result per detected line with a real bbox.
    """

    def __init__(self, lang: str = "eng", cmd: str | None = None) -> None:
        import pytesseract

        self._pt = pytesseract
        self._lang = lang
        resolved = cmd or _find_tesseract()
        if resolved:
            pytesseract.pytesseract.tesseract_cmd = resolved
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:  # binary missing / not runnable
            raise RuntimeError(_TESSERACT_HINT) from exc

    def read(self, image):
        import numpy as np
        from PIL import Image

        img = Image.fromarray(image) if isinstance(image, np.ndarray) else image
        data = self._pt.image_to_data(
            img, lang=self._lang, output_type=self._pt.Output.DICT
        )
        # group words into lines by (block, par, line) keys
        lines: dict[tuple, list[dict]] = {}
        for i, txt in enumerate(data["text"]):
            if not txt.strip() or int(data["conf"][i]) < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            lines.setdefault(key, []).append(
                {"text": txt, "x0": x, "top": y, "x1": x + w, "bottom": y + h,
                 "conf": float(data["conf"][i]) / 100.0}
            )
        results = []
        for words in lines.values():
            words.sort(key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in words)
            x0 = min(w["x0"] for w in words); top = min(w["top"] for w in words)
            x1 = max(w["x1"] for w in words); bottom = max(w["bottom"] for w in words)
            conf = sum(w["conf"] for w in words) / len(words)
            results.append(([[x0, top], [x1, top], [x1, bottom], [x0, bottom]], text, conf))
        return results


def get_ocr_backend(
    name: str = "rapidocr", *, lang: str = "eng", tesseract_path: str | None = None
) -> OCRBackend:
    if name == "rapidocr":
        return RapidOCRBackend()
    if name == "tesseract":
        return TesseractBackend(lang=lang, cmd=tesseract_path)
    raise ValueError(f"unknown OCR backend: {name}")


# --------------------------------------------------------------------------- #
# Render + OCR a whole document
# --------------------------------------------------------------------------- #
def _box_bounds(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def _cluster_visual_lines(boxes: list[dict], page_no: int) -> list[Line]:
    """Merge OCR boxes that sit on the same visual line into one Line.

    RapidOCR often splits a visual line into several boxes (e.g. a bold
    'Subject:' label separate from its title). We regroup by vertical overlap so
    heading text is whole, then sort boxes left-to-right.
    """
    boxes = sorted(boxes, key=lambda b: (b["top"], b["x0"]))
    groups: list[list[dict]] = []
    for b in boxes:
        center = (b["top"] + b["bottom"]) / 2
        if groups:
            g = groups[-1]
            g_center = sum((x["top"] + x["bottom"]) / 2 for x in g) / len(g)
            avg_h = sum(x["bottom"] - x["top"] for x in g) / len(g)
            if abs(center - g_center) <= 0.6 * avg_h:
                g.append(b)
                continue
        groups.append([b])

    lines: list[Line] = []
    for g in groups:
        g = sorted(g, key=lambda b: b["x0"])
        text = repair_spacing(" ".join(b["text"] for b in g))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        lines.append(
            Line(
                text=text,
                x0=round(min(b["x0"] for b in g), 1),
                x1=round(max(b["x1"] for b in g), 1),
                top=round(min(b["top"] for b in g), 1),
                bottom=round(max(b["bottom"] for b in g), 1),
                height=round(_median([b["bottom"] - b["top"] for b in g]), 1),
                conf=round(min(b["conf"] for b in g), 3),
                page=page_no,
            )
        )
    return lines


def _median(vals: list[float]) -> float:
    import statistics

    return statistics.median(vals) if vals else 0.0


def extract_pages_ocr(
    pdf_path: str, backend: OCRBackend, *, dpi: int = 200, min_conf: float = 0.4
) -> tuple[list[list[Line]], float]:
    """OCR every page. Returns (pages_of_lines, page_height_px)."""
    import numpy as np

    scale = dpi / 72.0
    pdf = pdfium.PdfDocument(pdf_path)
    pages: list[list[Line]] = []
    page_height = 0.0
    try:
        for page_no in range(len(pdf)):
            page = pdf[page_no]
            pil = page.render(scale=scale).to_pil().convert("RGB")
            page_height = max(page_height, pil.height)
            results = backend.read(np.asarray(pil))
            boxes: list[dict] = []
            for box, text, conf in results:
                conf = float(conf)
                if conf < min_conf or not text.strip():
                    continue
                x0, top, x1, bottom = _box_bounds(box)
                boxes.append(
                    {"x0": x0, "top": top, "x1": x1, "bottom": bottom,
                     "text": text, "conf": conf}
                )
            pages.append(_cluster_visual_lines(boxes, page_no + 1))
    finally:
        pdf.close()
    return pages, page_height or 1.0
