#!/usr/bin/env python3
"""
Correct Dangerous Glyph Words

Adds a corrected_sample_words column to dangerous_glyph_words table and
populates it by applying IAST replacement mappings to the sample_words.

This utility:
1. Adds corrected_sample_words JSONB column if it doesn't exist
2. Reads all records from dangerous_glyph_words table
3. Applies DANGEROUS_GLYPH_TO_IAST mapping to each word in sample_words
4. Updates corrected_sample_words with the corrected words

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    python correct_dangerous_glyph_words.py
    python correct_dangerous_glyph_words.py --dry-run  # Preview changes without updating
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any
import argparse
from dotenv import load_dotenv

# Import database utility
sys.path.insert(0, str(Path(__file__).parent))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()

# =============================================================================
# DANGEROUS GLYPH TO IAST REPLACEMENT MAPPING
# =============================================================================

DANGEROUS_GLYPH_TO_IAST = {
    "ä": "ā", "Ä": "Ā",
    "å": "ṛ", "Å": "Ṛ",
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


class DangerousGlyphCorrector:
    """
    Corrects dangerous glyphs in sample words from dangerous_glyph_words table.
    """

    def __init__(self, dry_run: bool = False):
        """
        Initialize the corrector.

        Args:
            dry_run: If True, preview changes without updating database
        """
        self.db = PureBhaktiVaultDB()
        self.dry_run = dry_run
        self.total_records = 0
        self.corrected_records = 0
        self.skipped_records = 0

    def correct_word(self, word: str) -> str:
        """
        Apply DANGEROUS_GLYPH_TO_IAST mapping to a single word.

        Args:
            word: Word containing dangerous glyphs

        Returns:
            Corrected word with IAST characters
        """
        corrected = word
        for dangerous_glyph, iast_char in DANGEROUS_GLYPH_TO_IAST.items():
            corrected = corrected.replace(dangerous_glyph, iast_char)
        return corrected

    def correct_sample_words(self, sample_words: List[str]) -> List[str]:
        """
        Apply corrections to a list of sample words.

        Args:
            sample_words: List of words containing dangerous glyphs

        Returns:
            List of corrected words with IAST characters
        """
        return [self.correct_word(word) for word in sample_words]

    def add_column_if_not_exists(self):
        """Add corrected_sample_words column if it doesn't exist."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if column exists
                    cur.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'dangerous_glyph_words'
                        AND column_name = 'corrected_sample_words'
                    """)
                    exists = cur.fetchone() is not None

                    if not exists:
                        print("📝 Adding corrected_sample_words column...")
                        cur.execute("""
                            ALTER TABLE dangerous_glyph_words
                            ADD COLUMN corrected_sample_words JSONB
                        """)
                        conn.commit()
                        print("✅ Column added successfully")
                    else:
                        print("✅ Column corrected_sample_words already exists")
        except Exception as e:
            raise DatabaseError(f"Failed to add column: {e}")

    def get_all_records(self) -> List[Dict[str, Any]]:
        """
        Get all records from dangerous_glyph_words table.

        Returns:
            List of dicts with id, sample_words
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT id, sample_words
                        FROM dangerous_glyph_words
                        ORDER BY id
                    """
                    cur.execute(query)
                    results = cur.fetchall()

                    records = []
                    for row in results:
                        record_id, sample_words_json = row

                        # Parse JSON
                        if isinstance(sample_words_json, str):
                            sample_words = json.loads(sample_words_json)
                        else:
                            sample_words = sample_words_json

                        records.append({
                            'id': record_id,
                            'sample_words': sample_words
                        })

                    return records
        except Exception as e:
            raise DatabaseError(f"Failed to query records: {e}")

    def update_record(self, record_id: int, corrected_words: List[str]):
        """
        Update a single record with corrected sample words.

        Args:
            record_id: Record ID to update
            corrected_words: List of corrected words
        """
        if self.dry_run:
            return

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    corrected_json = json.dumps(corrected_words)
                    query = """
                        UPDATE dangerous_glyph_words
                        SET corrected_sample_words = %s::jsonb
                        WHERE id = %s
                    """
                    cur.execute(query, (corrected_json, record_id))
                    conn.commit()
        except Exception as e:
            raise DatabaseError(f"Failed to update record {record_id}: {e}")

    def process_records(self):
        """Process all records and update with corrected words."""
        print("🔍 Fetching all records from dangerous_glyph_words...")
        records = self.get_all_records()
        self.total_records = len(records)

        if not records:
            print("❌ No records found in dangerous_glyph_words table")
            return

        print(f"✅ Found {self.total_records} records to process")
        print()

        if self.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made to database")
            print()

        # Process each record
        for i, record in enumerate(records, 1):
            record_id = record['id']
            sample_words = record['sample_words']

            if not sample_words:
                self.skipped_records += 1
                continue

            # Apply corrections
            corrected_words = self.correct_sample_words(sample_words)

            # Show progress every 100 records
            if i % 100 == 0:
                print(f"  Processing record {i}/{self.total_records}...")

            # Preview first 5 records in dry run mode
            if self.dry_run and i <= 5:
                print(f"Record {record_id}:")
                print(f"  Original (first 3): {sample_words[:3]}")
                print(f"  Corrected (first 3): {corrected_words[:3]}")
                print()

            # Update database
            if not self.dry_run:
                self.update_record(record_id, corrected_words)

            self.corrected_records += 1

    def display_summary(self):
        """Display processing summary."""
        print()
        print("=" * 80)
        print("📊 CORRECTION SUMMARY")
        print("=" * 80)
        print(f"Total records: {self.total_records}")
        print(f"Corrected: {self.corrected_records}")
        print(f"Skipped (empty): {self.skipped_records}")
        print()

        if self.dry_run:
            print("⚠️  DRY RUN MODE - No changes were made to the database")
            print("   Run without --dry-run to apply corrections")
        else:
            print("✅ All records updated successfully!")

        print()
        print("💡 Query examples:")
        print("   -- View original vs corrected:")
        print("   SELECT id, sample_words, corrected_sample_words")
        print("   FROM dangerous_glyph_words LIMIT 5;")
        print()
        print("   -- Find records with specific corrections:")
        print("   SELECT id, sample_words, corrected_sample_words")
        print("   FROM dangerous_glyph_words")
        print("   WHERE sample_words::text LIKE '%ä%';")
        print()

    def run(self):
        """Main execution method."""
        print("=" * 80)
        print("📚 DANGEROUS GLYPH WORD CORRECTOR")
        print("=" * 80)
        print()

        # Add column if needed
        if not self.dry_run:
            self.add_column_if_not_exists()
            print()

        # Process all records
        self.process_records()

        # Display summary
        self.display_summary()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Correct dangerous glyphs in sample words using IAST mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without updating database
  python correct_dangerous_glyph_words.py --dry-run

  # Apply corrections to all records
  python correct_dangerous_glyph_words.py
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating database"
    )

    args = parser.parse_args()

    try:
        corrector = DangerousGlyphCorrector(dry_run=args.dry_run)
        corrector.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Correction interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
