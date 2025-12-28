#!/usr/bin/env python3
"""
Extract Words with Ambiguous Diacritics

Builds a word dictionary for ambiguous diacritical characters (å, ñ) that have
multiple possible IAST mappings. These characters are problematic in legacy fonts
because context determines their meaning:
  - å could be ā OR ṛ
  - ñ could be ñ OR ṣ

This utility:
1. Queries all books where book_type = 'english-gurudev'
2. Scans all pages of each PDF using PyMuPDF
3. Extracts words containing dangerous glyphs
4. Applies GLOBAL replacements for all glyphs EXCEPT å and ñ
   (e.g., ë→ṇ, ä→ā, ®→ṛ, ß→ṣ, etc.)
5. Simplifies compound words - keeps only hyphenated parts with ambiguous chars
6. Captures only words that STILL contain å or ñ after global replacements
7. Tracks by (font_name, diacritic, word) for pattern analysis
8. Implements substring minimization to keep shortest meaningful forms
9. Skips Hindi/Bengali fonts (AARitu, AATripti prefixes)
10. Stores results in ambiguous_diacritic_words table

Example Word Processing:
  Original: "Kåñëa"
  After global replacements: "Kåñṇa" (ë→ṇ applied)
  Still contains: å, ñ → CAPTURED

  Original: "Bhagavät"
  After global replacements: "Bhagavāt" (ä→ā applied)
  Contains: NO ambiguous chars → SKIPPED

Compound Word Simplification (Split ALL compounds):
  "abhīñṭa-bhāva-anukūla" → "abhīñṭa" (only first part has ñ)
  "Kåñṇa-līlā" → "Kåñṇa" (only first part has å, ñ)
  "rādhā-Kåñṇa" → "Kåñṇa" (only second part has ambiguous chars)
  "mahå-bhågå" → "mahå" + "bhågå" (both parts split into separate entries)

  This approach maximizes data reduction by ensuring each unique word part
  is analyzed independently, regardless of what compounds it appears in.

Substring Minimization Rules:
- Keep shortest word form (e.g., "Kåñṇa" instead of "Mahā-Kåñṇa")
- Uses simple string containment check
- Works in conjunction with compound splitting for maximum data reduction

Font Filtering:
- Skips AARitu* and AATripti* fonts (Hindi/Bengali diacritics)
- Processes all other fonts including Gaudiya variants

Requirements:
    pip install psycopg2-binary python-dotenv PyMuPDF

Usage:
    python extract_ambiguous_diacritics.py              # Process all books
    python extract_ambiguous_diacritics.py --book-ids 7 # Test with book 7
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict
from dotenv import load_dotenv

# Import PyMuPDF
try:
    import fitz
except ImportError:
    print("❌ ERROR: PyMuPDF not installed. Install with: pip install PyMuPDF")
    sys.exit(1)

# Import database utility
sys.path.insert(0, str(Path(__file__).parent))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# Target ambiguous diacritics (case variations)
AMBIGUOUS_CHARS = {'å', 'Å', 'ñ', 'Ñ'}

# Normalize to lowercase for diacritic categorization
CHAR_TO_DIACRITIC = {
    'å': 'å',
    'Å': 'å',
    'ñ': 'ñ',
    'Ñ': 'ñ'
}

# Hard-coded book type
TARGET_BOOK_TYPE = "english-gurudev"

# Font prefixes to skip (Hindi/Bengali diacritics, not Sanskrit)
SKIP_FONT_PREFIXES = ("AARitu", "AATripti")

# IAST characters for word boundary detection
IAST_CHARS = "āīūṛṝḷḹṅṭḍṇśṣṃṁḥĀĪŪṚṜḶḸṄṬḌṆŚṢṂḤ"

# All dangerous glyphs (from extract_glyph_words.py)
# Include these in word pattern so words don't split at dangerous glyphs
DANGEROUS_GLYPHS = "äëéïöüòçßîùÄËÉÏÖÜÒÇÙ®µ√∂∫†ÿúÿÚ"

# Global replacement mapping for dangerous glyphs
# NOTE: å and ñ are NOT included because they are ambiguous (context-dependent)
GLOBAL_REPLACEMENTS = {
    "ä": "ā", "Ä": "Ā",
    "é": "ī", "É": "Ī",
    "ë": "ṇ", "Ë": "Ṇ",
    "ï": "ñ", "Ï": "Ñ",
    "ö": "ṭ", "Ö": "Ṭ",
    "ü": "ū", "Ü": "Ū",
    "ò": "ḍ", "Ò": "Ḍ",
    "ç": "ś", "Ç": "Ś",
    "ß": "ṣ",
    "î": "ī", "Î": "Ī",
    "®": "ṛ",
    "µ": "ṁ",
    "√": "ṇ",
    "∂": "ḍ",
    "∫": "ṅ",
    "ù": "ḥ", "Ù": "Ḥ",
    "†": "ṭ",
}


# =============================================================================
# AMBIGUOUS DIACRITIC WORD EXTRACTOR
# =============================================================================

class AmbiguousDiacriticExtractor:
    """
    Extracts words containing ambiguous diacritics (å, ñ) from PDF books.
    """

    def __init__(self):
        """Initialize the extractor."""
        self.db = PureBhaktiVaultDB()
        self.pdf_folder = Path(os.getenv("PDF_FOLDER", "./pdfs"))

        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")

        # Aggregation structure: (font_name, diacritic, word) -> stats
        # diacritic is normalized lowercase ('å' or 'ñ')
        self.stats: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # Track processed stats
        self.processed_count = 0
        self.total_books = 0

        # Track skipped fonts and compound simplifications
        self.skipped_fonts: Dict[str, int] = {}
        self.compound_simplifications = 0

        # Compile word extraction regex
        # Include IAST characters, ambiguous chars, dangerous glyphs, hyphens, apostrophes
        # IMPORTANT: Include dangerous glyphs so words aren't split at those characters
        ambiguous_chars_escaped = re.escape(''.join(AMBIGUOUS_CHARS))
        dangerous_glyphs_escaped = re.escape(DANGEROUS_GLYPHS)
        self.word_pattern = re.compile(
            rf"[A-Za-z{IAST_CHARS}{ambiguous_chars_escaped}{dangerous_glyphs_escaped}\-']+",
            re.UNICODE
        )

    def get_target_books(self, book_ids: List[int] = None) -> List[Dict[str, Any]]:
        """
        Get all books with target book type.

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
                        books.append({
                            'book_id': row[0],
                            'pdf_name': row[1]
                        })

                    return books
        except Exception as e:
            raise DatabaseError(f"Failed to query books: {e}")

    def apply_global_replacements(self, word: str) -> str:
        """
        Apply global IAST replacements to word.

        This replaces all dangerous glyphs EXCEPT å and ñ which are ambiguous.

        Args:
            word: Word containing dangerous glyphs

        Returns:
            Word with global replacements applied
        """
        corrected = word
        for dangerous_glyph, iast_char in GLOBAL_REPLACEMENTS.items():
            corrected = corrected.replace(dangerous_glyph, iast_char)
        return corrected

    def simplify_compound_word(self, word: str) -> List[str]:
        """
        Simplify compound words by extracting individual parts with ambiguous characters.

        For hyphenated compounds, split ALL compounds and return only parts containing å or ñ.
        This ensures each unique word part is analyzed independently, regardless of what
        compounds it appears in.

        Examples:
          "abhīñṭa-bhāva-anukūla" → ["abhīñṭa"] (only first part has ñ)
          "Kåñṇa-līlā" → ["Kåñṇa"] (only first part has å, ñ)
          "mahå-bhågå" → ["mahå", "bhågå"] (both parts have å, split into separate words)
          "rādhā-Kåñṇa" → ["Kåñṇa"] (only second part has ambiguous chars)
          "Kåñṇa" → ["Kåñṇa"] (no hyphen, return as single-item list)

        Args:
            word: Word to simplify

        Returns:
            List of word parts containing ambiguous characters
        """
        # If no hyphen, return as single-item list
        if '-' not in word:
            return [word]

        # Split by hyphen
        parts = word.split('-')

        # Find parts containing ambiguous characters
        parts_with_ambiguous = []
        for part in parts:
            if self.contains_ambiguous_char(part):
                parts_with_ambiguous.append(part)

        # If no parts have ambiguous chars, return original (shouldn't happen in practice)
        if not parts_with_ambiguous:
            return [word]

        # Return all parts with ambiguous chars as separate words
        return parts_with_ambiguous

    def extract_words_from_text(self, text: str) -> List[str]:
        """
        Extract words from text using regex.

        Args:
            text: Text to extract words from

        Returns:
            List of words
        """
        return self.word_pattern.findall(text)

    def contains_ambiguous_char(self, word: str) -> bool:
        """
        Check if word contains any ambiguous character.

        Args:
            word: Word to check

        Returns:
            True if word contains å, Å, ñ, or Ñ
        """
        return any(ch in AMBIGUOUS_CHARS for ch in word)

    def get_ambiguous_chars_in_word(self, word: str) -> Set[str]:
        """
        Get normalized ambiguous diacritics in word.

        Args:
            word: Word to analyze

        Returns:
            Set of normalized diacritics ('å', 'ñ')
        """
        diacritics = set()
        for ch in word:
            if ch in CHAR_TO_DIACRITIC:
                diacritics.add(CHAR_TO_DIACRITIC[ch])
        return diacritics

    def is_substring_of_existing(self, word: str, font_name: str, diacritic: str) -> bool:
        """
        Check if word is a substring of any existing word for same font+diacritic.

        Args:
            word: Word to check
            font_name: Font name
            diacritic: Normalized diacritic ('å' or 'ñ')

        Returns:
            True if word is substring of existing word
        """
        for (f, d, existing_word), _ in self.stats.items():
            if f == font_name and d == diacritic:
                if word != existing_word and word in existing_word:
                    return True
        return False

    def get_longer_words_containing(self, word: str, font_name: str, diacritic: str) -> List[str]:
        """
        Find existing words that contain this word as substring.

        Args:
            word: Word to search for
            font_name: Font name
            diacritic: Normalized diacritic

        Returns:
            List of longer words containing this word
        """
        longer_words = []
        for (f, d, existing_word), _ in self.stats.items():
            if f == font_name and d == diacritic:
                if word != existing_word and word in existing_word:
                    longer_words.append(existing_word)
        return longer_words

    def should_replace_with_shorter(self, _longer_word: str, _shorter_word: str) -> bool:
        """
        Determine if longer word should be replaced with shorter word.

        Since we split ALL compounds, we always prefer the shorter form for substring
        minimization.

        Args:
            _longer_word: Longer word (e.g., "Mahā-Kåñṇa") - not used, always replace
            _shorter_word: Shorter word (e.g., "Kåñṇa") - not used, always replace

        Returns:
            True (always replace with shorter form)
        """
        # Always prefer shorter form for substring minimization
        return True

    def scan_page(self, pdf_doc, page_num: int, book_id: int):
        """
        Scan a single page and extract words with ambiguous diacritics.

        Args:
            pdf_doc: PyMuPDF document object
            page_num: Page number (0-indexed)
            book_id: Book ID

        Returns:
            True if page had extractable text, False otherwise
        """
        page = pdf_doc[page_num]

        # Extract text with font information
        try:
            text_dict = page.get_text("dict")
        except Exception:
            return False

        if not text_dict or "blocks" not in text_dict:
            return False

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

                    # Extract words
                    words = self.extract_words_from_text(text)

                    for word in words:
                        # Check if word contains ambiguous characters
                        if not self.contains_ambiguous_char(word):
                            continue

                        # Apply global replacements FIRST (all dangerous glyphs except å and ñ)
                        corrected_word = self.apply_global_replacements(word)

                        # After global replacements, check if still contains ambiguous chars
                        if not self.contains_ambiguous_char(corrected_word):
                            continue

                        # Simplify compound words - returns list of parts with ambiguous chars
                        simplified_words = self.simplify_compound_word(corrected_word)

                        # Track compound word simplifications
                        if len(simplified_words) > 1 or (len(simplified_words) == 1 and simplified_words[0] != corrected_word):
                            self.compound_simplifications += 1

                        # Process each simplified word part
                        for simplified_word in simplified_words:
                            # After simplification, verify still contains ambiguous chars
                            if not self.contains_ambiguous_char(simplified_word):
                                continue

                            # Get all ambiguous diacritics in word
                            diacritics = self.get_ambiguous_chars_in_word(simplified_word)

                            # Process each diacritic separately
                            for diacritic in diacritics:
                                # Check if word is substring of existing words
                                if self.is_substring_of_existing(simplified_word, font_name, diacritic):
                                    continue  # Skip, we already have longer form

                                # Check if we have longer words that should be replaced
                                longer_words = self.get_longer_words_containing(simplified_word, font_name, diacritic)
                                for longer_word in longer_words:
                                    if self.should_replace_with_shorter(longer_word, simplified_word):
                                        # Remove longer word
                                        key = (font_name, diacritic, longer_word)
                                        if key in self.stats:
                                            del self.stats[key]

                                # Add or update word (using simplified_word)
                                key = (font_name, diacritic, simplified_word)

                                if key not in self.stats:
                                    self.stats[key] = {
                                        "count": 0,
                                        "book_ids": set()
                                    }

                                self.stats[key]["count"] += 1
                                self.stats[key]["book_ids"].add(book_id)

        return True

    def scan_book(self, book_info: Dict[str, Any]) -> bool:
        """
        Scan a single book.

        Args:
            book_info: Dict with book_id, pdf_name

        Returns:
            True if successful, False otherwise
        """
        book_id = book_info['book_id']
        pdf_name = book_info['pdf_name']
        pdf_path = self.pdf_folder / pdf_name

        if not pdf_path.exists():
            print(f"  ⚠️  PDF not found: {pdf_path}")
            return False

        try:
            pdf_doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"  ❌ Failed to open PDF: {e}")
            return False

        total_pages = len(pdf_doc)
        pages_with_text = 0

        print(f"  📖 Scanning {total_pages} pages...")

        # Scan each page
        for page_num in range(total_pages):
            if self.scan_page(pdf_doc, page_num, book_id):
                pages_with_text += 1

        pdf_doc.close()

        print(f"  ✅ Scanned {pages_with_text}/{total_pages} pages with text")
        return True

    def create_table_if_not_exists(self):
        """Create ambiguous_diacritic_words table if it doesn't exist."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS ambiguous_diacritic_words (
                            id SERIAL PRIMARY KEY,
                            font_name TEXT NOT NULL,
                            diacritic CHAR(1) NOT NULL,
                            word TEXT NOT NULL,
                            occurrence_count INTEGER NOT NULL,
                            book_ids JSONB NOT NULL,
                            created_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE(font_name, diacritic, word)
                        )
                    """)
                    conn.commit()
                    print("✅ Database table ready: ambiguous_diacritic_words")
        except Exception as e:
            raise DatabaseError(f"Failed to create table: {e}")

    def write_to_database(self):
        """Write aggregated results to database."""
        if not self.stats:
            print("  ⚠️  No data to write")
            return

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Delete existing entries (for reprocessing)
                    # Group by font to delete efficiently
                    fonts = set(key[0] for key in self.stats.keys())
                    for font_name in fonts:
                        cur.execute("""
                            DELETE FROM ambiguous_diacritic_words
                            WHERE font_name = %s
                        """, (font_name,))

                    # Insert new entries
                    query = """
                        INSERT INTO ambiguous_diacritic_words
                        (font_name, diacritic, word, occurrence_count, book_ids, created_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                        ON CONFLICT (font_name, diacritic, word)
                        DO UPDATE SET
                            occurrence_count = EXCLUDED.occurrence_count,
                            book_ids = EXCLUDED.book_ids
                    """

                    for (font_name, diacritic, word), data in self.stats.items():
                        book_ids_json = json.dumps(sorted(list(data["book_ids"])))
                        cur.execute(query, (
                            font_name,
                            diacritic,
                            word,
                            data["count"],
                            book_ids_json
                        ))

                    conn.commit()
                    print(f"  💾 Wrote {len(self.stats)} unique word entries to database")
        except Exception as e:
            raise DatabaseError(f"Failed to write to database: {e}")

    def run(self, book_ids: List[int] = None):
        """
        Main execution method.

        Args:
            book_ids: Optional list of specific book IDs to process
        """
        print("=" * 80)
        print("📚 AMBIGUOUS DIACRITIC WORD EXTRACTOR")
        print("=" * 80)
        print()
        print("Target characters: å (å/Å → ā or ṛ), ñ (ñ/Ñ → ñ or ṣ)")
        print()

        # Ensure table exists
        self.create_table_if_not_exists()
        print()

        # Get target books
        if book_ids:
            print(f"🔍 Querying specific books: {book_ids}...")
        else:
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
            pdf_name = book_info['pdf_name']

            print(f"[{i}/{self.total_books}] Book {book_id}: {pdf_name}")

            # Scan the book
            success = self.scan_book(book_info)

            if success:
                self.processed_count += 1

            print()

        # Write all results to database
        print("=" * 80)
        print("💾 Writing results to database...")
        print("=" * 80)
        self.write_to_database()
        print()

        # Print summary
        print("=" * 80)
        print("📊 EXTRACTION SUMMARY")
        print("=" * 80)
        print(f"Total books processed: {self.processed_count}/{self.total_books}")
        print(f"Unique (font, diacritic, word) entries: {len(self.stats)}")
        print()

        # Summary by diacritic
        diacritic_counts = defaultdict(int)
        for (_, diacritic, _), _ in self.stats.items():
            diacritic_counts[diacritic] += 1

        print("Breakdown by diacritic:")
        for diacritic in sorted(diacritic_counts.keys()):
            count = diacritic_counts[diacritic]
            print(f"  {diacritic}: {count:,} unique words")
        print()

        # Optimization statistics
        print("Optimization statistics:")
        print(f"  Compound words simplified: {self.compound_simplifications:,}")
        if self.skipped_fonts:
            print(f"  Skipped fonts (Hindi/Bengali): {len(self.skipped_fonts)} fonts")
            total_skipped_spans = sum(self.skipped_fonts.values())
            print(f"  Total spans skipped: {total_skipped_spans:,}")
            # Show top 3 skipped fonts
            top_skipped = sorted(self.skipped_fonts.items(), key=lambda x: x[1], reverse=True)[:3]
            if top_skipped:
                print("  Top skipped fonts:")
                for font, count in top_skipped:
                    print(f"    {font}: {count:,} spans")
        print()

        print("✅ Extraction complete!")
        print()
        print("💡 Query examples:")
        print("   -- View all words for specific diacritic:")
        print("   SELECT font_name, word, occurrence_count, book_ids")
        print("   FROM ambiguous_diacritic_words WHERE diacritic = 'å';")
        print()
        print("   -- Find most common words:")
        print("   SELECT diacritic, word, SUM(occurrence_count) as total")
        print("   FROM ambiguous_diacritic_words")
        print("   GROUP BY diacritic, word ORDER BY total DESC LIMIT 20;")
        print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract words with ambiguous diacritics (å, ñ) from PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--book-ids",
        type=str,
        help="Comma-separated list of book IDs to process (e.g., '5,7,15'). For testing purposes."
    )

    args = parser.parse_args()

    # Parse book IDs if provided
    book_ids = None
    if args.book_ids:
        try:
            book_ids = [int(bid.strip()) for bid in args.book_ids.split(',')]
        except ValueError:
            print("❌ ERROR: Invalid book IDs format. Use comma-separated integers (e.g., '5,7,15')")
            sys.exit(1)

    try:
        extractor = AmbiguousDiacriticExtractor()
        extractor.run(book_ids)
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
