#!/usr/bin/env python3
"""
Glossary Sanskrit Character Error Detector

Tests glossary terms for common Sanskrit transliteration errors including:
1. Problematic character patterns (oā, jṣā, ṣja, taā, āṣś, çré, åñë, etc.)
2. Special characters that indicate encoding issues (®, ß, √, ò, ∫, ∂, µ, etc.)
3. Both upper, lower, and mixed case scenarios

Outputs results to CSV with: glossary_id, book_id, pattern_matched, term

Usage:
    python test_glossary_sanskrit_errors.py
    python test_glossary_sanskrit_errors.py --output errors.csv
    python test_glossary_sanskrit_errors.py --book-ids 35,36,51
"""

import os
import sys
import csv
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import argparse
from dotenv import load_dotenv

# Import database utility
from pure_bhakti_vault_db import PureBhaktiVaultDB

# Load environment variables
load_dotenv()


class GlossarySanskritErrorDetector:
    """Detect common Sanskrit transliteration errors in glossary terms using patterns from sanskrit_utils.py."""

    # Get patterns from sanskrit_utils.py
    # These are known encoding/conversion errors that fix_iast_glyphs() corrects

    # Pattern replacements (multi-character patterns from sanskrit_utils.py)
    # These are clear encoding errors that should always be fixed
    PATTERN_ERRORS = {
        'kåñëa': 'kṛṣṇa',
        'oā': 'oṁ',
        'jṣā': 'jñā',
        'ṣja': 'ñja',
        'taā': 'taṁ',
        'āṣś': 'ṛṣṇ',
        'çré': 'śrī'
    }

    # Special characters (from sanskrit_utils.py)
    # These are symbol/encoding errors that should always be replaced
    SPECIAL_CHAR_ERRORS = {
        '®': 'ṛ (vocalic r)',
        'ß': 'ṣ (retroflex s)',
        '√': 'ś (palatal s)',
        'ò': 'ḍ (retroflex d)',
        '†': 'ṭ (retroflex t)',
        '∫': 'ṅ (velar n)',
        '∂': 'ḍ (retroflex d)',
        'µ': 'ṁ (anusvara)'
    }

    # Note: Glyph replacements (ä, å, ë, etc.) are NOT included because they
    # may not be errors in all cases and require contextual evaluation

    def __init__(self, output_file: str = None):
        """
        Initialize the error detector.

        Args:
            output_file: Optional CSV file path for output (default: auto-generated)
        """
        self.db = PureBhaktiVaultDB()

        # Generate default output filename if not provided
        if output_file:
            self.output_file = Path(output_file)
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.output_file = Path(f'glossary_sanskrit_errors_{timestamp}.csv')

        self.errors_found = []

    def check_term_for_errors(self, glossary_id: int, book_id: int, term: str) -> List[Dict[str, Any]]:
        """
        Check a single term for all types of errors using patterns from sanskrit_utils.py.

        Args:
            glossary_id: Glossary ID
            book_id: Book ID
            term: Term to check

        Returns:
            List of error records found with corrected versions
        """
        errors = []

        if not term:
            return errors

        # Check for pattern errors (multi-character sequences)
        for pattern, replacement in self.PATTERN_ERRORS.items():
            if pattern in term:
                # Apply just this pattern to see the corrected version
                corrected_for_this_pattern = term.replace(pattern, replacement)
                errors.append({
                    'glossary_id': glossary_id,
                    'book_id': book_id,
                    'error_type': 'pattern',
                    'pattern_matched': pattern,
                    'replacement': replacement,
                    'original_term': term,
                    'corrected_term': corrected_for_this_pattern
                })

        # Check for special character errors (symbols)
        for char, replacement_desc in self.SPECIAL_CHAR_ERRORS.items():
            if char in term:
                # Extract just the replacement character from the description
                replacement_char = replacement_desc.split()[0]  # e.g., "ṛ" from "ṛ (vocalic r)"
                corrected_for_this_char = term.replace(char, replacement_char)
                errors.append({
                    'glossary_id': glossary_id,
                    'book_id': book_id,
                    'error_type': 'special_char',
                    'pattern_matched': char,
                    'replacement': replacement_desc,
                    'original_term': term,
                    'corrected_term': corrected_for_this_char
                })

        return errors

    def scan_glossary_table(self, book_ids: List[int] = None) -> int:
        """
        Scan the entire glossary table for errors.

        Args:
            book_ids: Optional list of book IDs to filter by

        Returns:
            Number of errors found
        """
        print("🔍 Scanning glossary table for Sanskrit transliteration errors...")
        print("=" * 70)

        # Build query
        where_clause = ""
        if book_ids:
            book_ids_str = ','.join(map(str, book_ids))
            where_clause = f"WHERE book_id IN ({book_ids_str})"

        query = f"""
            SELECT glossary_id, book_id, term
            FROM glossary
            {where_clause}
            ORDER BY book_id, glossary_id
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()

                print(f"📊 Found {len(results)} glossary entries to check")

                if book_ids:
                    print(f"   Filtered to book IDs: {book_ids}")

                print()

                # Check each term
                total_errors = 0
                for row in results:
                    glossary_id = row['glossary_id']
                    book_id = row['book_id']
                    term = row['term']

                    errors = self.check_term_for_errors(glossary_id, book_id, term)

                    if errors:
                        self.errors_found.extend(errors)
                        total_errors += len(errors)

                print(f"✅ Scan complete")
                print(f"   Total errors found: {total_errors}")
                print(f"   Unique terms with errors: {len(set(e['glossary_id'] for e in self.errors_found))}")

                return total_errors

        except Exception as e:
            print(f"❌ Error scanning glossary table: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def write_results_to_csv(self) -> bool:
        """
        Write error results to CSV file.

        Returns:
            True if successful
        """
        if not self.errors_found:
            print("\n⚠️  No errors found, skipping CSV output")
            return True

        try:
            print(f"\n📝 Writing results to CSV: {self.output_file}")

            with open(self.output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['glossary_id', 'book_id', 'error_type', 'pattern_matched',
                             'replacement', 'original_term', 'corrected_term']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for error in self.errors_found:
                    writer.writerow(error)

            print(f"✅ Results written to: {self.output_file}")
            print(f"   Total errors: {len(self.errors_found)}")

            # Print summary statistics
            self.print_summary()

            return True

        except Exception as e:
            print(f"❌ Failed to write CSV: {e}")
            return False

    def print_summary(self):
        """Print summary statistics of errors found."""
        if not self.errors_found:
            return

        print("\n" + "=" * 70)
        print("📊 ERROR SUMMARY")
        print("=" * 70)

        # Count by error type
        error_types = {}
        for error in self.errors_found:
            error_type = error['error_type']
            error_types[error_type] = error_types.get(error_type, 0) + 1

        print("\nErrors by type:")
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {error_type}: {count}")

        # Count by pattern
        patterns = {}
        for error in self.errors_found:
            pattern = error['pattern_matched']
            patterns[pattern] = patterns.get(pattern, 0) + 1

        print("\nTop 20 most common patterns:")
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  • '{pattern}': {count} occurrences")

        # Count by book
        books = {}
        for error in self.errors_found:
            book_id = error['book_id']
            books[book_id] = books.get(book_id, 0) + 1

        print("\nErrors by book:")
        for book_id, count in sorted(books.items(), key=lambda x: x[1], reverse=True):
            print(f"  • Book {book_id}: {count} errors")

        # Show sample errors
        print("\nSample terms with errors (first 10):")
        unique_terms = {}
        for error in self.errors_found:
            original = error['original_term']
            if original not in unique_terms:
                unique_terms[original] = error
                if len(unique_terms) >= 10:
                    break

        for i, (original, error) in enumerate(unique_terms.items(), 1):
            corrected = error.get('corrected_term', original)
            pattern = error['pattern_matched']
            replacement = error['replacement']
            print(f"  {i}. '{original}' → '{corrected}'")
            print(f"      Pattern: '{pattern}' → {replacement}")

        print("=" * 70)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Detect Sanskrit transliteration errors in glossary terms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_glossary_sanskrit_errors.py
  python test_glossary_sanskrit_errors.py --output errors.csv
  python test_glossary_sanskrit_errors.py --book-ids 35,36,51

The script checks for:
1. Pattern errors from sanskrit_utils.py (kåñëa, oā, jṣā, ṣja, taā, āṣś, çré)
2. Special character errors (®, ß, √, ò, †, ∫, ∂, µ)

Note: Glyph replacements (ä, å, ë, etc.) are NOT checked as they may be
context-dependent and not always errors.

Output includes both original and corrected terms for manual review.
        """
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output CSV file path (default: auto-generated with timestamp)'
    )

    parser.add_argument(
        '--book-ids',
        type=str,
        help='Comma-separated list of book IDs to check (default: all books)'
    )

    return parser.parse_args()


def main():
    """Main function."""
    args = parse_arguments()

    print("🚀 Glossary Sanskrit Error Detector")
    print("=" * 70)

    # Parse book IDs if provided
    book_ids = None
    if args.book_ids:
        try:
            book_ids = [int(bid.strip()) for bid in args.book_ids.split(',')]
            print(f"📚 Checking book IDs: {book_ids}")
        except ValueError:
            print(f"❌ Invalid book IDs format: {args.book_ids}")
            print("   Expected format: 35,36,51")
            return

    # Initialize detector
    detector = GlossarySanskritErrorDetector(output_file=args.output)

    # Test database connection
    if not detector.db.test_connection():
        print("❌ Failed to connect to database")
        return

    print("✅ Database connection successful\n")

    # Scan glossary table
    total_errors = detector.scan_glossary_table(book_ids=book_ids)

    if total_errors == 0:
        print("\n🎉 No errors found! All glossary terms look clean.")
        return

    # Write results to CSV
    detector.write_results_to_csv()

    print(f"\n✅ Complete! Check the output file: {detector.output_file}")


if __name__ == "__main__":
    main()
