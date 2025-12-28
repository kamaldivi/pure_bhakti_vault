#!/usr/bin/env python3
"""
Extract Words Containing Dangerous Glyphs

Scans PDF books for words containing dangerous (corrupted) Sanskrit glyphs
and stores aggregated results in PostgreSQL for manual analysis and
font-based rule derivation.

This utility:
1. Queries books by book_type from database
2. Skips books, if need they need to pre-configured
3. Skips fonts starting with AARitu/AATripti (Hindi/Bengali diacritics)
4. Scans all pages of each PDF
5. Extracts words containing dangerous glyphs (e.g., ä, å, ë, ®, √, ß)
6. Aggregates by (book_id, font_name, glyph)
7. Stores unique sample words and page numbers

The output enables:
- Manual review of corrupted words
- Derivation of font-specific replacement rules
- Validation of global vs font-specific patterns

Note: Books with Gaudiya fonts are skipped because they use different
glyph mappings. AARitu/AATripti fonts are skipped because they represent
Hindi/Bengali diacritics, not Sanskrit IAST characters.

Requirements:
    pip install psycopg2-binary python-dotenv PyMuPDF

Usage:
    python extract_glyph_words.py
    python extract_glyph_words.py --book-ids 7,15,50
"""

import os
import sys
import re
import json
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import argparse
from dotenv import load_dotenv

# Import database utility
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()

# =============================================================================
# DANGEROUS GLYPHS CONFIGURATION
# =============================================================================

# 20 dangerous glyphs (lowercase) - established through manual analysis
DANGEROUS_GLYPHS_BASE = [
    "å", "ä", "ë", "é", "ï", "ö", "ü", "ú", "ù", "ÿ", "ç",
    "î", "ò", "µ", "ß", "®", "√", "∂", "∫", "†", "ñ",
]

# Include uppercase variants where they exist
DANGEROUS_GLYPHS = set(DANGEROUS_GLYPHS_BASE + [
    "Å", "Ä", "Ë", "É", "Ï", "Ö", "Ü", "Ú", "Ù", "Ÿ", "Ç", "Î", "Ò", "Ñ",
    # Note: µ, ß, ®, √, ∂, ∫, † don't have typical uppercase variants
])

# Maximum sample words and pages to store
MAX_SAMPLE_WORDS = 50
MAX_SAMPLE_PAGES = 20

# Hard-coded book type
TARGET_BOOK_TYPE = "english-gurudev"

# Books to skip (scanned books. Text can only extracted via OCR)
SKIP_BOOK_IDS = {102}

# Font prefixes to skip (Hindi/Bengali diacritics, not Sanskrit)
SKIP_FONT_PREFIXES = ("AARitu", "AATripti")

# IAST characters for word boundary detection
IAST_CHARS = "āīūṛṝḷḹṅñṭḍṇśṣṃṁḥĀĪŪṚṜḶḸṄÑṬḌṆŚṢṂḤ"

# =============================================================================
# DANGEROUS GLYPH WORD EXTRACTOR
# =============================================================================

