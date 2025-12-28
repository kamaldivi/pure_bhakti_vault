#!/usr/bin/env python3
"""
Diagnose TOC Update Issues

This script analyzes why some TOC records were skipped and why validation failures occurred.
"""

import sys
import argparse
from typing import Dict, List

# Add the src directory to the path
sys.path.append('./src/prod_utils')

try:
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Required dependencies not found: {e}")
    sys.exit(1)

# Load environment variables
load_dotenv()


class TOCDiagnostics:
    """Diagnose issues with TOC page number updates."""

    def __init__(self):
        """Initialize the diagnostics with database connection."""
        self.db = PureBhaktiVaultDB()

    def analyze_skipped_records(self, book_id: int = None) -> Dict:
        """
        Analyze why records were skipped during the update.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Dictionary with analysis results
        """
        print("🔍 Analyzing skipped records...")

        # Build WHERE clause for book filter
        where_book = ""
        params_book = []
        if book_id:
            where_book = "WHERE book_id = %s"
            params_book = [book_id]

        # 1. Records with NULL or empty page_label_raw
        null_empty_query = f"""
            SELECT book_id, COUNT(*) as count
            FROM table_of_contents
            {where_book}
            AND (page_label_raw IS NULL OR TRIM(page_label_raw) = '')
            GROUP BY book_id
            ORDER BY book_id
        """

        null_empty_results = self.db.execute_query(null_empty_query, params_book, 'all')

        # 2. Records with page_label_raw but no matching page_map entry
        no_match_query = f"""
            SELECT t.book_id, COUNT(*) as count
            FROM table_of_contents t
            LEFT JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE p.page_label IS NULL
            AND t.page_label_raw IS NOT NULL
            AND TRIM(t.page_label_raw) != ''
            {where_book.replace('WHERE', 'AND') if where_book else ''}
            GROUP BY t.book_id
            ORDER BY t.book_id
        """

        params_no_match = params_book if book_id else []
        no_match_results = self.db.execute_query(no_match_query, params_no_match, 'all')

        # 3. Sample records with no matches
        sample_no_match_query = f"""
            SELECT t.book_id, t.toc_id, t.toc_label, t.page_label_raw
            FROM table_of_contents t
            LEFT JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE p.page_label IS NULL
            AND t.page_label_raw IS NOT NULL
            AND TRIM(t.page_label_raw) != ''
            {where_book.replace('WHERE', 'AND') if where_book else ''}
            ORDER BY t.book_id, t.toc_id
            LIMIT 10
        """

        sample_no_match = self.db.execute_query(sample_no_match_query, params_no_match, 'all')

        # 4. Records where page_number already matches page_map
        already_correct_query = f"""
            SELECT t.book_id, COUNT(*) as count
            FROM table_of_contents t
            INNER JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE t.page_number = p.page_number
            {where_book.replace('WHERE', 'AND') if where_book else ''}
            GROUP BY t.book_id
            ORDER BY t.book_id
        """

        already_correct_results = self.db.execute_query(already_correct_query, params_no_match, 'all')

        return {
            'null_empty': null_empty_results,
            'no_match': no_match_results,
            'sample_no_match': sample_no_match,
            'already_correct': already_correct_results
        }

    def analyze_validation_failures(self, book_id: int = None) -> Dict:
        """
        Analyze validation failures (mismatched page numbers).

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Dictionary with validation failure analysis
        """
        print("❌ Analyzing validation failures...")

        where_book = ""
        params = []
        if book_id:
            where_book = "AND t.book_id = %s"
            params = [book_id]

        # Find mismatched records
        mismatch_query = f"""
            SELECT
                t.book_id,
                t.toc_id,
                t.toc_label,
                t.page_label_raw,
                t.page_number as toc_page_number,
                p.page_number as map_page_number,
                p.page_label as map_page_label,
                p.page_type
            FROM table_of_contents t
            INNER JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE t.page_number <> p.page_number
            {where_book}
            ORDER BY t.book_id, t.toc_id
        """

        mismatches = self.db.execute_query(mismatch_query, params, 'all')

        # Count by book
        mismatch_count_query = f"""
            SELECT
                t.book_id,
                COUNT(*) as mismatch_count
            FROM table_of_contents t
            INNER JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE t.page_number <> p.page_number
            {where_book}
            GROUP BY t.book_id
            ORDER BY t.book_id
        """

        mismatch_counts = self.db.execute_query(mismatch_count_query, params, 'all')

        return {
            'mismatches': mismatches,
            'mismatch_counts': mismatch_counts
        }

    def analyze_page_label_patterns(self, book_id: int = None) -> Dict:
        """
        Analyze patterns in page labels that might cause matching issues.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Dictionary with pattern analysis
        """
        print("🔤 Analyzing page label patterns...")

        where_book = ""
        params = []
        if book_id:
            where_book = "WHERE book_id = %s"
            params = [book_id]

        # Find unusual page_label_raw patterns
        unusual_patterns_query = f"""
            SELECT
                page_label_raw,
                COUNT(*) as frequency,
                STRING_AGG(DISTINCT book_id::text, ', ') as book_ids
            FROM table_of_contents
            {where_book}
            AND page_label_raw IS NOT NULL
            AND TRIM(page_label_raw) != ''
            AND page_label_raw !~ '^[0-9]+$'  -- Not just numbers
            AND page_label_raw !~ '^[ivxlcdm]+$'  -- Not just roman numerals
            GROUP BY page_label_raw
            ORDER BY frequency DESC, page_label_raw
            LIMIT 20
        """

        unusual_patterns = self.db.execute_query(unusual_patterns_query, params, 'all')

        # Find page_label_raw with special characters
        special_chars_query = f"""
            SELECT
                page_label_raw,
                LENGTH(page_label_raw) as length,
                toc_id,
                book_id,
                toc_label
            FROM table_of_contents
            {where_book}
            AND page_label_raw IS NOT NULL
            AND (
                page_label_raw ~ '[^a-zA-Z0-9ivxlcdm\-\.]'  -- Contains special chars
                OR LENGTH(page_label_raw) > 10  -- Too long
                OR page_label_raw ~ '\s'  -- Contains spaces
            )
            ORDER BY book_id, toc_id
            LIMIT 20
        """

        special_chars = self.db.execute_query(special_chars_query, params, 'all')

        return {
            'unusual_patterns': unusual_patterns,
            'special_chars': special_chars
        }

    def get_overall_statistics(self, book_id: int = None) -> Dict:
        """
        Get overall statistics about TOC and page_map data.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Dictionary with overall statistics
        """
        print("📊 Getting overall statistics...")

        where_book = ""
        params = []
        if book_id:
            where_book = "WHERE book_id = %s"
            params = [book_id]

        # TOC statistics
        toc_stats_query = f"""
            SELECT
                book_id,
                COUNT(*) as total_toc_records,
                COUNT(page_label_raw) as records_with_page_label_raw,
                COUNT(*) - COUNT(page_label_raw) as records_without_page_label_raw,
                COUNT(CASE WHEN TRIM(page_label_raw) = '' THEN 1 END) as records_with_empty_page_label_raw
            FROM table_of_contents
            {where_book}
            GROUP BY book_id
            ORDER BY book_id
        """

        toc_stats = self.db.execute_query(toc_stats_query, params, 'all')

        # Page map statistics
        page_map_stats_query = f"""
            SELECT
                book_id,
                COUNT(*) as total_page_map_records,
                COUNT(DISTINCT page_label) as unique_page_labels,
                COUNT(CASE WHEN page_label IS NULL OR TRIM(page_label) = '' THEN 1 END) as records_without_page_label
            FROM page_map
            {where_book}
            GROUP BY book_id
            ORDER BY book_id
        """

        page_map_stats = self.db.execute_query(page_map_stats_query, params, 'all')

        # Matching statistics
        matching_stats_query = f"""
            SELECT
                t.book_id,
                COUNT(t.toc_id) as total_toc_with_labels,
                COUNT(p.page_number) as matching_page_map_records,
                COUNT(t.toc_id) - COUNT(p.page_number) as unmatched_toc_records
            FROM table_of_contents t
            LEFT JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            WHERE t.page_label_raw IS NOT NULL
            AND TRIM(t.page_label_raw) != ''
            {where_book.replace('WHERE', 'AND') if where_book else ''}
            GROUP BY t.book_id
            ORDER BY t.book_id
        """

        params_matching = params if book_id else []
        matching_stats = self.db.execute_query(matching_stats_query, params_matching, 'all')

        return {
            'toc_stats': toc_stats,
            'page_map_stats': page_map_stats,
            'matching_stats': matching_stats
        }

    def print_analysis_report(self, book_id: int = None):
        """Print a comprehensive analysis report."""
        print("=" * 80)
        print("📋 TOC UPDATE DIAGNOSTICS REPORT")
        print("=" * 80)

        if book_id:
            print(f"🔍 Analysis for Book ID: {book_id}")
        else:
            print("🔍 Analysis for ALL books")
        print()

        # Get overall statistics
        stats = self.get_overall_statistics(book_id)

        print("📊 OVERALL STATISTICS")
        print("-" * 40)
        for stat in stats['toc_stats']:
            book_id_display = stat['book_id']
            print(f"Book {book_id_display}:")
            print(f"  Total TOC records: {stat['total_toc_records']}")
            print(f"  Records with page_label_raw: {stat['records_with_page_label_raw']}")
            print(f"  Records without page_label_raw: {stat['records_without_page_label_raw']}")
            print(f"  Records with empty page_label_raw: {stat['records_with_empty_page_label_raw']}")
            print()

        for stat in stats['matching_stats']:
            book_id_display = stat['book_id']
            print(f"Book {book_id_display} Matching:")
            print(f"  TOC records with labels: {stat['total_toc_with_labels']}")
            print(f"  Matching page_map records: {stat['matching_page_map_records']}")
            print(f"  Unmatched TOC records: {stat['unmatched_toc_records']}")
            print()

        # Analyze skipped records
        skipped_analysis = self.analyze_skipped_records(book_id)

        print("⏭️  SKIPPED RECORDS ANALYSIS")
        print("-" * 40)

        print("Records with NULL/empty page_label_raw:")
        if skipped_analysis['null_empty']:
            for result in skipped_analysis['null_empty']:
                print(f"  Book {result['book_id']}: {result['count']} records")
        else:
            print("  None found")
        print()

        print("Records with page_label_raw but no matching page_map:")
        if skipped_analysis['no_match']:
            for result in skipped_analysis['no_match']:
                print(f"  Book {result['book_id']}: {result['count']} records")
        else:
            print("  None found")
        print()

        print("Sample unmatched records:")
        if skipped_analysis['sample_no_match']:
            for record in skipped_analysis['sample_no_match'][:5]:
                print(f"  Book {record['book_id']}, TOC {record['toc_id']}: '{record['page_label_raw']}' - {record['toc_label'][:50]}...")
        else:
            print("  None found")
        print()

        # Analyze validation failures
        validation_analysis = self.analyze_validation_failures(book_id)

        print("❌ VALIDATION FAILURES")
        print("-" * 40)

        if validation_analysis['mismatch_counts']:
            for result in validation_analysis['mismatch_counts']:
                print(f"Book {result['book_id']}: {result['mismatch_count']} mismatched records")
            print()

            print("Sample mismatched records:")
            for mismatch in validation_analysis['mismatches'][:10]:
                print(f"  Book {mismatch['book_id']}, TOC {mismatch['toc_id']}: "
                      f"Raw='{mismatch['page_label_raw']}' TOC_page={mismatch['toc_page_number']} "
                      f"Map_page={mismatch['map_page_number']} - {mismatch['toc_label'][:40]}...")
        else:
            print("✅ No validation failures found")
        print()

        # Analyze page label patterns
        pattern_analysis = self.analyze_page_label_patterns(book_id)

        print("🔤 PAGE LABEL PATTERN ANALYSIS")
        print("-" * 40)

        print("Unusual page_label_raw patterns:")
        if pattern_analysis['unusual_patterns']:
            for pattern in pattern_analysis['unusual_patterns'][:10]:
                print(f"  '{pattern['page_label_raw']}': {pattern['frequency']} times (Books: {pattern['book_ids']})")
        else:
            print("  None found")
        print()

        print("Page labels with special characters:")
        if pattern_analysis['special_chars']:
            for record in pattern_analysis['special_chars'][:5]:
                print(f"  Book {record['book_id']}, TOC {record['toc_id']}: "
                      f"'{record['page_label_raw']}' (len={record['length']}) - {record['toc_label'][:40]}...")
        else:
            print("  None found")
        print()

        print("=" * 80)


def main():
    """Main function to handle command line execution."""
    parser = argparse.ArgumentParser(
        description="Diagnose TOC update issues"
    )
    parser.add_argument(
        '--book-id',
        type=int,
        help='Analyze specific book ID only (optional)'
    )

    args = parser.parse_args()

    try:
        diagnostics = TOCDiagnostics()

        # Test database connection
        if not diagnostics.db.test_connection():
            print("Error: Failed to connect to database")
            sys.exit(1)

        # Run the analysis
        diagnostics.print_analysis_report(args.book_id)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()