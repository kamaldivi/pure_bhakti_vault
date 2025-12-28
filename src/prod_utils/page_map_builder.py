#!/usr/bin/env python3
"""
page_map_builder.py
===================

Purpose
-------
Builds the `page_map` table for all PDFs found under a folder configured via `.env`.
For each PDF file:

1) Resolve `book_id` using your existing DB util (`PureBhaktiVaultDB.get_book_id_by_pdf_name()`).
2) Try to extract page labels via PyMuPDF (`page.get_label()`), normalizing any PDF hex-string
   chunks like `<FEFF0061>` -> `a`.
3) If page labels are missing or empty, use page_number as page_label (e.g., page 5 gets label "5").
4) Upsert results into `page_map` using a single direct SQL `INSERT ... ON CONFLICT`.
   - page_number = page_index + 1 (1-based)
   - page_label  = normalized label (or page_number as string if no label)
   - page_type   = 'Primary' (default)

Design Principles
-----------------
- **No duplication** of DB code: we use `PureBhaktiVaultDB` for connection/cursor mgmt and book lookups.
- **Simple fallback**: When embedded labels are missing, use page_number as the label.
- **No configuration required**: No dependency on header_height, footer_height, or page_label_location from book table.

Environment
-----------
Requires a `.env` with at least:
    PDF_FOLDER=/path/to/pdfs

Your DB util should already read the DSN/params from `.env` internally. If not, configure it as needed.

Install
-------
    pip install pymupdf psycopg2-binary python-dotenv

Run
---
    python page_map_builder.py

Schema Assumptions
------------------
- `page_map` table exists with a unique key on (book_id, page_number).
  If you need a CREATE TABLE helper, add it separately or let me know the exact schema.
"""

import os
import re
import logging
from pathlib import Path

# .env support
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

import fitz  # PyMuPDF
from psycopg2.extras import execute_values

# Your DB util (already provided by you)
from pure_bhakti_vault_db import PureBhaktiVaultDB


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("page_map_builder")


# --------------------------------------------------------------------------------------
# Label normalization helpers
# --------------------------------------------------------------------------------------
_HEX_CHUNK_RE = re.compile(r"<([0-9A-Fa-f \t\r\n]+)>")

def _decode_hex_bytes_to_text(hex_bytes: bytes) -> str:
    """
    Decode bytes that likely represent text in UTF-16 (with or without BOM), falling back to UTF-8.
    """
    for enc in ("utf-16", "utf-16-be", "utf-8"):
        try:
            return hex_bytes.decode(enc)
        except UnicodeError:
            continue
    return ""

def normalize_page_label(label: str) -> str:
    """
    Replace any number of <...> hex-string chunks inside label with decoded text.
    Example: '<FEFF0061>10' -> 'a10'
    """
    if not label:
        return ""
    def _repl(m):
        hexstr = m.group(1).replace(" ", "")
        try:
            return _decode_hex_bytes_to_text(bytes.fromhex(hexstr))
        except ValueError:
            return m.group(0)  # keep original if not valid hex
    return _HEX_CHUNK_RE.sub(_repl, label)


# --------------------------------------------------------------------------------------
# Core builder
# --------------------------------------------------------------------------------------
class PageMapBuilderRef:
    """
    Thin coordinator that uses PureBhaktiVaultDB for DB access and delegates label extraction
    to either PyMuPDF (preferred) or the fallback header/footer module.
    The only direct SQL here is the INSERT into `page_map`.
    """
    def __init__(self, pdf_folder: str):
        self.pdf_folder = Path(pdf_folder)
        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")
        self.db = PureBhaktiVaultDB()

    def process_pdf(self, pdf_name: str) -> None:
        pdf_path = self.pdf_folder / pdf_name
        log.info("Processing PDF: %s", pdf_path.name)

        # Resolve book_id via DB util
        book_id = self.db.get_book_id_by_pdf_name(pdf_path.name)
        if book_id is None:
            stem = pdf_path.stem
            if stem and stem != pdf_path.name:
                book_id = self.db.get_book_id_by_pdf_name(stem)
        if book_id is None:
            log.warning("Could not find book_id for %s; skipping.", pdf_path.name)
            return

        # Open the PDF
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            log.error("Failed to open %s: %s", pdf_path, e)
            return

        # Check if PDF has embedded page labels
        defs = doc.get_page_labels()
        rows = []

        if not defs:
            # No embedded page labels - use page_number as page_label
            log.info("No embedded page labels found, using page_number as page_label")
            for i in range(doc.page_count):
                page_number = i + 1
                page_label = str(page_number)  # Use page_number as label
                rows.append((book_id, page_number, page_label, "Primary"))
        else:
            # Extract embedded page labels
            log.info("Found embedded page labels, extracting...")
            for i in range(doc.page_count):
                page = doc.load_page(i)
                raw = page.get_label() or ""
                label = normalize_page_label(raw)

                # If normalized label is empty, fallback to page_number
                if not label or not label.strip():
                    label = str(i + 1)

                page_number = i + 1
                rows.append((book_id, page_number, label, "Primary"))

        doc.close()

        if not rows:
            log.info("No pages found for %s", pdf_path.name)
            return

        # Upsert into page_map
        insert_sql = """
            INSERT INTO page_map (book_id, page_number, page_label, page_type)
            VALUES %s
            ON CONFLICT (book_id, page_number) DO UPDATE
            SET page_label = EXCLUDED.page_label,
                page_type  = EXCLUDED.page_type
        """
        try:
            with self.db.get_cursor(dictionary=False) as cur:
                execute_values(cur, insert_sql, rows)
        except Exception as e:
            log.error("Failed to insert page_map rows for %s: %s", pdf_path.name, e)
            return

        log.info("Inserted/updated %d rows for book_id=%s", len(rows), book_id)

    def run(self):
        pdfs = sorted(self.pdf_folder.glob("*.pdf"))
        if not pdfs:
            log.warning("No PDFs found in %s", self.pdf_folder)
            return
        for pdf in pdfs:
            self.process_pdf(pdf.name)


# --------------------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------------------
def main():
    pdf_folder = os.getenv("PDF_FOLDER")
    if not pdf_folder:
        raise RuntimeError("PDF_FOLDER not set in environment (.env)")
    builder = PageMapBuilderRef(pdf_folder)
    builder.run()

if __name__ == "__main__":
    main()