class DangerousGlyphWordExtractor:
    """
    Extracts words containing dangerous glyphs from PDF books.
    """

    def __init__(self):
        """Initialize the extractor."""
        self.db = PureBhaktiVaultDB()
        self.pdf_folder = Path(os.getenv("PDF_FOLDER", "./pdfs"))

        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")

        # Aggregation structure: (book_id, font_name, glyph) -> stats
        self.stats: Dict[Tuple[int, str, str], Dict[str, Any]] = {}

        # Track ignored books
        self.ignored_books: List[Dict[str, Any]] = []

        # Track skipped fonts (Hindi/Bengali)
        self.skipped_fonts: Dict[str, int] = {}

        # Compile word extraction regex (includes IAST and dangerous glyphs)
        # Matches sequences of letters, hyphens, apostrophes (common in transliterated text)
        # IMPORTANT: Include dangerous glyphs in pattern so words aren't split
        dangerous_glyphs_escaped = re.escape(''.join(DANGEROUS_GLYPHS))
        self.word_pattern = re.compile(
            rf"[A-Za-z{IAST_CHARS}{dangerous_glyphs_escaped}\-']+",
            re.UNICODE
        )

        self.processed_count = 0
        self.total_books = 0

    def get_target_books(self, book_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Get target books from database.

        Args:
            book_ids: Optional list of specific book IDs to process

        Returns:
            List of dicts with book_id, pdf_name
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    if book_ids:
                        # Process specific book IDs
                        placeholders = ','.join(['%s'] * len(book_ids))
                        query = f"""
                            SELECT book_id, pdf_name
                            FROM book
                            WHERE book_id IN ({placeholders})
                            ORDER BY book_id
                        """
                        cur.execute(query, book_ids)
                    else:
                        # Process all books of target type
                        query = """
                            SELECT book_id, pdf_name
                            FROM book
                            WHERE book_type = %s
                            ORDER BY book_id
                        """
                        cur.execute(query, (TARGET_BOOK_TYPE,))

                    results = cur.fetchall()
                    books = []
                    for row in results:
                        book_id = row[0]
                        # Skip books with Gaudiya fonts
                        if book_id in SKIP_BOOK_IDS:
                            continue
                        books.append({
                            'book_id': book_id,
                            'pdf_name': row[1]
                        })

                    return books
        except Exception as e:
            raise DatabaseError(f"Failed to query books: {e}")

    def extract_words_from_text(self, text: str) -> List[str]:
        """
        Extract clean words from text using regex.

        Args:
            text: Raw text from PDF span

        Returns:
            List of words that match the word pattern
        """
        return self.word_pattern.findall(text)

    def scan_page(
        self,
        pdf_doc: fitz.Document,
        page_num: int,
        book_id: int
    ) -> bool:
        """
        Scan a single page for words containing dangerous glyphs.

        Args:
            pdf_doc: PyMuPDF document object
            page_num: Page number (0-indexed for PyMuPDF)
            book_id: Book ID

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

        page_number_display = page_num + 1  # 1-indexed for display

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # Skip non-text blocks
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    font_name = span.get("font", "Unknown")

                    if not text:
                        continue

                    # Skip fonts with Hindi/Bengali diacritics
                    if font_name.startswith(SKIP_FONT_PREFIXES):
                        self.skipped_fonts[font_name] = self.skipped_fonts.get(font_name, 0) + 1
                        continue

                    # Extract clean words using regex
                    words = self.extract_words_from_text(text)

                    for word in words:
                        # Check if word contains any dangerous glyph
                        glyphs_in_word = set(ch for ch in word if ch in DANGEROUS_GLYPHS)

                        if not glyphs_in_word:
                            continue

                        # For each dangerous glyph in the word, update aggregation
                        for glyph in glyphs_in_word:
                            key = (book_id, font_name, glyph)

                            if key not in self.stats:
                                # Initialize new entry
                                self.stats[key] = {
                                    "unicode": f"U+{ord(glyph):04X}",
                                    "count": 0,
                                    "pages": set(),
                                    "sample_words": []
                                }

                            # Update aggregation
                            self.stats[key]["count"] += 1

                            # Add page if not at limit
                            if len(self.stats[key]["pages"]) < MAX_SAMPLE_PAGES:
                                self.stats[key]["pages"].add(page_number_display)

                            # Add word if not at limit and not duplicate
                            if (len(self.stats[key]["sample_words"]) < MAX_SAMPLE_WORDS and
                                    word not in self.stats[key]["sample_words"]):
                                self.stats[key]["sample_words"].append(word)

        return True

    def scan_book(self, book_info: Dict[str, Any]) -> bool:
        """
        Scan all pages of a book.

        Args:
            book_info: Dict with book_id, pdf_name

        Returns:
            True if book was successfully scanned, False if ignored
        """
        book_id = book_info['book_id']
        pdf_name = book_info['pdf_name']
        pdf_path = self.pdf_folder / pdf_name

        if not pdf_path.exists():
            print(f"  ⚠️  PDF not found: {pdf_name}")
            self.ignored_books.append({
                'book_id': book_id,
                'reason': 'PDF file not found'
            })
            return False

        try:
            pdf_doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"  ⚠️  Failed to open PDF: {pdf_name} - {e}")
            self.ignored_books.append({
                'book_id': book_id,
                'reason': f'Failed to open: {e}'
            })
            return False

        total_pages = len(pdf_doc)
        extractable_pages = 0

        print(f"  📖 Scanning {total_pages} pages...")

        for page_num in range(total_pages):
            if self.scan_page(pdf_doc, page_num, book_id):
                extractable_pages += 1

        pdf_doc.close()

        if extractable_pages == 0:
            print(f"  ⚠️  No extractable text (scanned PDF)")
            self.ignored_books.append({
                'book_id': book_id,
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
                    # Delete existing entries for this book (for restartability)
                    cur.execute(
                        "DELETE FROM dangerous_glyph_words WHERE book_id = %s",
                        (book_id,)
                    )

                    for (bid, font_name, glyph), data in book_stats.items():
                        # Convert pages set to sorted list and then to JSON
                        pages_list = sorted(list(data["pages"]))
                        pages_json = json.dumps(pages_list)
                        words_json = json.dumps(data["sample_words"])

                        # Insert aggregated row
                        query = """
                            INSERT INTO dangerous_glyph_words
                            (book_id, font_name, glyph, unicode_codepoint,
                             occurrence_count, sample_words, pages_sample, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                        """
                        cur.execute(query, (
                            bid,
                            font_name,
                            glyph,
                            data["unicode"],
                            data["count"],
                            words_json,
                            pages_json
                        ))

                    conn.commit()
                    print(f"  💾 Wrote {len(book_stats)} dangerous glyph entries to database")
        except Exception as e:
            print(f"  ❌ Database write failed: {e}")
            raise DatabaseError(f"Failed to write to database: {e}")

    def create_table_if_not_exists(self):
        """Create dangerous_glyph_words table if it doesn't exist."""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS dangerous_glyph_words (
                id SERIAL PRIMARY KEY,
                book_id INTEGER NOT NULL REFERENCES book(book_id),
                font_name TEXT NOT NULL,
                glyph TEXT NOT NULL,
                unicode_codepoint TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL,
                sample_words JSONB NOT NULL,
                pages_sample JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(book_id, font_name, glyph)
            );

            CREATE INDEX IF NOT EXISTS idx_dangerous_glyph_words_book_id
                ON dangerous_glyph_words(book_id);
            CREATE INDEX IF NOT EXISTS idx_dangerous_glyph_words_font_name
                ON dangerous_glyph_words(font_name);
            CREATE INDEX IF NOT EXISTS idx_dangerous_glyph_words_glyph
                ON dangerous_glyph_words(glyph);
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_table_sql)
                    conn.commit()
                    print("✅ Database table ready: dangerous_glyph_words")
        except Exception as e:
            raise DatabaseError(f"Failed to create table: {e}")

    def run(self, book_ids: Optional[List[int]] = None):
        """
        Main execution method.

        Args:
            book_ids: Optional list of specific book IDs to process
        """
        print("=" * 80)
        print("📚 DANGEROUS GLYPH WORD EXTRACTOR")
        print("=" * 80)
        print()

        # Ensure table exists
        self.create_table_if_not_exists()
        print()

        # Get target books
        print(f"🔍 Querying books (type: {TARGET_BOOK_TYPE})...")
        print(f"⚠️  Skipping {len(SKIP_BOOK_IDS)} books with Gaudiya fonts: {sorted(SKIP_BOOK_IDS)}")
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
            pdf_name = book_info['pdf_name']

            print(f"[{i}/{self.total_books}] Book {book_id}: {pdf_name}")

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
        print("📊 EXTRACTION SUMMARY")
        print("=" * 80)
        print(f"Total books queried: {self.total_books}")
        print(f"Successfully processed: {self.processed_count}")
        print(f"Ignored/skipped: {len(self.ignored_books)}")
        print()

        if self.ignored_books:
            print("⚠️  IGNORED BOOKS:")
            for book in self.ignored_books:
                print(f"  • Book {book['book_id']}")
                print(f"    Reason: {book['reason']}")
            print()

        if self.skipped_fonts:
            print("⚠️  SKIPPED FONTS (Hindi/Bengali diacritics):")
            total_skipped = sum(self.skipped_fonts.values())
            print(f"  Total text spans skipped: {total_skipped:,}")
            print(f"  Unique fonts skipped: {len(self.skipped_fonts)}")
            print()
            print("  Font breakdown:")
            for font_name, count in sorted(self.skipped_fonts.items(), key=lambda x: x[1], reverse=True):
                print(f"    • {font_name}: {count:,} spans")
            print()

        print("✅ Extraction complete!")
        print()
        print("💡 Query examples:")
        print("   -- Words with specific glyph:")
        print("   SELECT book_id, font_name, sample_words")
        print("   FROM dangerous_glyph_words WHERE glyph = 'ä';")
        print()
        print("   -- Font-specific patterns:")
        print("   SELECT font_name, glyph, SUM(occurrence_count)")
        print("   FROM dangerous_glyph_words")
        print("   GROUP BY font_name, glyph ORDER BY SUM(occurrence_count) DESC;")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract words containing dangerous Sanskrit glyphs from PDFs"
    )
    parser.add_argument(
        "--book-ids",
        type=str,
        help="Comma-separated list of book IDs to process (e.g., '7,15,50')"
    )

    args = parser.parse_args()

    # Parse book IDs if provided
    book_ids = None
    if args.book_ids:
        try:
            book_ids = [int(bid.strip()) for bid in args.book_ids.split(',')]
        except ValueError:
            print("❌ ERROR: Invalid book IDs format. Use comma-separated integers (e.g., '7,15,50')")
            return

    try:
        extractor = DangerousGlyphWordExtractor()
        extractor.run(book_ids=book_ids)
    except KeyboardInterrupt:
        print("\n\n⚠️  Extraction interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
