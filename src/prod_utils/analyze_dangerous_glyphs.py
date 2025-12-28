#!/usr/bin/env python3
"""
Analyze Dangerous Glyphs Across Books

Aggregates dangerous glyph data across all books to identify:
- Total occurrence counts per (font_name, glyph)
- Combined unique sample words from all books
- Font-specific corruption patterns

This analysis helps derive:
- Global replacement rules (glyphs that behave the same across all fonts)
- Font-specific replacement rules (glyphs that vary by font)

Requirements:
    pip install psycopg2-binary python-dotenv tabulate

Usage:
    python analyze_dangerous_glyphs.py                    # Auto-exports CSV to PROCESS_FOLDER
    python analyze_dangerous_glyphs.py --no-csv           # Display only, no CSV export
    python analyze_dangerous_glyphs.py --export-csv custom.csv  # Export to custom path
    python analyze_dangerous_glyphs.py --glyph ä          # Filter by glyph + auto-export
    python analyze_dangerous_glyphs.py --font GaraScsmDReg  # Filter by font + auto-export
"""

import os
import sys
import json
import csv
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Import database utility
sys.path.insert(0, str(Path(__file__).parent))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# Load environment variables
load_dotenv()


class DangerousGlyphAnalyzer:
    """
    Analyzes dangerous glyph data aggregated across all books.
    """

    def __init__(self):
        """Initialize the analyzer."""
        self.db = PureBhaktiVaultDB()
        self.process_folder = Path(os.getenv("PROCESS_FOLDER", "./process_output"))

        # Ensure process folder exists
        self.process_folder.mkdir(parents=True, exist_ok=True)

    def get_aggregated_data(
        self,
        glyph_filter: Optional[str] = None,
        font_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated dangerous glyph data across all books.

        Args:
            glyph_filter: Optional glyph to filter by (e.g., 'ä')
            font_filter: Optional font name to filter by (e.g., 'GaraScsmDReg')

        Returns:
            List of dicts with font_name, glyph, unicode, total_occurrences,
            unique_sample_words, book_count, books_affected
        """
        # Build WHERE clause based on filters
        where_clauses = []
        params = []

        if glyph_filter:
            where_clauses.append("glyph = %s")
            params.append(glyph_filter)

        if font_filter:
            where_clauses.append("font_name = %s")
            params.append(font_filter)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = f"""
            SELECT
                font_name,
                glyph,
                unicode_codepoint,
                SUM(occurrence_count) as total_occurrences,
                jsonb_agg(sample_words) as all_sample_words,
                COUNT(DISTINCT book_id) as book_count,
                array_agg(DISTINCT book_id ORDER BY book_id) as books_affected
            FROM dangerous_glyph_words
            {where_sql}
            GROUP BY font_name, glyph, unicode_codepoint
            ORDER BY total_occurrences DESC, font_name, glyph
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    results = cur.fetchall()

                    aggregated = []
                    for row in results:
                        font_name, glyph, unicode, total_occ, all_words_json, book_count, books = row

                        # Combine and deduplicate sample words from all books
                        all_words = []
                        if isinstance(all_words_json, str):
                            all_words_data = json.loads(all_words_json)
                        else:
                            all_words_data = all_words_json

                        # Flatten nested arrays and deduplicate
                        unique_words = set()
                        for words_array in all_words_data:
                            if isinstance(words_array, list):
                                unique_words.update(words_array)

                        all_words = sorted(list(unique_words))

                        aggregated.append({
                            'font_name': font_name,
                            'glyph': glyph,
                            'unicode': unicode,
                            'total_occurrences': total_occ,
                            'unique_sample_words': all_words,
                            'word_count': len(all_words),
                            'book_count': book_count,
                            'books_affected': books
                        })

                    return aggregated
        except Exception as e:
            raise DatabaseError(f"Failed to query aggregated data: {e}")

    def display_table(self, data: List[Dict[str, Any]], max_words: int = 10):
        """
        Display aggregated data in a formatted table.

        Args:
            data: List of aggregated data dicts
            max_words: Maximum number of sample words to display per row
        """
        if not data:
            print("No data found.")
            return

        print("=" * 120)
        print("DANGEROUS GLYPH ANALYSIS - AGGREGATED ACROSS ALL BOOKS")
        print("=" * 120)
        print()

        if HAS_TABULATE:
            # Prepare table data
            headers = ["Font", "Glyph", "Unicode", "Total Occ.", "Books", "Unique Words", "Sample Words"]
            rows = []

            for item in data:
                sample_words = item['unique_sample_words'][:max_words]
                words_display = ', '.join(sample_words)
                if len(item['unique_sample_words']) > max_words:
                    words_display += f" ... (+{len(item['unique_sample_words']) - max_words} more)"

                rows.append([
                    item['font_name'],
                    item['glyph'],
                    item['unicode'],
                    f"{item['total_occurrences']:,}",
                    item['book_count'],
                    item['word_count'],
                    words_display
                ])

            print(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            # Fallback: simple text format
            for i, item in enumerate(data, 1):
                print(f"{i}. Font: {item['font_name']}")
                print(f"   Glyph: \"{item['glyph']}\" ({item['unicode']})")
                print(f"   Total Occurrences: {item['total_occurrences']:,} across {item['book_count']} book(s)")
                print(f"   Unique Sample Words ({item['word_count']}): {', '.join(item['unique_sample_words'][:max_words])}...")
                print(f"   Books Affected: {item['books_affected']}")
                print()

        print("=" * 120)
        print(f"Total entries: {len(data)}")
        print()

    def generate_default_csv_path(self, glyph_filter: Optional[str] = None, font_filter: Optional[str] = None) -> Path:
        """
        Generate default CSV output path with timestamp.

        Args:
            glyph_filter: Optional glyph filter being used
            font_filter: Optional font filter being used

        Returns:
            Path object for the CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create descriptive filename based on filters
        if glyph_filter and font_filter:
            filename = f"dangerous_glyphs_{glyph_filter}_{font_filter}_{timestamp}.csv"
        elif glyph_filter:
            filename = f"dangerous_glyphs_{glyph_filter}_{timestamp}.csv"
        elif font_filter:
            filename = f"dangerous_glyphs_{font_filter}_{timestamp}.csv"
        else:
            filename = f"dangerous_glyphs_analysis_{timestamp}.csv"

        return self.process_folder / filename

    def export_csv(self, data: List[Dict[str, Any]], output_path: str):
        """
        Export aggregated data to CSV.

        Args:
            data: List of aggregated data dicts
            output_path: Path to output CSV file
        """
        if not data:
            print("No data to export.")
            return

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'font_name',
                    'glyph',
                    'unicode_codepoint',
                    'total_occurrences',
                    'book_count',
                    'books_affected',
                    'unique_word_count',
                    'sample_words'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for item in data:
                    writer.writerow({
                        'font_name': item['font_name'],
                        'glyph': item['glyph'],
                        'unicode_codepoint': item['unicode'],
                        'total_occurrences': item['total_occurrences'],
                        'book_count': item['book_count'],
                        'books_affected': ','.join(map(str, item['books_affected'])),
                        'unique_word_count': item['word_count'],
                        'sample_words': ' | '.join(item['unique_sample_words'])
                    })

            print(f"✅ Exported {len(data)} entries to: {output_path}")
        except Exception as e:
            print(f"❌ Export failed: {e}")
            raise

    def display_summary_stats(self, data: List[Dict[str, Any]]):
        """
        Display summary statistics.

        Args:
            data: List of aggregated data dicts
        """
        if not data:
            return

        total_occurrences = sum(item['total_occurrences'] for item in data)
        unique_fonts = len(set(item['font_name'] for item in data))
        unique_glyphs = len(set(item['glyph'] for item in data))

        print("📊 SUMMARY STATISTICS")
        print("=" * 60)
        print(f"Total unique (font, glyph) combinations: {len(data)}")
        print(f"Total occurrences across all books: {total_occurrences:,}")
        print(f"Unique fonts with dangerous glyphs: {unique_fonts}")
        print(f"Unique dangerous glyphs found: {unique_glyphs}")
        print()

        # Top 5 most common glyphs (aggregated across fonts)
        glyph_totals = {}
        for item in data:
            glyph = item['glyph']
            glyph_totals[glyph] = glyph_totals.get(glyph, 0) + item['total_occurrences']

        top_glyphs = sorted(glyph_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        print("Top 5 Most Common Dangerous Glyphs (across all fonts):")
        for glyph, count in top_glyphs:
            print(f"  \"{glyph}\": {count:,} occurrences")
        print()

        # Top 5 fonts with most dangerous glyphs
        font_totals = {}
        for item in data:
            font = item['font_name']
            font_totals[font] = font_totals.get(font, 0) + item['total_occurrences']

        top_fonts = sorted(font_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        print("Top 5 Fonts with Most Dangerous Glyphs:")
        for font, count in top_fonts:
            print(f"  {font}: {count:,} occurrences")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze dangerous glyphs aggregated across all books",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show all aggregated data (auto-exports to PROCESS_FOLDER)
  python analyze_dangerous_glyphs.py

  # Display only, no CSV export
  python analyze_dangerous_glyphs.py --no-csv

  # Filter by specific glyph (auto-exports)
  python analyze_dangerous_glyphs.py --glyph ä

  # Filter by specific font (auto-exports)
  python analyze_dangerous_glyphs.py --font GaraScsmDReg

  # Export to custom location (overrides PROCESS_FOLDER)
  python analyze_dangerous_glyphs.py --export-csv /custom/path/report.csv

  # Combine filters with custom export
  python analyze_dangerous_glyphs.py --glyph å --export-csv a_ring_analysis.csv
        """
    )
    parser.add_argument(
        "--glyph",
        type=str,
        help="Filter by specific glyph (e.g., 'ä', 'å', '®')"
    )
    parser.add_argument(
        "--font",
        type=str,
        help="Filter by specific font name (e.g., 'GaraScsmDReg')"
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        metavar="FILE",
        help="Export results to CSV file (optional: overrides default auto-export to PROCESS_FOLDER)"
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Disable automatic CSV export"
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=10,
        help="Maximum sample words to display per row (default: 10)"
    )

    args = parser.parse_args()

    try:
        analyzer = DangerousGlyphAnalyzer()

        print("🔍 Querying dangerous glyph data...")
        data = analyzer.get_aggregated_data(
            glyph_filter=args.glyph,
            font_filter=args.font
        )

        if not data:
            print("❌ No data found matching the filters.")
            return

        print(f"✅ Found {len(data)} aggregated entries")
        print()

        # Display summary stats
        analyzer.display_summary_stats(data)

        # Display table
        analyzer.display_table(data, max_words=args.max_words)

        # Auto-export to CSV (unless disabled)
        if not args.no_csv:
            if args.export_csv:
                # User provided custom path
                csv_path = args.export_csv
            else:
                # Generate default path in PROCESS_FOLDER
                csv_path = analyzer.generate_default_csv_path(
                    glyph_filter=args.glyph,
                    font_filter=args.font
                )

            analyzer.export_csv(data, str(csv_path))

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
