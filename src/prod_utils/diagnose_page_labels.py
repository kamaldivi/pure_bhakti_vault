#!/usr/bin/env python3
"""
diagnose_page_labels.py
========================

Purpose
-------
Diagnoses page_label and page_number mapping issues by:
1. Reading book, page_map table to collect book_id, pdf_name, page_label info
2. Reading all PDFs under /Users/kamaldivi/Development/pbb_books folder
3. Using PyMuPDF to extract page labels from PDFs
4. Generating a CSV report with:
   - Books that have no page_labels built in PDF
   - Books where page_label/page_numbers don't match database values

Output
------
CSV file: page_label_diagnosis.csv
Columns: book_id, pdf_name, page_number, db_page_label, pdf_page_label, issue_type

Issue types:
- NO_PDF_LABELS: PDF has no embedded page labels
- MISMATCH: Database page_label doesn't match PDF page_label
- MISSING_IN_DB: Page exists in PDF but not in database
- MISSING_IN_PDF: Page exists in database but not in PDF

Dependencies
------------
    pip install pymupdf psycopg2-binary python-dotenv

Run
---
    python diagnose_page_labels.py
"""

import os
import csv
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re

# .env support
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import fitz  # PyMuPDF
from pure_bhakti_vault_db import PureBhaktiVaultDB

# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("page_label_diagnosis")

# --------------------------------------------------------------------------------------
# Label normalization (from page_map_builder.py)
# --------------------------------------------------------------------------------------
_HEX_CHUNK_RE = re.compile(r"<([0-9A-Fa-f \t\r\n]+)>")

