#!/usr/bin/env python3
"""
transleterate_util.py

Font-aware Sanskrit transliteration cleanup for extracted PDF text.

- Loads BASE_CHAR_MAP plus per-font overrides (from known families).
- Optionally reads a per-PDF font profile JSON (produced by scan_iast_fonts.py)
  to decide which overrides to apply.
- Provides a test runner that reads TEST_PDF_NAME and TEST_PAGE_NUMBER from .env,
  extracts that page using PyMuPDF, and prints cleaned text.

Requirements:
  pip install python-dotenv pymupdf
"""

from __future__ import annotations
import os, re, json, unicodedata, pathlib
from collections import Counter
from typing import Dict, List, Any, Optional

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# -------------------- Base & Overrides --------------------

BASE_CHAR_MAP: Dict[str, str] = {
    # Core glyph fixes
    '®':'ṛ','ß':'ṣ','√':'ś','ò':'ḍ','†':'ṭ','∫':'ṅ','∂':'ḍ',
    '¯':'ā','˙':'ḥ','˚':'',
    # latin diacritic cleanups commonly seen in legacy exports
    'ä':'ā','Ä':'Ā','é':'ī','É':'Ī','á':'ā','Á':'Ā','î':'ī','Î':'Ī','û':'ū','Û':'Ū',
}

# Per-font overrides discovered from your scans. These are merged over BASE_CHAR_MAP
FONT_OVERRIDES: Dict[str, Dict[str, str]] = {
    # Prabandhavali: DiaJansonText-* → √ as ṇ; ç/Ç → ś/Ś; å/Å → ā/Ā; ˙ → ḥ
    "DiaJansonText-Roman": {'√':'ṇ','ç':'ś','Ç':'Ś','å':'ā','Å':'Ā','˙':'ḥ'},
    "DiaJansonText-Bold":  {'√':'ṇ','ç':'ś','Ç':'Ś','å':'ā','Å':'Ā','˙':'ḥ'},

    # Prema-pradīpa: RamaGaramondPlus → ä/é/ò/ë usage
    "RamaGaramondPlus":    {'ä':'ā','Ä':'Ā','é':'ī','É':'Ī','ò':'ḍ','ë':'ṇ','Ë':'Ṇ'},

    # Upadeśāmṛta: BalaramU-* mostly clean IAST → no overrides needed
}

# Regex-based sequence fixes (applied after char mapping)
SEQUENCE_FIXES: List[tuple[str, str]] = [
    (r'ṛr', 'ār'),               # ā mis-OCR as ṛ + r
]

# Protect legitimate ṛ contexts so aggressive fixes don't touch them
VALID_R_PATTERNS = [
    r'kṛ', r'dṛ', r'pṛ', r'bṛ', r'mṛ', r'tṛ', r'nṛ', r'smṛ',
    r'ṛṣi', r'Ṛg', r'ṛtu', r'kṛṣ'
]

def _protect_real_r(text: str) -> tuple[str, Dict[str, str]]:
    protect_map: Dict[str, str] = {}
    for i, pat in enumerate(VALID_R_PATTERNS):
        placeholder = f'⟪R{i}⟫'
        text = re.sub(pat, placeholder, text)
        protect_map[placeholder] = re.sub(r'\\','', pat)
    return text, protect_map

def _unprotect_real_r(text: str, protect_map: Dict[str,str]) -> str:
    for ph, original in protect_map.items():
        text = text.replace(ph, original)
    return text

# -------------------- Font profile helpers --------------------

def _dominant_fonts_from_json(fonts_json: Dict[str, Any], top_n: int = 3) -> List[str]:
    fonts = fonts_json.get("fonts", {})
    scored = []
    for name, stats in fonts.items():
        score = stats.get("iast_spans",0) + stats.get("legacy_spans",0) + stats.get("other_spans",0)
        scored.append((score, name))
    scored.sort(reverse=True)
    return [name for _, name in scored[:top_n]]

def _merge_char_maps(dominant_fonts: List[str]) -> Dict[str,str]:
    merged = dict(BASE_CHAR_MAP)
    for font in dominant_fonts:
        ov = FONT_OVERRIDES.get(font)
        if ov:
            merged.update(ov)
    return merged

