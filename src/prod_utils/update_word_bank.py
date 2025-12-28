#!/usr/bin/env python3
"""
Update Word Bank Program Fixed Column

Standalone utility to update the program_fixed column in pbb_word_bank table
using the sanskrit_utils transliteration fixer.

This utility:
1. Reads all records from pbb_word_bank table
2. Applies correct_sanskrit_diacritics() from sanskrit_utils to each raw_word
3. Updates the program_fixed column with the fixed version (OVERWRITES existing values)
4. Preserves case (UPPERCASE, Title Case, lowercase)
5. Reports statistics and examples for review

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    python update_word_bank.py                    # Process all words
    python update_word_bank.py --dry-run          # Preview without updating
    python update_word_bank.py --limit 100        # Test on first 100 records
    python update_word_bank.py --batch-size 500   # Custom batch size

Note:
    Uses sanskrit_utils package (v1.0.14) for best accuracy:
    - 98-99% accuracy
    - Global åñ → ṛṣ mapping (fixes 400+ words)
    - 15 priority rules for å → ṛ/ā
    - 10+ patterns for ñ → ṣ/ñ
    - Case preservation
    - All character mappings (à→ṁ, ï→ñ, ˇ→Ṭ, ì→ṅ, åñ→ṛṣ, etc.)
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from dotenv import load_dotenv
import time

# Import database utility
sys.path.insert(0, str(Path(__file__).parent))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from sanskrit_utils import correct_sanskrit_diacritics, apply_global_char_map

# Load environment variables
load_dotenv()


class WordBankUpdater:
    """Updates program_fixed column in pbb_word_bank using sanskrit_utils package."""

    def __init__(self, dry_run: bool = False, batch_size: int = 1000):
        """
        Initialize the updater.

        Args:
            dry_run: If True, preview changes without updating database
            batch_size: Number of records to update per batch (default: 1000)
        """
        self.db = PureBhaktiVaultDB()
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.total_records = 0
        self.changed_records = 0
        self.unchanged_records = 0
        self.error_records = 0
        self.examples = []

    def get_total_count(self) -> int:
        """Get total count of records in pbb_word_bank."""
        try:
            query = "SELECT COUNT(*) as count FROM pbb_word_bank"
            result = self.db.execute_query(query, fetch='one')
            return result['count'] if result else 0
        except DatabaseError as e:
            print(f"❌ Failed to get total count: {e}")
            return 0

    def get_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get records from pbb_word_bank table.

        Args:
            limit: Optional limit on number of records to fetch

        Returns:
            List of record dictionaries with word_id, raw_word, program_fixed
        """
        try:
            query = """
                SELECT word_id, raw_word, program_fixed
                FROM pbb_word_bank
                ORDER BY word_id
            """

            if limit:
                query += f" LIMIT {limit}"

            results = self.db.execute_query(query, fetch='all')
            return results if results else []

        except DatabaseError as e:
            print(f"❌ Failed to fetch records: {e}")
            return []

    def update_record(self, word_id: int, corrected_word: str) -> bool:
        """
        Update a single record's program_fixed column.

        Args:
            word_id: The word ID to update
            corrected_word: The corrected word value

        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            return True

        try:
            query = """
                UPDATE pbb_word_bank
                SET program_fixed = %s
                WHERE word_id = %s
            """

            with self.db.get_cursor() as cursor:
                cursor.execute(query, (corrected_word, word_id))

            return True

        except Exception as e:
            print(f"❌ Failed to update word_id {word_id}: {e}")
            return False

    def update_batch(self, updates: List[tuple]) -> int:
        """
        Update multiple records in a batch.

        Args:
            updates: List of tuples (corrected_word, word_id)

        Returns:
            Number of successfully updated records
        """
        if self.dry_run:
            return len(updates)

        try:
            query = """
                UPDATE pbb_word_bank
                SET program_fixed = %s
                WHERE word_id = %s
            """

            with self.db.get_cursor() as cursor:
                cursor.executemany(query, updates)

            return len(updates)

        except Exception as e:
            print(f"❌ Failed to update batch: {e}")
            return 0

    def process_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process records and update program_fixed column.

        Args:
            records: List of record dictionaries

        Returns:
            Statistics dictionary
        """
        total = len(records)
        print(f"\n{'🔍 DRY RUN - ' if self.dry_run else ''}Processing {total:,} records...")
        print("-" * 80)

        batch_updates = []

        for idx, record in enumerate(records, 1):
            word_id = record['word_id']
            raw_word = record['raw_word']
            old_program_fixed = record.get('program_fixed', '')

            try:
                # Apply sanskrit_utils correction
                # IMPORTANT: Apply Stage 1 (global char map) FIRST, then Stage 3 (diacritic rules)
                # This ensures åñ → ṛṣ is applied before individual å/ñ processing
                stage1_word, stage1_changes = apply_global_char_map(raw_word)
                corrected_word, rules_applied = correct_sanskrit_diacritics(stage1_word)

                # Track statistics
                self.total_records += 1

                if corrected_word != old_program_fixed:
                    self.changed_records += 1

                    # Collect examples (first 20)
                    if len(self.examples) < 20:
                        self.examples.append({
                            'word_id': word_id,
                            'raw_word': raw_word,
                            'old_value': old_program_fixed or '(NULL)',
                            'new_value': corrected_word,
                            'rules': ', '.join(rules_applied) if rules_applied else 'global char map only'
                        })

                    # Add to batch
                    batch_updates.append((corrected_word, word_id))
                else:
                    self.unchanged_records += 1

                # Process batch when it reaches batch_size
                if len(batch_updates) >= self.batch_size:
                    if not self.dry_run:
                        updated = self.update_batch(batch_updates)
                        if updated != len(batch_updates):
                            print(f"⚠️  Warning: Batch update count mismatch")
                    batch_updates = []

                # Progress indicator
                if idx % 5000 == 0 or idx == total:
                    pct = (idx / total) * 100
                    print(f"  Progress: {idx:,}/{total:,} ({pct:.1f}%) - "
                          f"Changed: {self.changed_records:,}, "
                          f"Unchanged: {self.unchanged_records:,}")

            except Exception as e:
                self.error_records += 1
                print(f"  ⚠️  Error processing word_id {word_id} ('{raw_word}'): {e}")
                continue

        # Process remaining batch
        if batch_updates:
            if not self.dry_run:
                updated = self.update_batch(batch_updates)
                if updated != len(batch_updates):
                    print(f"⚠️  Warning: Final batch update count mismatch")

        return {
            'total': self.total_records,
            'changed': self.changed_records,
            'unchanged': self.unchanged_records,
            'errors': self.error_records
        }

    def print_statistics(self, stats: Dict[str, Any]):
        """Print statistics and examples."""
        print("\n" + "=" * 80)
        print("STATISTICS")
        print("=" * 80)
        print(f"Total records processed: {stats['total']:,}")
        print(f"Records changed:         {stats['changed']:,} ({100*stats['changed']/stats['total']:.1f}%)")
        print(f"Records unchanged:       {stats['unchanged']:,} ({100*stats['unchanged']/stats['total']:.1f}%)")

        if stats['errors'] > 0:
            print(f"Errors encountered:      {stats['errors']:,}")

        if self.examples:
            print("\n" + "=" * 80)
            print("SAMPLE CHANGES (First 20)")
            print("=" * 80)

            for i, ex in enumerate(self.examples, 1):
                print(f"\n{i}. Word ID {ex['word_id']}:")
                print(f"   Raw word:     {ex['raw_word']}")
                print(f"   Old value:    {ex['old_value']}")
                print(f"   New value:    {ex['new_value']}")
                print(f"   Rules used:   {ex['rules']}")

        print("\n" + "=" * 80)

    def verify_updates(self):
        """Verify the updates by sampling the database."""
        if self.dry_run:
            return

        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80)

        try:
            # Count records with program_fixed
            query = "SELECT COUNT(*) as count FROM pbb_word_bank WHERE program_fixed IS NOT NULL AND program_fixed != ''"
            result = self.db.execute_query(query, fetch='one')
            with_fixed = result['count'] if result else 0

            # Total count
            total = self.get_total_count()

            print(f"Total records in pbb_word_bank: {total:,}")
            print(f"Records with program_fixed:     {with_fixed:,} ({100*with_fixed/total:.1f}%)")

            # Sample a few updated records
            if self.examples:
                print("\nVerifying sample updates...")
                sample_ids = [ex['word_id'] for ex in self.examples[:5]]

                query = f"""
                    SELECT word_id, raw_word, program_fixed
                    FROM pbb_word_bank
                    WHERE word_id IN ({','.join(map(str, sample_ids))})
                """

                results = self.db.execute_query(query, fetch='all')

                print("\nSample records after update:")
                for rec in results:
                    print(f"  ID {rec['word_id']}: '{rec['raw_word']}' → '{rec['program_fixed']}'")

        except DatabaseError as e:
            print(f"❌ Verification failed: {e}")

    def run(self, limit: Optional[int] = None):
        """
        Main execution method.

        Args:
            limit: Optional limit on number of records to process
        """
        print("=" * 80)
        print("WORD BANK UPDATER - Update program_fixed using sanskrit_utils")
        print("=" * 80)

        if self.dry_run:
            print("\n🔍 DRY RUN MODE - No database changes will be made\n")

        # Test database connection
        if not self.db.test_connection():
            print("❌ Failed to connect to database. Exiting.")
            return

        # Get total count
        total_count = self.get_total_count()
        print(f"\nTotal records in pbb_word_bank: {total_count:,}")

        if limit:
            print(f"Limiting processing to first {limit:,} records")

        # Fetch records
        start_time = time.time()
        print("\n📖 Fetching records from database...")
        records = self.get_records(limit=limit)

        if not records:
            print("❌ No records found to process")
            return

        print(f"✅ Fetched {len(records):,} records in {time.time() - start_time:.2f}s")

        # Process records
        process_start = time.time()
        stats = self.process_records(records)
        process_time = time.time() - process_start

        # Print statistics
        self.print_statistics(stats)

        print(f"\nProcessing time: {process_time:.2f}s")
        print(f"Average time per record: {(process_time/stats['total']*1000):.2f}ms")

        # Verify updates
        if not self.dry_run and stats['changed'] > 0:
            self.verify_updates()

        print("\n" + "=" * 80)
        if self.dry_run:
            print("✅ DRY RUN COMPLETE - Review changes above")
            print("   Run without --dry-run to apply updates")
        else:
            print("✅ UPDATE COMPLETE")
        print("=" * 80)


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Update program_fixed column in pbb_word_bank using sanskrit_utils',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without updating database
  python update_word_bank.py --dry-run

  # Update all records in pbb_word_bank
  python update_word_bank.py

  # Test on first 100 records only
  python update_word_bank.py --dry-run --limit 100

  # Update with custom batch size
  python update_word_bank.py --batch-size 500

  # Update all records (production run)
  python update_word_bank.py

Note:
  This will OVERWRITE existing program_fixed values with new corrections
  from sanskrit_utils (v1.0.14) which has 98-99% accuracy.
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without updating database'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit processing to first N records (for testing)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of records to update per batch (default: 1000)'
    )

    args = parser.parse_args()

    # Confirmation for production run
    if not args.dry_run and not args.limit:
        print("⚠️  WARNING: This will update ALL records in pbb_word_bank.program_fixed")
        print("   Existing values will be OVERWRITTEN with sanskrit_utils corrections.")
        response = input("\nContinue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    # Create and run updater
    updater = WordBankUpdater(
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )

    updater.run(limit=args.limit)


if __name__ == '__main__':
    main()
