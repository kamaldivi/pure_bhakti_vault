#!/usr/bin/env python3
"""
scan_iast_fonts.py

Reads PDF files under the folder specified in .env (PDF_FOLDER)
and detects which fonts are used for:
 - IAST transliteration (Latin with diacritics),
 - Devanagari text,
 - Legacy/glyph noise (OCR or non-Unicode glyph fonts: ® √ ∫ † ò ...).

Outputs:
 - scan_summary.csv: one row per PDF with counts and a "profile_guess"
 - scan_details/<pdf_basename>.fonts.json: per-PDF font breakdown + samples

Requirements: pip install pymupdf python-dotenv
"""

import os, sys, json, re, unicodedata, csv, pathlib
from collections import defaultdict, Counter
from typing import Dict, Any, List, Tuple

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    import fitz  # PyMuPDF
except Exception as e:
    print("ERROR: PyMuPDF (fitz) is required. pip install pymupdf", file=sys.stderr)
    raise

IAST_CHARS = set(list("āīūṛṝḷḹṅñṇśṣḍṭṁṃḥ"))
DEVANAGARI_RANGE = (0x0900, 0x097F)
LEGACY_NOISE = set(list("®√∫†ò∂ß¯˙˚¸`´¨ˆ˝˛•…–—"))

def is_devanagari(s: str) -> bool:
    return any(DEVANAGARI_RANGE[0] <= ord(ch) <= DEVANAGARI_RANGE[1] for ch in s)

def has_iast(s: str) -> bool:
    return any(ch in IAST_CHARS for ch in s)

def has_legacy_noise(s: str) -> bool:
    return any(ch in LEGACY_NOISE for ch in s)

def iter_pdf_spans(doc):
    for pno in range(len(doc)):
        page = doc.load_page(pno)
        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "") or ""
                    font = span.get("font", "") or ""
                    size = span.get("size", 0)
                    if text.strip():
                        yield (pno+1, font, size, unicodedata.normalize("NFC", text))

def profile_guess(counts: Dict[str, int]) -> str:
    dev = counts.get("dev_spans", 0)
    iast = counts.get("iast_spans", 0)
    legacy = counts.get("legacy_spans", 0)
    total = max(counts.get("total_spans", 1), 1)

    dev_ratio = dev / total
    iast_ratio = iast / total
    legacy_ratio = legacy / total

    if dev_ratio >= 0.05 and dev > iast and dev > legacy:
        return "unicode_devanagari"
    if iast_ratio >= 0.03 and legacy_ratio <= 0.01:
        return "unicode_iast"
    if legacy_ratio >= 0.01 and legacy >= iast:
        return "legacy_glyph"
    return "plain_latin"

def scan_pdf(pdf_path: str) -> Tuple[Dict[str, int], Dict[str, Any]]:
    counts = Counter()
    per_font = defaultdict(lambda: {"iast_spans":0, "dev_spans":0, "legacy_spans":0,
                                    "other_spans":0, "sizes":Counter(), "samples":[]})
    samples_limit = 5

    with fitz.open(pdf_path) as doc:
        for pno, font, size, text in iter_pdf_spans(doc):
            counts["total_spans"] += 1
            entry = per_font[font]
            entry["sizes"][round(size,2)] += 1

            if is_devanagari(text):
                counts["dev_spans"] += 1
                entry["dev_spans"] += 1
                if len(entry["samples"]) < samples_limit:
                    entry["samples"].append({"page": pno, "type":"dev", "text": text[:160]})
            elif has_iast(text):
                counts["iast_spans"] += 1
                entry["iast_spans"] += 1
                if len(entry["samples"]) < samples_limit:
                    entry["samples"].append({"page": pno, "type":"iast", "text": text[:160]})
            elif has_legacy_noise(text):
                counts["legacy_spans"] += 1
                entry["legacy_spans"] += 1
                if len(entry["samples"]) < samples_limit:
                    entry["samples"].append({"page": pno, "type":"legacy", "text": text[:160]})
            else:
                counts["other_spans"] += 1
                entry["other_spans"] += 1

    details = {"pdf": os.path.basename(pdf_path), "fonts": {}}
    for font, info in sorted(per_font.items(),
                             key=lambda kv: (kv[1]["iast_spans"], kv[1]["dev_spans"], kv[1]["legacy_spans"], sum(kv[1]["sizes"].values())),
                             reverse=True):
        details["fonts"][font] = {
            "iast_spans": info["iast_spans"],
            "dev_spans": info["dev_spans"],
            "legacy_spans": info["legacy_spans"],
            "other_spans": info["other_spans"],
            "sizes": dict(info["sizes"]),
            "samples": info["samples"],
        }
    counts = dict(counts)
    counts["profile_guess"] = profile_guess(counts)
    return counts, details

def main():
    if load_dotenv:
        load_dotenv()

    pdf_folder = os.getenv("PDF_FOLDER")
    if not pdf_folder:
        print("ERROR: PDF_FOLDER is not set in .env", file=sys.stderr)
        sys.exit(2)

    pdf_folder = os.path.expanduser(pdf_folder)
    if not os.path.isdir(pdf_folder):
        print(f"ERROR: PDF_FOLDER does not exist: {pdf_folder}", file=sys.stderr)
        sys.exit(2)

    out_dir = os.path.join(os.getcwd(), "scan_details")
    os.makedirs(out_dir, exist_ok=True)
    summary_rows = []

    pdf_paths: List[str] = []
    for root, dirs, files in os.walk(pdf_folder):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, f))

    if not pdf_paths:
        print(f"No PDFs found under {pdf_folder}")
        return

    for path in sorted(pdf_paths):
        try:
            counts, details = scan_pdf(path)
        except Exception as e:
            print(f"ERROR scanning {path}: {e}", file=sys.stderr)
            counts = {"total_spans":0, "iast_spans":0, "dev_spans":0, "legacy_spans":0, "other_spans":0, "profile_guess":"error"}
            details = {"pdf": os.path.basename(path), "error": str(e)}

        summary_rows.append({
            "pdf": os.path.relpath(path, pdf_folder),
            "total_spans": counts.get("total_spans", 0),
            "iast_spans": counts.get("iast_spans", 0),
            "dev_spans": counts.get("dev_spans", 0),
            "legacy_spans": counts.get("legacy_spans", 0),
            "other_spans": counts.get("other_spans", 0),
            "profile_guess": counts.get("profile_guess", ""),
        })

        json_path = os.path.join(out_dir, pathlib.Path(path).stem + ".fonts.json")
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(details, jf, ensure_ascii=False, indent=2)

    csv_path = "scan_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=["pdf","total_spans","iast_spans","dev_spans","legacy_spans","other_spans","profile_guess"])
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    print(f"Wrote summary: {csv_path}")
    print(f"Wrote per-file details under: {out_dir}")
    print("Tip: 'profile_guess' helps choose a transliteration path:")
    print("  - unicode_devanagari → transliterate Devanagari → IAST")
    print("  - unicode_iast       → text already IAST; minimal cleanup")
    print("  - legacy_glyph       → apply font-specific CHAR_MAP + sequence fixes")
    print("  - plain_latin        → probably English/plain Latin text")

if __name__ == "__main__":
    main()