def _decode_hex_bytes_to_text(hex_bytes: bytes) -> str:
    """Decode bytes that likely represent text in UTF-16 (with or without BOM), falling back to UTF-8."""
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
# Diagnosis Logic
# --------------------------------------------------------------------------------------
class PageLabelDiagnostics:
    """Diagnoses page label mismatches between database and PDFs."""

    def __init__(self, pdf_folder: str, output_csv: str = "page_label_diagnosis.csv"):
        self.pdf_folder = Path(pdf_folder)
        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")

        self.output_csv = output_csv
        self.db = PureBhaktiVaultDB()
        self.issues: List[Dict[str, str]] = []

        # Statistics
        self.stats = {
            'total_books': 0,
            'books_no_pdf_labels': 0,
            'books_with_mismatches': 0,
            'total_mismatches': 0,
            'total_missing_in_db': 0,
            'total_missing_in_pdf': 0,
        }

    def get_db_page_labels(self, book_id: int) -> Dict[int, str]:
        """
        Retrieve page_number -> page_label mapping from database for a book.

        Returns:
            dict: {page_number: page_label}
        """
        query = """
            SELECT page_number, page_label
            FROM page_map
            WHERE book_id = %s
            ORDER BY page_number
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                results = cursor.fetchall()
                return {row['page_number']: row['page_label'] or '' for row in results}
        except Exception as e:
            log.error(f"Error fetching page labels from DB for book_id {book_id}: {e}")
            return {}

    def get_pdf_page_labels(self, pdf_path: Path) -> Tuple[bool, Dict[int, str]]:
        """
        Extract page labels from PDF using PyMuPDF.

        Returns:
            tuple: (has_labels, {page_number: page_label})
                   has_labels is False if PDF has no embedded labels
        """
        try:
            doc = fitz.open(pdf_path)
            defs = doc.get_page_labels()

            # Check if PDF has embedded page labels
            if not defs:
                log.info(f"PDF has no embedded page labels: {pdf_path.name}")
                return False, {}

            labels = {}
            for i in range(doc.page_count):
                page = doc.load_page(i)
                raw_label = page.get_label() or ""
                normalized_label = normalize_page_label(raw_label)
                page_number = i + 1
                labels[page_number] = normalized_label

            doc.close()
            return True, labels

        except Exception as e:
            log.error(f"Error reading PDF {pdf_path}: {e}")
            return False, {}

    def diagnose_book(self, pdf_name: str) -> None:
        """Diagnose a single book for page label issues."""
        pdf_path = self.pdf_folder / pdf_name

        if not pdf_path.exists():
            log.warning(f"PDF file not found: {pdf_path}")
            return

        log.info(f"Diagnosing: {pdf_name}")
        self.stats['total_books'] += 1

        # Get book_id from database
        book_id = self.db.get_book_id_by_pdf_name(pdf_name)
        if book_id is None:
            # Try without extension
            stem = pdf_path.stem
            if stem and stem != pdf_name:
                book_id = self.db.get_book_id_by_pdf_name(stem)

        if book_id is None:
            log.warning(f"Book not found in database: {pdf_name}")
            self.issues.append({
                'book_id': 'N/A',
                'pdf_name': pdf_name,
                'page_number': 'N/A',
                'db_page_label': 'N/A',
                'pdf_page_label': 'N/A',
                'issue_type': 'BOOK_NOT_IN_DB'
            })
            return

        # Get page labels from database
        db_labels = self.get_db_page_labels(book_id)

        # Get page labels from PDF
        has_pdf_labels, pdf_labels = self.get_pdf_page_labels(pdf_path)

        # Check if PDF has no labels
        if not has_pdf_labels:
            self.stats['books_no_pdf_labels'] += 1
            self.issues.append({
                'book_id': str(book_id),
                'pdf_name': pdf_name,
                'page_number': 'N/A',
                'db_page_label': 'N/A',
                'pdf_page_label': 'N/A',
                'issue_type': 'NO_PDF_LABELS'
            })
            return

        # Compare page labels
        book_has_mismatches = False
        all_page_numbers = set(db_labels.keys()) | set(pdf_labels.keys())

        for page_number in sorted(all_page_numbers):
            db_label = db_labels.get(page_number, None)
            pdf_label = pdf_labels.get(page_number, None)

            # Check for mismatches
            if db_label is None and pdf_label is not None:
                # Page exists in PDF but not in database
                book_has_mismatches = True
                self.stats['total_missing_in_db'] += 1
                self.issues.append({
                    'book_id': str(book_id),
                    'pdf_name': pdf_name,
                    'page_number': str(page_number),
                    'db_page_label': '',
                    'pdf_page_label': pdf_label,
                    'issue_type': 'MISSING_IN_DB'
                })

            elif db_label is not None and pdf_label is None:
                # Page exists in database but not in PDF
                book_has_mismatches = True
                self.stats['total_missing_in_pdf'] += 1
                self.issues.append({
                    'book_id': str(book_id),
                    'pdf_name': pdf_name,
                    'page_number': str(page_number),
                    'db_page_label': db_label,
                    'pdf_page_label': '',
                    'issue_type': 'MISSING_IN_PDF'
                })

            elif db_label != pdf_label:
                # Labels don't match
                book_has_mismatches = True
                self.stats['total_mismatches'] += 1
                self.issues.append({
                    'book_id': str(book_id),
                    'pdf_name': pdf_name,
                    'page_number': str(page_number),
                    'db_page_label': db_label or '',
                    'pdf_page_label': pdf_label or '',
                    'issue_type': 'MISMATCH'
                })

        if book_has_mismatches:
            self.stats['books_with_mismatches'] += 1
            log.warning(f"Found mismatches in: {pdf_name}")
        else:
            log.info(f"No issues found in: {pdf_name}")

    def diagnose_all_books(self) -> None:
        """Diagnose all books in the database."""
        log.info("Fetching all books from database...")

        try:
            books = self.db.get_all_books()
            log.info(f"Found {len(books)} books in database")

            for book in books:
                pdf_name = book['pdf_name']
                self.diagnose_book(pdf_name)

        except Exception as e:
            log.error(f"Error fetching books from database: {e}")
            return

    def write_report(self) -> None:
        """Write diagnosis report to CSV file."""
        if not self.issues:
            log.info("No issues found! All page labels match.")
            # Still write an empty CSV with headers
            with open(self.output_csv, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    'book_id', 'pdf_name', 'page_number',
                    'db_page_label', 'pdf_page_label', 'issue_type'
                ])
                writer.writeheader()
            return

        log.info(f"Writing report to: {self.output_csv}")

        with open(self.output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[
                'book_id', 'pdf_name', 'page_number',
                'db_page_label', 'pdf_page_label', 'issue_type'
            ])
            writer.writeheader()
            writer.writerows(self.issues)

        log.info(f"Report written with {len(self.issues)} issues")

    def print_summary(self) -> None:
        """Print summary statistics."""
        print("\n" + "=" * 70)
        print("PAGE LABEL DIAGNOSIS SUMMARY")
        print("=" * 70)
        print(f"Total books analyzed:           {self.stats['total_books']}")
        print(f"Books with no PDF labels:       {self.stats['books_no_pdf_labels']}")
        print(f"Books with mismatches:          {self.stats['books_with_mismatches']}")
        print(f"Total label mismatches:         {self.stats['total_mismatches']}")
        print(f"Pages missing in DB:            {self.stats['total_missing_in_db']}")
        print(f"Pages missing in PDF:           {self.stats['total_missing_in_pdf']}")
        print(f"Total issues:                   {len(self.issues)}")
        print("=" * 70)
        print(f"\nReport saved to: {self.output_csv}")
        print()

    def run(self) -> None:
        """Run the complete diagnosis."""
        log.info("Starting page label diagnosis...")

        # Test database connection
        if not self.db.test_connection():
            log.error("Failed to connect to database")
            return

        # Diagnose all books
        self.diagnose_all_books()

        # Write report
        self.write_report()

        # Print summary
        self.print_summary()


# --------------------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------------------
def main():
    pdf_folder = os.getenv("PDF_FOLDER", "/Users/kamaldivi/Development/pbb_books")
    output_csv = "page_label_diagnosis.csv"

    log.info(f"PDF Folder: {pdf_folder}")
    log.info(f"Output CSV: {output_csv}")

    diagnostics = PageLabelDiagnostics(pdf_folder, output_csv)
    diagnostics.run()


if __name__ == "__main__":
    main()
