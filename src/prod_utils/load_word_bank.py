#!/usr/bin/env python3
"""
Word Bank Loader Utility

Consolidates CSV files from input and fixed folders into a single database table.
- Input folder: Contains CSVs with raw_word and pgm_fix columns
- Fixed folder: Contains CSVs with raw_word and fixed_word (AI-corrected) columns
- Output: pbb_word_bank table with raw_word, program_fixed, ai_fixed structure

Usage:
    python load_word_bank.py [--dry-run] [--clear]

Options:
    --dry-run: Preview the data without inserting into database
    --clear: Drop and recreate the table before loading
"""

import os
import csv
import re
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict, Tuple
import sys

# Load environment variables
load_dotenv()

class WordBankLoader:
    """Loads word bank data from CSV files into PostgreSQL database."""

    def __init__(self, dry_run: bool = False, clear_table: bool = False):
        self.dry_run = dry_run
        self.clear_table = clear_table
        self.process_folder = os.getenv('PROCESS_FOLDER')
        self.input_folder = os.path.join(self.process_folder, 'input')
        self.fixed_folder = os.path.join(self.process_folder, 'fixed')

        # Database connection
        self.conn = None
        self.cursor = None

        # Statistics
        self.total_rows = 0
        self.skipped_rows = 0
        self.inserted_rows = 0

    def connect_db(self):
        """Connect to PostgreSQL database."""
        if self.dry_run:
            print("🔍 DRY RUN MODE - No database changes will be made\n")
            return

        try:
            self.conn = psycopg2.connect(
                host=os.getenv('DB_HOST'),
                port=os.getenv('DB_PORT'),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD')
            )
            self.cursor = self.conn.cursor()
            print("✅ Connected to database\n")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            sys.exit(1)

    def create_table(self):
        """Create pbb_word_bank table if it doesn't exist."""
        if self.dry_run:
            print("📋 Would create table: pbb_word_bank")
            print("   Columns: word_id (PK), raw_word, program_fixed, ai_fixed\n")
            return

        if self.clear_table:
            print("🗑️  Dropping existing table if exists...")
            self.cursor.execute("DROP TABLE IF EXISTS pbb_word_bank CASCADE")
            self.conn.commit()
            print("✅ Table dropped\n")

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS pbb_word_bank (
            word_id SERIAL PRIMARY KEY,
            raw_word TEXT NOT NULL,
            program_fixed TEXT,
            ai_fixed TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pbb_word_bank_raw_word
        ON pbb_word_bank(raw_word);
        """

        try:
            self.cursor.execute(create_table_sql)
            self.conn.commit()
            print("✅ Table pbb_word_bank created/verified\n")
        except Exception as e:
            print(f"❌ Failed to create table: {e}")
            sys.exit(1)

    def get_csv_pairs(self) -> List[Tuple[str, str, str]]:
        """
        Find matching CSV pairs from input and fixed folders.
        Returns list of tuples: (prefix, input_path, fixed_path)
        """
        input_files = {}
        fixed_files = {}

        # Scan input folder
        for filename in os.listdir(self.input_folder):
            if filename.endswith('.csv'):
                match = re.match(r'^(\d+)', filename)
                if match:
                    prefix = match.group(1)
                    input_files[prefix] = os.path.join(self.input_folder, filename)

        # Scan fixed folder
        for filename in os.listdir(self.fixed_folder):
            if filename.endswith('.csv'):
                match = re.match(r'^(\d+)', filename)
                if match:
                    prefix = match.group(1)
                    fixed_files[prefix] = os.path.join(self.fixed_folder, filename)

        # Match pairs
        pairs = []
        for prefix in sorted(input_files.keys()):
            if prefix in fixed_files:
                pairs.append((prefix, input_files[prefix], fixed_files[prefix]))
            else:
                print(f"⚠️  Warning: No matching fixed file for prefix {prefix}")

        return pairs

    def read_csv_to_dict(self, filepath: str, value_column: str) -> Dict[str, str]:
        """
        Read CSV file and return dictionary mapping raw_word to value_column.
        """
        data = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_word = row.get('raw_word', '').strip()
                    value = row.get(value_column, '').strip()
                    if raw_word:
                        data[raw_word] = value
        except Exception as e:
            print(f"❌ Error reading {filepath}: {e}")

        return data

    def merge_csv_pairs(self, pairs: List[Tuple[str, str, str]]) -> List[Dict]:
        """
        Merge matched CSV pairs into consolidated data.
        Returns list of dictionaries with raw_word, program_fixed, ai_fixed.
        """
        print("📂 Reading and merging CSV files...\n")

        all_words = {}  # Key: raw_word, Value: {program_fixed, ai_fixed}

        for prefix, input_path, fixed_path in pairs:
            print(f"   Processing prefix {prefix}...")

            # Read input CSV (pgm_fix)
            input_data = self.read_csv_to_dict(input_path, 'pgm_fix')

            # Read fixed CSV (fixed_word = ai_fixed)
            fixed_data = self.read_csv_to_dict(fixed_path, 'fixed_word')

            # Merge data
            all_raw_words = set(input_data.keys()) | set(fixed_data.keys())

            for raw_word in all_raw_words:
                if raw_word not in all_words:
                    all_words[raw_word] = {
                        'raw_word': raw_word,
                        'program_fixed': input_data.get(raw_word, None),
                        'ai_fixed': fixed_data.get(raw_word, None)
                    }

        print(f"\n✅ Total unique raw_words found: {len(all_words)}\n")
        return list(all_words.values())

    def insert_data(self, data: List[Dict]):
        """Insert consolidated data into pbb_word_bank table."""
        if self.dry_run:
            print("📊 DRY RUN - Sample of data to be inserted:\n")
            for i, row in enumerate(data[:10]):
                print(f"   Row {i+1}:")
                print(f"      raw_word: {row['raw_word']}")
                print(f"      program_fixed: {row['program_fixed']}")
                print(f"      ai_fixed: {row['ai_fixed']}")

            if len(data) > 10:
                print(f"\n   ... and {len(data) - 10} more rows")

            print(f"\n📈 Total rows to insert: {len(data)}")
            return

        print("💾 Inserting data into pbb_word_bank table...")

        insert_sql = """
        INSERT INTO pbb_word_bank (raw_word, program_fixed, ai_fixed)
        VALUES (%s, %s, %s)
        """

        batch_size = 1000
        total = len(data)

        try:
            for i in range(0, total, batch_size):
                batch = data[i:i + batch_size]
                values = [
                    (row['raw_word'], row['program_fixed'], row['ai_fixed'])
                    for row in batch
                ]

                self.cursor.executemany(insert_sql, values)
                self.conn.commit()

                progress = min(i + batch_size, total)
                print(f"   Inserted {progress}/{total} rows...")

            print(f"\n✅ Successfully inserted {total} rows\n")
            self.inserted_rows = total

        except Exception as e:
            print(f"❌ Error inserting data: {e}")
            self.conn.rollback()
            sys.exit(1)

    def verify_data(self):
        """Verify inserted data with summary statistics."""
        if self.dry_run:
            return

        print("🔍 Verifying inserted data...\n")

        # Total count
        self.cursor.execute("SELECT COUNT(*) FROM pbb_word_bank")
        total_count = self.cursor.fetchone()[0]

        # Count with program_fixed
        self.cursor.execute("SELECT COUNT(*) FROM pbb_word_bank WHERE program_fixed IS NOT NULL")
        program_fixed_count = self.cursor.fetchone()[0]

        # Count with ai_fixed
        self.cursor.execute("SELECT COUNT(*) FROM pbb_word_bank WHERE ai_fixed IS NOT NULL")
        ai_fixed_count = self.cursor.fetchone()[0]

        # Count with both
        self.cursor.execute("""
            SELECT COUNT(*) FROM pbb_word_bank
            WHERE program_fixed IS NOT NULL AND ai_fixed IS NOT NULL
        """)
        both_count = self.cursor.fetchone()[0]

        # Sample rows
        self.cursor.execute("SELECT * FROM pbb_word_bank LIMIT 5")
        sample_rows = self.cursor.fetchall()

        print("📊 Database Summary:")
        print(f"   Total rows: {total_count}")
        print(f"   Rows with program_fixed: {program_fixed_count} ({100*program_fixed_count/total_count:.1f}%)")
        print(f"   Rows with ai_fixed: {ai_fixed_count} ({100*ai_fixed_count/total_count:.1f}%)")
        print(f"   Rows with both fixes: {both_count} ({100*both_count/total_count:.1f}%)")
        print("\n📝 Sample rows:")
        for row in sample_rows:
            print(f"   ID {row[0]}: {row[1][:30]}... -> pgm: {row[2][:30] if row[2] else 'NULL'}... | ai: {row[3][:30] if row[3] else 'NULL'}...")
        print()

    def run(self):
        """Main execution flow."""
        print("=" * 60)
        print("Word Bank Loader Utility")
        print("=" * 60)
        print()

        # Step 1: Connect to database
        self.connect_db()

        # Step 2: Create table
        self.create_table()

        # Step 3: Find CSV pairs
        print("🔍 Scanning for CSV files...\n")
        pairs = self.get_csv_pairs()

        if not pairs:
            print("❌ No matching CSV pairs found!")
            sys.exit(1)

        print(f"✅ Found {len(pairs)} matching CSV pairs:\n")
        for prefix, input_path, fixed_path in pairs:
            print(f"   {prefix}: {os.path.basename(input_path)} + {os.path.basename(fixed_path)}")
        print()

        # Step 4: Merge CSV data
        consolidated_data = self.merge_csv_pairs(pairs)

        # Step 5: Insert data
        self.insert_data(consolidated_data)

        # Step 6: Verify
        if not self.dry_run:
            self.verify_data()

        print("=" * 60)
        print("✅ Word Bank Load Complete!")
        print("=" * 60)

        # Cleanup
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


def main():
    """Main entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Load word bank CSVs into pbb_word_bank table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview without making changes
  python load_word_bank.py --dry-run

  # Load data into existing table
  python load_word_bank.py

  # Clear table and reload all data
  python load_word_bank.py --clear
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview operations without modifying database'
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Drop and recreate table before loading'
    )

    args = parser.parse_args()

    # Create and run loader
    loader = WordBankLoader(
        dry_run=args.dry_run,
        clear_table=args.clear
    )

    loader.run()


if __name__ == '__main__':
    main()
