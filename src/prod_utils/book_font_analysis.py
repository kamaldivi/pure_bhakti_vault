#!/usr/bin/env python3
"""
Book Font Analysis Utility

Scans books for problematic Sanskrit glyphs and generates aggregated
font-based corruption statistics for profile derivation.

This utility:
1. Queries books by book_type from the database
2. Scans all pages of each PDF
3. Detects non-standard glyphs (characters outside allowed IAST/ASCII set)
4. Aggregates findings by (book_id, font_name, glyph)
5. Stores aggregated results in sanskrit_font_analysis table

The output enables derivation of:
- Global-safe replacements (e.g., î → ī)
- Font-specific profiles (e.g., ScaGoudy: å→ṛ, ë→ṇ)

Requirements:
    pip install psycopg2-binary python-dotenv PyMuPDF

Usage:
    python book_font_analysis.py
    python book_font_analysis.py --book-ids 56,115,120
"""

import os
import sys
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional
from datetime import datetime
from collections import defaultdict
import argparse
import re
import json
from dotenv import load_dotenv

# Import database utility
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()

# Define allowed character sets
# Allowed ASCII (letters and digits)
ALLOWED_ASCII = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

# Allowed IAST characters (International Alphabet of Sanskrit Transliteration)
ALLOWED_IAST = set("āīūṛṝḷḹṅñṭḍṇśṣṃṁḥĀĪŪṚṜḶḸṄÑṬḌṆŚṢṂḤ")

# Allowed punctuation, symbols, and whitespace
ALLOWED_PUNCTUATION = set(
    # Basic punctuation and symbols
    " .,;:!?\"'()-—–[]{}/@#$%&*+=<>|\\~`_^"
    # Whitespace characters
    "\n\r\t"
    # Typographic quotes
    "\u2018\u2019\u201C\u201D\u201A\u201E"  # ‘ ’ “ ” ‚ „
    # Bullets and list markers
    "•◦▪●◉○△▲►"
    # Ellipsis
    "…"
    # Copyright and trademark (NOTE: ® intentionally excluded)
    "©™"
    # Soft hyphen
    "\u00AD"
    # Various space characters (non-breaking, em, en, thin, hair, etc.)
    "\u00A0"  # Non-breaking space
    "\u2000\u2001\u2002\u2003"  # Various spaces
    "\u2004\u2005\u2006\u2007\u2008\u2009\u200A"
)

# Combining diacritical marks (in case decomposed forms appear)
ALLOWED_COMBINING = set(
    "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030A\u030B\u030C"  # accents above
    "\u0323\u0324\u0325\u0327\u0328"  # accents below
)

# Spacing modifier letters (standalone diacritical glyphs)
ALLOWED_SPACING_MODIFIERS = set(
    "\u02C6\u02C7\u02D8\u02D9\u02DA\u02DB\u02DC\u02DD"  # ˆ ˇ ˘ ˙ ˚ ˛ ˜ ˝
    "\u00B4\u0060"  # ´ `
)

# Additional legitimate symbols
ALLOWED_SYMBOLS = set(
    # IMPORTANT: † is intentionally excluded — it maps to corrupted ṭ in many fonts
    "‡§¶"   # double dagger, section sign, pilcrow
    "‰‱"    # per mille, per ten thousand
    "°"     # degree sign
)

# Control characters and zero-width characters (allowed but usually stripped)
ALLOWED_CONTROL = set(
    "\u0000\u0001\u0002\u0003\u0004\u0005\u0006\u0007\u0008\u000B\u000C\u000E\u000F"
    "\u0010\u0011\u0012\u0013\u0014\u0015\u0016\u0017\u0018\u0019\u001A\u001B\u001C\u001D\u001E\u001F"
    "\u200B\u200C\u200D"   # zero-width characters
    "\uFEFF"              # BOM
)