def load_font_profile_json(font_json_dir: str, pdf_name: str) -> Optional[Dict[str, Any]]:
    """
    Load the scan_details JSON by stem from font_json_dir.
    pdf_name can be either a file name (with .pdf) or a stem.
    """
    stem = pathlib.Path(pdf_name).stem
    candidate = pathlib.Path(font_json_dir) / f"{stem}.fonts.json"
    if candidate.is_file():
        with open(candidate, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# -------------------- Public API --------------------

def transliterate_text(text: str, fonts_json: Optional[Dict[str, Any]] = None) -> str:
    """
    Clean up transliteration using base char map + optional font-aware overrides + sequence fixes.
    """
    s = unicodedata.normalize('NFC', text)
    # Choose char map
    char_map = BASE_CHAR_MAP if not fonts_json else _merge_char_maps(_dominant_fonts_from_json(fonts_json))
    # Protect legitimate ṛ contexts
    s, ph = _protect_real_r(s)
    # Apply char map
    for bad, good in char_map.items():
        s = s.replace(bad, good)
    # Apply sequence fixes
    for pat, repl in SEQUENCE_FIXES:
        s = re.sub(pat, repl, s)
    # Unprotect
    s = _unprotect_real_r(s, ph)
    return unicodedata.normalize('NFC', s)

def transliterate_page(pdf_path: str, page_number: int, font_json_dir: Optional[str] = None) -> str:
    """
    Extract text from a PDF page and transliterate with font-aware mapping.
    Requires PyMuPDF.
    """
    import fitz  # lazy import
    # Load font profile JSON if available
    fonts_json = None
    if font_json_dir:
        fonts_json = load_font_profile_json(font_json_dir, os.path.basename(pdf_path))

    with fitz.open(pdf_path) as doc:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f"page_number out of range: 1..{len(doc)}")
        page = doc.load_page(page_number-1)
        txt = page.get_text("text")
    return transliterate_text(txt, fonts_json=fonts_json)

# -------------------- Test runner --------------------

def _env(var: str, default: Optional[str]=None) -> Optional[str]:
    v = os.getenv(var, default)
    return v

def run_env_test() -> None:
    """
    Uses .env variables:
      - PDF_FOLDER: root folder with PDFs
      - FONT_JSON_DIR: directory containing *.fonts.json (default: ./scan_details)
      - TEST_PDF_NAME: file name of the PDF to test (must be found under PDF_FOLDER)
      - TEST_PAGE_NUMBER: 1-based page number to test

    Prints raw vs transliterated snippet.
    """
    if load_dotenv:
        load_dotenv()

    pdf_root = _env("PDF_FOLDER")
    if not pdf_root or not os.path.isdir(pdf_root):
        raise SystemExit("PDF_FOLDER not set or not a directory in .env")

    font_json_dir = _env("FONT_JSON_DIR", os.path.join(os.getcwd(), "scan_details"))
    test_pdf_name = _env("TEST_PDF_NAME")
    test_page_number = int(_env("TEST_PAGE_NUMBER", "1"))

    if not test_pdf_name:
        raise SystemExit("TEST_PDF_NAME not set in .env")

    # Resolve PDF path by searching under PDF_FOLDER
    target_path = None
    for root, dirs, files in os.walk(pdf_root):
        for f in files:
            if f.lower().endswith(".pdf") and f == test_pdf_name:
                target_path = os.path.join(root, f)
                break
        if target_path: break

    if not target_path:
        raise SystemExit(f"Could not find {test_pdf_name} under {pdf_root}")

    # Extract + transliterate
    import fitz
    with fitz.open(target_path) as doc:
        if test_page_number < 1 or test_page_number > len(doc):
            raise SystemExit(f"TEST_PAGE_NUMBER out of range: 1..{len(doc)}")
        page = doc.load_page(test_page_number-1)
        raw_text = page.get_text("text")

    fonts_json = load_font_profile_json(font_json_dir, test_pdf_name)
    cleaned = transliterate_text(raw_text, fonts_json=fonts_json)

    # Show short comparison
    print("="*80)
    print(f"PDF: {test_pdf_name}  Page: {test_page_number}")
    print(f"Font profile: {('loaded from '+font_json_dir) if fonts_json else 'not found (BASE only)'}")
    print("- RAW (first 600 chars) -")
    print(raw_text.replace("\n"," "))
    print("- CLEANED (first 600 chars) -")
    print(cleaned.replace("\n"," "))
    print("="*80)

if __name__ == "__main__":
    run_env_test()
