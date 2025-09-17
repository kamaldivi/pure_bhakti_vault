#!/usr/bin/env python3
# detect_publisher_pages.py
import os
import re
import csv
from pathlib import Path
from typing import Tuple, Dict, List

import fitz  # PyMuPDF
from dotenv import load_dotenv

# --------------------------
# Regexes & heuristic rules
# --------------------------
URL_RE = re.compile(r"(?:https?://|www\.)", re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONEISH_RE = re.compile(r"\+?\d[\d\s().-]{6,}")
ALLCAPS_TITLE_RE = re.compile(r"^[A-Z][\w’'\-–:;,() ]{2,}$")
SHORT_TITLE_LINE_RE = re.compile(r"^(?:[A-Z][\w’'\-–]+(?:[ :][A-Z][\w’'\-–]+){0,7})$")

POSITIVE_PATTERNS = [
    r"©|copyright|creative\s+commons|some\s+rights\s+reserved",
    r"\bISBN\b|\bISSN\b|\bLibrary of Congress Control Number\b|\bBritish Library Cataloguing\b",
    r"Cataloging in Publication Data|CIP\b|D\.K\. Agencies",
    r"First Edition|Second Edition|Third Edition|Fourth Edition|Printed at|Printed by|edition\b|reprint",
    r"Worldwide (Centers|Centres) & Contacts|OUR WEBSITES|our websites|contact\s+us",
    r"\bbooks by\b|\benglish titles published by\b|\btitles published by\b|\bBOOKS BY\b",
    r"Permissions beyond the scope of this license|Attribution-No Derivative Works|creativecommons\.org",
]
NEGATIVE_PATTERNS = [
    r"\bContents\b|\bTable of Contents\b|\bChapter\b|\bPreface\b|\bIntroduction\b"
]

POS_RES = [re.compile(p, re.I) for p in POSITIVE_PATTERNS]
NEG_RES = [re.compile(p, re.I) for p in NEGATIVE_PATTERNS]

DEFAULT_THRESHOLD = 6  # label as publisher page if score >= 6

# --------------------------
# Helpers
# --------------------------
def page_text_stats(text: str) -> Dict[str, int]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    words = re.findall(r"\b[\w’']+\b", text)
    numerics = re.findall(r"\b\d+\b", text)
    urls = URL_RE.findall(text)
    emails = EMAIL_RE.findall(text)
    phones = PHONEISH_RE.findall(text)

    short_title_like = sum(
        1 for ln in lines if 3 <= len(ln) <= 80 and SHORT_TITLE_LINE_RE.match(ln)
    )
    allcaps_title_like = sum(
        1 for ln in lines if 3 <= len(ln) <= 80 and ALLCAPS_TITLE_RE.match(ln) and ln.upper() == ln
    )

    return {
        "line_count": len(lines),
        "word_count": len(words),
        "numeric_count": len(numerics),
        "url_count": len(urls),
        "email_count": len(emails),
        "phoneish_count": len(phones),
        "short_title_like": short_title_like,
        "allcaps_title_like": allcaps_title_like,
    }

def score_page(text: str) -> Tuple[int, List[str], Dict[str, int], str, str]:
    """Return (score, reasons, stats, label, confidence)."""
    reasons = []
    score = 0

    # pattern matches
    for rx in POS_RES:
        if rx.search(text):
            score += 3
            reasons.append(f"match:{rx.pattern}")

    for rx in NEG_RES:
        if rx.search(text):
            score -= 2
            reasons.append(f"neg:{rx.pattern}")

    stats = page_text_stats(text)
    wc = stats["word_count"]

    # contact density
    if stats["url_count"] >= 3:
        score += 2; reasons.append("urls>=3")
    if stats["email_count"] >= 1:
        score += 1; reasons.append("email>=1")
    if stats["phoneish_count"] >= 3:
        score += 2; reasons.append("phones>=3")

    if wc <= 250 and (stats["url_count"] + stats["email_count"] + stats["phoneish_count"]) >= 5:
        score += 3; reasons.append("contact_heavy_low_wc")

    # numeric density (e.g., catalogs / phone lists)
    if stats["numeric_count"] >= 30 and wc <= 500:
        score += 2; reasons.append("numeric_heavy_low_wc")

    # title-list patterns (publisher catalogs)
    if stats["short_title_like"] >= 8:
        score += 2; reasons.append("many_short_titles")
    if stats["allcaps_title_like"] >= 4:
        score += 1; reasons.append("many_allcaps_titles")

    # license cue
    if "license" in text.lower() and "creative" in text.lower():
        score += 2; reasons.append("license")

    # very empty text pages are not auto-labeled unless also match positives
    # (avoid flagging blank pages)
    if wc < 10 and score < 3:
        reasons.append("near_blank_text")
        # don't penalize, just note

    # label / confidence
    label = "publisher_info" if score >= DEFAULT_THRESHOLD else "content"
    # Confidence bands: tune to your corpus
    if score >= DEFAULT_THRESHOLD + 3:
        confidence = "high"
    elif score >= DEFAULT_THRESHOLD:
        confidence = "medium"
    elif score >= DEFAULT_THRESHOLD - 2:
        confidence = "low"
    else:
        confidence = "very_low"

    return score, reasons, stats, label, confidence

def extract_text(page: fitz.Page) -> str:
    """
    Prefer 'text' for readable extraction; if empty but images exist,
    still return empty (we avoid image-only false positives unless patterns hit).
    """
    txt = page.get_text("text")
    if txt.strip():
        return txt
    # Fallback: sometimes "text" returns little—try "blocks"
    blocks = page.get_text("blocks")
    if blocks:
        text = "\n".join(b[4] for b in blocks if isinstance(b, (list, tuple)) and len(b) >= 5)
        return text
    return ""

# --------------------------
# Main processing
# --------------------------
def analyze_pdf(pdf_path: Path) -> List[dict]:
    doc = fitz.open(pdf_path)
    results = []
    for i, page in enumerate(doc):
        text = extract_text(page)
        score, reasons, stats, label, confidence = score_page(text)

        # Optional sanity: detect image-only pages (blank text + images)
        image_only = (not text.strip()) and (len(page.get_images(full=True)) > 0)

        results.append({
            "pdf": pdf_path.name,
            "page_index": i,
            "page_number": i + 1,
            # explicit assessment fields
            "assessment": "positive_match" if label == "publisher_info" else "no_match",
            "confidence": confidence,
            "score": score,
            # supporting stats
            "word_count": stats["word_count"],
            "urls": stats["url_count"],
            "emails": stats["email_count"],
            "phones": stats["phoneish_count"],
            "short_title_like": stats["short_title_like"],
            "image_only": image_only,
            # human-readable reasons
            "reasons": ";".join(reasons),
        })
    return results

def analyze_folder(pdf_folder: Path) -> List[dict]:
    rows = []
    for pdf in sorted(pdf_folder.glob("*.pdf")):
        try:
            rows.extend(analyze_pdf(pdf))
        except Exception as e:
            rows.append({
                "pdf": pdf.name,
                "page_index": -1,
                "page_number": -1,
                "assessment": "error",
                "confidence": "n/a",
                "score": -999,
                "word_count": 0,
                "urls": 0,
                "emails": 0,
                "phones": 0,
                "short_title_like": 0,
                "image_only": False,
                "reasons": f"exception:{type(e).__name__}:{e}",
            })
    return rows

def main():
    load_dotenv()  # loads .env in CWD
    pdf_folder = Path(os.getenv("PDF_FOLDER", "")).expanduser()
    process_folder = Path(os.getenv("PROCESS_FOLDER", "")).expanduser()

    if not pdf_folder.exists() or not pdf_folder.is_dir():
        raise SystemExit(f"PDF_FOLDER not found or not a directory: {pdf_folder}")
    process_folder.mkdir(parents=True, exist_ok=True)

    out_csv = process_folder / "publisher_page_flags.csv"
    rows = analyze_folder(pdf_folder)

    if not rows:
        raise SystemExit("No PDFs processed—no rows to write.")

    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {out_csv}")

if __name__ == "__main__":
    main()