SAFE_CURRENCY     = set("¡¢£¤¥")
SAFE_SUPERSCRIPTS = set("²³")
SAFE_MATH         = set("±÷∞∼≈≤≥")
SAFE_LIGATURES    = set("ﬁﬂ")
SAFE_DECORATIVE   = set("◊⦁")

# Augment ALLOWED_CHARS
ALLOWED_CHARS = (
    ALLOWED_ASCII |
    ALLOWED_IAST |
    ALLOWED_PUNCTUATION |
    ALLOWED_COMBINING |
    ALLOWED_SPACING_MODIFIERS |
    ALLOWED_SYMBOLS |
    ALLOWED_CONTROL |
    SAFE_CURRENCY |
    SAFE_SUPERSCRIPTS |
    SAFE_MATH |
    SAFE_LIGATURES |
    SAFE_DECORATIVE
)


# Hard-coded book type
TARGET_BOOK_TYPE = "english-gurudev"


class BookFontAnalyzer:
    """
    Scans books for problematic Sanskrit glyphs and generates
    aggregated font-based corruption statistics.
    """

    def __init__(self):
        """Initialize the analyzer."""
        self.db = PureBhaktiVaultDB()
        self.pdf_folder = Path(os.getenv("PDF_FOLDER", "./pdfs"))

        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")

        # Aggregation structure: (book_id, font_name, glyph) -> stats
        self.stats: Dict[Tuple[int, str, str], Dict[str, Any]] = {}

        # Track ignored books (scanned PDFs without text)
        self.ignored_books: List[Dict[str, Any]] = []

        # Track processed books count
        self.processed_count = 0
        self.total_books = 0

    def get_target_books(self, book_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Get target books from database.

        Args:
            book_ids: Optional list of specific book IDs to process

        Returns:
            List of dicts with book_id, pdf_name, book_title
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    if book_ids:
                        # Process specific book IDs
                        placeholders = ','.join(['%s'] * len(book_ids))
                        query = f"""
                            SELECT book_id, pdf_name,
                                   COALESCE(english_book_title, original_book_title) as book_title
                            FROM book
                            WHERE book_id IN ({placeholders})
                            ORDER BY book_id
                        """
                        cur.execute(query, book_ids)
                    else:
                        # Process all books of target type
                        query = """
                            SELECT book_id, pdf_name,
                                   COALESCE(english_book_title, original_book_title) as book_title
                            FROM book
                            WHERE book_type = %s
                            ORDER BY book_id
                        """
                        cur.execute(query, (TARGET_BOOK_TYPE,))

                    results = cur.fetchall()
                    books = []
                    for row in results:
                        books.append({
                            'book_id': row[0],
                            'pdf_name': row[1],
                            'book_title': row[2] or 'Unknown'
                        })

                    return books
        except Exception as e:
            raise DatabaseError(f"Failed to query books: {e}")

    def get_word_context(self, text: str, char_index: int) -> str:
        """
        Extract the complete word containing the character at char_index.

        Args:
            text: Full text
            char_index: Index of the problematic character

        Returns:
            The word containing the character
        """
        # Find word boundaries (whitespace or punctuation)
        start = char_index
        while start > 0 and text[start - 1] not in ' \n\r\t.,;:!?()[]{}':
            start -= 1

        end = char_index
        while end < len(text) - 1 and text[end + 1] not in ' \n\r\t.,;:!?()[]{}':
            end += 1

        # Extract word (include the char itself)
        word = text[start:end + 1]
        return word.strip()

    def scan_page(self, pdf_doc: fitz.Document, page_num: int, book_id: int, book_title: str) -> bool:
        """
        Scan a single page for problematic glyphs.

        Args:
            pdf_doc: PyMuPDF document object
            page_num: Page number (0-indexed for PyMuPDF)
            book_id: Book ID
            book_title: Book title for aggregation

        Returns:
            True if page had extractable text, False otherwise
        """
        page = pdf_doc[page_num]

        # Try to extract text with font information
        try:
            text_dict = page.get_text("dict")
        except Exception:
            return False

        if not text_dict or "blocks" not in text_dict:
            return False

        # Build full text for context extraction
        full_text = page.get_text()
        if not full_text or len(full_text.strip()) == 0:
            return False

        char_index = 0  # Track position in full text

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # Skip non-text blocks
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    font_name = span.get("font", "Unknown")

                    # Check each character
                    for char in text:
                        if char not in ALLOWED_CHARS:
                            # Found a problematic glyph
                            key = (book_id, font_name, char)

                            if key not in self.stats:
                                # Initialize new entry
                                self.stats[key] = {
                                    "book_title": book_title,
                                    "unicode": f"U+{ord(char):04X}",
                                    "count": 0,
                                    "pages": set(),
                                    "sample_contexts": []
                                }

                            # Update aggregation
                            self.stats[key]["count"] += 1

                            # Add page if not at limit
                            if len(self.stats[key]["pages"]) < 20:
                                self.stats[key]["pages"].add(page_num + 1)  # 1-indexed for display

                            # Add context if not at limit
                            if len(self.stats[key]["sample_contexts"]) < 20:
                                context = self.get_word_context(full_text, char_index)
                                if context and context not in self.stats[key]["sample_contexts"]:
                                    self.stats[key]["sample_contexts"].append(context)

                        char_index += 1

        return True

    def scan_book(self, book_info: Dict[str, Any]) -> bool:
        """
        Scan all pages of a book.

        Args:
            book_info: Dict with book_id, pdf_name, book_title

        Returns:
            True if book was successfully scanned, False if ignored
        """
        book_id = book_info['book_id']
        pdf_name = book_info['pdf_name']
        book_title = book_info['book_title']
        pdf_path = self.pdf_folder / pdf_name

        if not pdf_path.exists():
            print(f"  ⚠️  PDF not found: {pdf_name}")
            self.ignored_books.append({
                'book_id': book_id,
                'book_title': book_title,
                'reason': 'PDF file not found'
            })
            return False

        try:
            pdf_doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"  ⚠️  Failed to open PDF: {pdf_name} - {e}")
            self.ignored_books.append({
                'book_id': book_id,
                'book_title': book_title,
                'reason': f'Failed to open: {e}'
            })
            return False

        total_pages = len(pdf_doc)
        extractable_pages = 0

        print(f"  📖 Scanning {total_pages} pages...")

        for page_num in range(total_pages):
            if self.scan_page(pdf_doc, page_num, book_id, book_title):
                extractable_pages += 1

        pdf_doc.close()

        if extractable_pages == 0:
            print(f"  ⚠️  No extractable text (scanned PDF)")
            self.ignored_books.append({
                'book_id': book_id,
                'book_title': book_title,
                'reason': 'No extractable text (scanned PDF)'
            })
            return False

        print(f"  ✅ Scanned {extractable_pages}/{total_pages} pages with text")
        return True

    def write_to_database(self, book_id: int):
        """
        Write aggregated results for a book to database.

        Args:
            book_id: Book ID to write results for
        """
        if not self.stats:
            return

        # Filter stats for this book
        book_stats = {k: v for k, v in self.stats.items() if k[0] == book_id}

        if not book_stats:
            return

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    for (bid, font_name, glyph), data in book_stats.items():
                        # Convert pages set to sorted list and then to JSON
                        pages_list = sorted(list(data["pages"]))
                        pages_json = json.dumps(pages_list)
                        contexts_json = json.dumps(data["sample_contexts"])

                        # Insert aggregated row
                        query = """
                            INSERT INTO sanskrit_font_analysis
                            (book_id, book_title, font_name, glyph, unicode_codepoint,
                             occurrence_count, pages_sample, sample_contexts, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                        """
                        cur.execute(query, (
                            bid,
                            data["book_title"],
                            font_name,
                            glyph,
                            data["unicode"],
                            data["count"],
                            pages_json,
                            contexts_json
                        ))

                    conn.commit()
                    print(f"  💾 Wrote {len(book_stats)} glyph entries to database")
        except Exception as e:
            print(f"  ❌ Database write failed: {e}")
            raise DatabaseError(f"Failed to write to database: {e}")

    def create_table_if_not_exists(self):
        """Create sanskrit_font_analysis table if it doesn't exist."""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS sanskrit_font_analysis (
                id SERIAL PRIMARY KEY,
                book_id INTEGER NOT NULL,
                book_title TEXT,
                font_name TEXT NOT NULL,
                glyph TEXT NOT NULL,
                unicode_codepoint TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL,
                pages_sample JSONB,
                sample_contexts JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(book_id, font_name, glyph)
            );

            CREATE INDEX IF NOT EXISTS idx_sanskrit_font_analysis_book_id
                ON sanskrit_font_analysis(book_id);
            CREATE INDEX IF NOT EXISTS idx_sanskrit_font_analysis_font_name
                ON sanskrit_font_analysis(font_name);
            CREATE INDEX IF NOT EXISTS idx_sanskrit_font_analysis_glyph
                ON sanskrit_font_analysis(glyph);
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_table_sql)
                    conn.commit()
                    print("✅ Database table ready: sanskrit_font_analysis")
        except Exception as e:
            raise DatabaseError(f"Failed to create table: {e}")

    def run(self, book_ids: Optional[List[int]] = None):
        """
        Main execution method.

        Args:
            book_ids: Optional list of specific book IDs to process
        """
        print("=" * 80)
        print("📚 BOOK FONT ANALYSIS UTILITY")
        print("=" * 80)
        print()

        # Ensure table exists
        self.create_table_if_not_exists()
        print()

        # Get target books
        print(f"🔍 Querying books (type: {TARGET_BOOK_TYPE})...")
        books = self.get_target_books(book_ids)
        self.total_books = len(books)

        if not books:
            print("❌ No books found")
            return

        print(f"✅ Found {self.total_books} book(s) to process")
        print()

        # Process each book
        for i, book_info in enumerate(books, 1):
            book_id = book_info['book_id']
            book_title = book_info['book_title']
            pdf_name = book_info['pdf_name']

            print(f"[{i}/{self.total_books}] Book {book_id}: {book_title}")
            print(f"  📄 PDF: {pdf_name}")

            # Clear stats for this book
            self.stats = {}

            # Scan the book
            success = self.scan_book(book_info)

            if success:
                # Write to database after each book
                self.write_to_database(book_id)
                self.processed_count += 1

            print()

        # Print summary
        print("=" * 80)
        print("📊 ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"Total books queried: {self.total_books}")
        print(f"Successfully processed: {self.processed_count}")
        print(f"Ignored/skipped: {len(self.ignored_books)}")
        print()

        if self.ignored_books:
            print("⚠️  IGNORED BOOKS:")
            for book in self.ignored_books:
                print(f"  • Book {book['book_id']}: {book['book_title']}")
                print(f"    Reason: {book['reason']}")
            print()

        print("✅ Analysis complete!")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Sanskrit font corruption patterns across books"
    )
    parser.add_argument(
        "--book-ids",
        type=str,
        help="Comma-separated list of book IDs to process (e.g., '56,115,120')"
    )

    args = parser.parse_args()

    # Parse book IDs if provided
    book_ids = None
    if args.book_ids:
        try:
            book_ids = [int(bid.strip()) for bid in args.book_ids.split(',')]
        except ValueError:
            print("❌ ERROR: Invalid book IDs format. Use comma-separated integers (e.g., '56,115,120')")
            return

    try:
        analyzer = BookFontAnalyzer()
        analyzer.run(book_ids=book_ids)
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
