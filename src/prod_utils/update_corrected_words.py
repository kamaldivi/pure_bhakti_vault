#!/usr/bin/env python3
"""
Update Corrected Words in Database

Standalone utility to update the corrected_word column in ambiguous_diacritic_words
table using the sanskrit_utils transliteration fixer.

This utility:
1. Reads all records from ambiguous_diacritic_words table
2. Applies correct_sanskrit_diacritics() from sanskrit_utils to each word
3. Updates the corrected_word column with the fixed version
4. Reports statistics and examples for review

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    python update_corrected_words.py                    # Process all words
    python update_corrected_words.py --dry-run          # Preview without updating
    python update_corrected_words.py --limit 100        # Test on first 100 records
    python update_corrected_words.py --diacritic å      # Update only å words
    python update_corrected_words.py --diacritic ñ      # Update only ñ words

Note:
    Now uses sanskrit_utils package (v1.0.9) for better accuracy:
    - 98-99% accuracy (vs ~70% for old char_mapper)
    - 12 priority rules for å → ṛ/ā
    - 10+ patterns for ñ → ṣ/ñ
    - Case preservation
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from dotenv import load_dotenv

# Import database utility
sys.path.insert(0, str(Path(__file__).parent))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from sanskrit_utils import correct_sanskrit_diacritics

# Load environment variables
load_dotenv()


class CorrectedWordUpdater:
    """Updates corrected_word column using sanskrit_utils package."""

    def __init__(self, dry_run: bool = False):
        """
        Initialize the updater.

        Args:
            dry_run: If True, preview changes without updating database
        """
        self.db = PureBhaktiVaultDB()
        self.dry_run = dry_run
        self.total_records = 0
        self.changed_records = 0
        self.unchanged_records = 0
        self.corrections_by_diacritic = defaultdict(int)

    def add_column_if_not_exists(self):
        """Add corrected_word column if it doesn't exist."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if column exists
                    cur.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'ambiguous_diacritic_words'
                        AND column_name = 'corrected_word'
                    """)
                    exists = cur.fetchone() is not None

                    if not exists:
                        print("📝 Adding corrected_word column...")
                        cur.execute("""
                            ALTER TABLE ambiguous_diacritic_words
                            ADD COLUMN corrected_word TEXT
                        """)
                        conn.commit()
                        print("✅ Column added successfully")
                    else:
                        print("✅ Column corrected_word already exists")
        except Exception as e:
            raise DatabaseError(f"Failed to add column: {e}")

    def get_records(
        self,
        diacritic_filter: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get records from ambiguous_diacritic_words table.

        Args:
            diacritic_filter: Optional filter by diacritic ('å' or 'ñ')
            limit: Optional limit on number of records

        Returns:
            List of dicts with id, font_name, diacritic, word, occurrence_count
        """
        where_clause = ""
        params = []

        if diacritic_filter:
            where_clause = "WHERE diacritic = %s"
            params.append(diacritic_filter)

        limit_clause = ""
        if limit:
            limit_clause = f"LIMIT {limit}"

        query = f"""
            SELECT id, font_name, diacritic, word, occurrence_count
            FROM ambiguous_diacritic_words
            {where_clause}
            ORDER BY occurrence_count DESC, id
            {limit_clause}
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    results = cur.fetchall()

                    records = []
                    for row in results:
                        records.append({
                            'id': row[0],
                            'font_name': row[1],
                            'diacritic': row[2],
                            'word': row[3],
                            'occurrence_count': row[4]
                        })

                    return records
        except Exception as e:
            raise DatabaseError(f"Failed to query records: {e}")

    def update_record(self, record_id: int, corrected_word: str):
        """
        Update a single record with corrected word.

        Args:
            record_id: Record ID to update
            corrected_word: Corrected word from sanskrit_utils
        """
        if self.dry_run:
            return

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        UPDATE ambiguous_diacritic_words
                        SET corrected_word = %s
                        WHERE id = %s
                    """
                    cur.execute(query, (corrected_word, record_id))
                    conn.commit()
        except Exception as e:
            raise DatabaseError(f"Failed to update record {record_id}: {e}")

    def process_records(
        self,
        diacritic_filter: Optional[str] = None,
        limit: Optional[int] = None
    ):
        """
        Process all records and apply sanskrit_utils corrections.

        Args:
            diacritic_filter: Optional filter by diacritic
            limit: Optional limit on number of records
        """
        print("🔍 Fetching records from ambiguous_diacritic_words...")
        records = self.get_records(diacritic_filter, limit)
        self.total_records = len(records)

        if not records:
            print("❌ No records found")
            return

        print(f"✅ Found {self.total_records} records to process")
        print()

        if self.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made to database")
            print()

        # Store examples for display
        examples_changed = []
        examples_unchanged = []

        # Process each record
        for i, record in enumerate(records, 1):
            record_id = record['id']
            font_name = record['font_name']
            diacritic = record['diacritic']
            original_word = record['word']
            occurrence_count = record['occurrence_count']

            # Apply sanskrit_utils correction (more accurate than old char_mapper)
            corrected_word, _ = correct_sanskrit_diacritics(original_word)

            # Track changes
            if corrected_word != original_word:
                self.changed_records += 1
                self.corrections_by_diacritic[diacritic] += 1

                # Store examples (up to 10 per category)
                if len(examples_changed) < 10:
                    examples_changed.append({
                        'font': font_name,
                        'diacritic': diacritic,
                        'original': original_word,
                        'corrected': corrected_word,
                        'count': occurrence_count
                    })
            else:
                self.unchanged_records += 1

                # Store examples (up to 10)
                if len(examples_unchanged) < 10:
                    examples_unchanged.append({
                        'font': font_name,
                        'diacritic': diacritic,
                        'word': original_word,
                        'count': occurrence_count
                    })

            # Update database
            if not self.dry_run:
                self.update_record(record_id, corrected_word)

            # Show progress every 100 records
            if i % 100 == 0:
                print(f"  Processing record {i}/{self.total_records}...")

        # Display examples
        self.display_examples(examples_changed, examples_unchanged)

    def display_examples(self, changed: List[Dict], unchanged: List[Dict]):
        """Display example corrections and unchanged words."""
        print()
        print("=" * 80)
        print("📋 EXAMPLE CORRECTIONS (up to 10)")
        print("=" * 80)

        if changed:
            for ex in changed:
                print(f"Font: {ex['font']}")
                print(f"  {ex['original']} → {ex['corrected']} ({ex['diacritic']}, {ex['count']} occurrences)")
        else:
            print("(No changes applied)")

        print()
        print("=" * 80)
        print("📋 EXAMPLE UNCHANGED WORDS (up to 10)")
        print("=" * 80)

        if unchanged:
            for ex in unchanged:
                print(f"Font: {ex['font']}")
                print(f"  {ex['word']} (unchanged, {ex['diacritic']}, {ex['count']} occurrences)")
        else:
            print("(All words were changed)")

        print()

    def display_summary(self):
        """Display processing summary."""
        print("=" * 80)
        print("📊 UPDATE SUMMARY")
        print("=" * 80)
        print(f"Total records processed: {self.total_records}")

        if self.total_records > 0:
            print(f"Words changed by sanskrit_utils: {self.changed_records} ({self.changed_records/self.total_records*100:.1f}%)")
            print(f"Words unchanged: {self.unchanged_records} ({self.unchanged_records/self.total_records*100:.1f}%)")
        print()

        if self.corrections_by_diacritic:
            print("Corrections by diacritic:")
            for diacritic in sorted(self.corrections_by_diacritic.keys()):
                count = self.corrections_by_diacritic[diacritic]
                print(f"  {diacritic}: {count:,} words corrected")
            print()

        if self.dry_run:
            print("⚠️  DRY RUN MODE - No changes were made to the database")
            print("   Run without --dry-run to apply corrections")
        else:
            print("✅ All corrections written to corrected_word column")

        print()
        print("💡 Query to review corrections:")
        print("   SELECT font_name, diacritic, word, corrected_word, occurrence_count")
        print("   FROM ambiguous_diacritic_words")
        print("   WHERE word != corrected_word")
        print("   ORDER BY occurrence_count DESC")
        print("   LIMIT 50;")
        print()

    def run(
        self,
        diacritic_filter: Optional[str] = None,
        limit: Optional[int] = None
    ):
        """
        Main execution method.

        Args:
            diacritic_filter: Optional filter by diacritic
            limit: Optional limit on number of records
        """
        print("=" * 80)
        print("🔄 CORRECTED WORD UPDATER")
        print("=" * 80)
        print()

        # Add column if needed
        if not self.dry_run:
            self.add_column_if_not_exists()
            print()

        # Process all records
        self.process_records(diacritic_filter, limit)

        # Display summary
        self.display_summary()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update corrected_word column using sanskrit_utils",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all words and update database
  python update_corrected_words.py

  # Preview changes without updating
  python update_corrected_words.py --dry-run

  # Test on first 100 records
  python update_corrected_words.py --limit 100 --dry-run

  # Update only å words
  python update_corrected_words.py --diacritic å

  # Update only ñ words with limit
  python update_corrected_words.py --diacritic ñ --limit 50 --dry-run
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating database"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of records to process (for testing)"
    )
    parser.add_argument(
        "--diacritic",
        type=str,
        choices=["å", "ñ"],
        help="Filter by specific diacritic (å or ñ)"
    )

    args = parser.parse_args()

    try:
        updater = CorrectedWordUpdater(dry_run=args.dry_run)
        updater.run(diacritic_filter=args.diacritic, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  Update interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
