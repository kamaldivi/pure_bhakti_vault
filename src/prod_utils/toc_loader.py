"""
Table of Contents (TOC) Loader Utility

Loads TOC entries from CSV files into the table_of_contents database table.
Handles hierarchical parent-child relationships and page number resolution.

Supports two CSV formats:
1. Single-book format: {book_id}_toc.csv (e.g., 5_toc.csv)
   - One CSV file per book
   - book_id extracted from filename

2. Multi-book format: toc_*.csv (e.g., toc_11032025.csv)
   - Multiple books in one CSV file
   - book_id column required in CSV
   - Automatically tracks book boundaries and maintains separate hierarchies

CSV Structure:
    Required columns: book_id, toc_level, toc_label
    Optional columns: page_label, page_number, parent_toc_id

Features:
    - Automatic parent_toc_id assignment based on toc_level hierarchy
    - Page number lookup from page_map table using page_label
    - Sanskrit text cleaning via fix_iast_glyphs()
    - Maintains separate parent stacks for each book in multi-book CSVs
    - Deletes existing TOC entries per book before insertion (prevents duplicates)
    - Leaves page_label empty when not in CSV (API joins with page_map to get labels)

Page Label Handling:
    - If page_label provided: Looks up page_number in page_map table
    - If page_label empty: Uses page_number directly from CSV, stores empty page_label
    - This allows API to join table_of_contents with page_map using page_number

Dependencies:
    pip install psycopg2-binary python-dotenv

Usage:
    python toc_loader.py

Environment:
    Requires TOC_FOLDER in .env file
"""

import os
import csv
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging
from dotenv import load_dotenv
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from sanskrit_utils import fix_iast_glyphs

# Load environment variables (override=True to override system env vars)
load_dotenv(override=True)


class TOCLoader:
    """
    Loads table of contents entries from CSV files into the database.
    Handles hierarchical relationships and page number resolution.
    """

    def __init__(self, toc_folder: str, db: Optional[PureBhaktiVaultDB] = None):
        """
        Initialize the TOC loader.

        Args:
            toc_folder: Path to folder containing TOC CSV files
            db: Optional PureBhaktiVaultDB instance
        """
        self.toc_folder = Path(toc_folder)
        self.db = db or PureBhaktiVaultDB()
        self.logger = self._setup_logger()

        if not self.toc_folder.exists():
            raise FileNotFoundError(f"TOC folder not found: {toc_folder}")

    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the TOC loader."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _delete_toc_entries_for_book(self, book_id: int) -> int:
        """
        Delete all existing TOC entries for a book before inserting new ones.
        This prevents duplicates when re-running the loader.

        Args:
            book_id: The book ID

        Returns:
            int: Number of rows deleted
        """
        query = """
            DELETE FROM table_of_contents
            WHERE book_id = %s
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    self.logger.info(
                        f"  Deleted {deleted_count} existing TOC entries for book_id={book_id}"
                    )
                return deleted_count

        except Exception as e:
            self.logger.error(
                f"Error deleting TOC entries for book_id={book_id}: {e}"
            )
            return 0

    def _get_page_number(self, book_id: int, page_label: str) -> Optional[int]:
        """
        Get page_number from page_map table using book_id and page_label.

        Args:
            book_id: The book ID
            page_label: The page label to search for

        Returns:
            int: page_number if found, None otherwise
        """
        query = """
            SELECT page_number
            FROM page_map
            WHERE book_id = %s AND page_label = %s
            LIMIT 1
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id, page_label))
                result = cursor.fetchone()
                if result:
                    return result['page_number']
                else:
                    self.logger.warning(
                        f"Page number not found for book_id={book_id}, "
                        f"page_label='{page_label}'"
                    )
                    return None

        except Exception as e:
            self.logger.error(
                f"Error getting page number for book_id={book_id}, "
                f"page_label='{page_label}': {e}"
            )
            return None

    def _insert_toc_entry(
        self,
        book_id: int,
        toc_level: int,
        toc_label: str,
        page_label: str,
        page_number: Optional[int],
        parent_toc_id: Optional[int]
    ) -> Optional[int]:
        """
        Insert a TOC entry into the database.

        Args:
            book_id: The book ID
            toc_level: The TOC hierarchy level
            toc_label: The TOC label text (already cleaned)
            page_label: The page label
            page_number: The page number (can be None if not found)
            parent_toc_id: The parent TOC ID (None for top-level)

        Returns:
            int: The inserted toc_id, or None if failed
        """
        query = """
            INSERT INTO table_of_contents
                (book_id, toc_level, toc_label, page_label, page_number, parent_toc_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING toc_id
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(
                    query,
                    (book_id, toc_level, toc_label, page_label, page_number, parent_toc_id)
                )
                result = cursor.fetchone()
                if result:
                    return result['toc_id']
                return None

        except Exception as e:
            self.logger.error(f"Error inserting TOC entry: {e}")
            self.logger.error(
                f"  Data: book_id={book_id}, level={toc_level}, "
                f"label='{toc_label}', page_label='{page_label}'"
            )
            raise DatabaseError(f"Failed to insert TOC entry: {e}")

    def _process_csv_file(self, csv_path: Path) -> Dict[str, int]:
        """
        Process a single TOC CSV file.
        Supports both single-book format (book_id from filename) and
        multi-book format (book_id from CSV column).

        Args:
            csv_path: Path to the CSV file

        Returns:
            dict: Statistics with counts of inserted entries
        """
        stats = {'inserted': 0, 'errors': 0, 'books_processed': set()}

        # Try to extract book_id from filename (e.g., "5_toc.csv" -> 5)
        # If not possible, assume multi-book CSV format
        filename_book_id = None
        try:
            filename_book_id = int(csv_path.stem.split('_')[0])
        except (ValueError, IndexError):
            # Not a single-book CSV, will read book_id from each row
            pass

        if filename_book_id:
            self.logger.info(f"\nProcessing: {csv_path.name} (book_id={filename_book_id})")
        else:
            self.logger.info(f"\nProcessing: {csv_path.name} (multi-book format)")

        # Track parent TOC IDs by level for hierarchical insertion
        # Format: parent_stack[book_id][level] = toc_id
        parent_stack: Dict[int, Dict[int, int]] = {}

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                # Validate required columns
                required_cols = ['book_id', 'toc_level', 'toc_label']
                if not all(col in reader.fieldnames for col in required_cols):
                    self.logger.error(
                        f"Missing required columns. Found: {reader.fieldnames}, "
                        f"Required: {required_cols}"
                    )
                    stats['errors'] = 1
                    return stats

                # Track the last book_id to detect book changes
                current_book_id = None

                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        # Read book_id from CSV
                        if not row['book_id'] or not row['book_id'].strip():
                            self.logger.warning(f"Row {row_num}: Missing book_id, skipping")
                            stats['errors'] += 1
                            continue

                        csv_book_id = int(row['book_id'])

                        # If filename has book_id and it doesn't match, warn
                        if filename_book_id and csv_book_id != filename_book_id:
                            self.logger.warning(
                                f"Row {row_num}: book_id mismatch "
                                f"(CSV={csv_book_id}, filename={filename_book_id})"
                            )

                        # Detect book change and reset parent stack for new book
                        if current_book_id is None or csv_book_id != current_book_id:
                            if current_book_id is not None:
                                self.logger.info(
                                    f"  Book {current_book_id} complete: "
                                    f"{len([b for b in stats['books_processed'] if b == current_book_id])} entries"
                                )
                            current_book_id = csv_book_id
                            stats['books_processed'].add(csv_book_id)
                            self.logger.info(f"  Processing book_id={csv_book_id}...")

                            # Delete existing TOC entries for this book to prevent duplicates
                            self._delete_toc_entries_for_book(csv_book_id)

                            # Initialize parent stack for this book if needed
                            if csv_book_id not in parent_stack:
                                parent_stack[csv_book_id] = {}

                        # Read and validate other fields
                        toc_level = int(row['toc_level'])
                        toc_label = row['toc_label'].strip()

                        # Clean TOC label using Sanskrit utils
                        cleaned_label = fix_iast_glyphs(toc_label, book_id=csv_book_id)

                        # Handle page_label and page_number
                        # Priority: 1) page_label lookup in page_map, 2) direct page_number from CSV
                        page_label = row.get('page_label', '').strip()
                        page_number = None

                        if page_label:
                            # Use page_label to lookup page_number in page_map
                            page_number = self._get_page_number(csv_book_id, page_label)
                        elif 'page_number' in row and row['page_number'].strip():
                            # If no page_label, use page_number directly from CSV
                            try:
                                page_number = int(row['page_number'].strip())
                                # Keep page_label empty - API will join with page_map to get it
                                page_label = ''
                            except (ValueError, TypeError):
                                self.logger.warning(
                                    f"Row {row_num}: Invalid page_number value: {row['page_number']}"
                                )

                        # Skip entry if we don't have a valid page_number
                        if page_number is None:
                            self.logger.warning(
                                f"Row {row_num}: No valid page_number found for book {csv_book_id}, "
                                f"label '{toc_label[:30]}...', skipping"
                            )
                            stats['errors'] += 1
                            continue

                        # Determine parent_toc_id based on hierarchy within this book
                        parent_toc_id = None
                        if toc_level > 1:
                            # Find the immediate parent (last inserted at level - 1 for this book)
                            parent_toc_id = parent_stack[csv_book_id].get(toc_level - 1)
                            if parent_toc_id is None:
                                self.logger.warning(
                                    f"Row {row_num}: No parent found for book {csv_book_id}, "
                                    f"level {toc_level}, treating as top-level"
                                )

                        # Insert the TOC entry
                        toc_id = self._insert_toc_entry(
                            book_id=csv_book_id,
                            toc_level=toc_level,
                            toc_label=cleaned_label,
                            page_label=page_label,
                            page_number=page_number,
                            parent_toc_id=parent_toc_id
                        )

                        if toc_id:
                            # Update parent stack for this book
                            parent_stack[csv_book_id][toc_level] = toc_id

                            # Clear deeper levels from stack (new sibling invalidates children)
                            levels_to_clear = [
                                lvl for lvl in parent_stack[csv_book_id] if lvl > toc_level
                            ]
                            for lvl in levels_to_clear:
                                del parent_stack[csv_book_id][lvl]

                            stats['inserted'] += 1

                            if stats['inserted'] % 10 == 0:
                                self.logger.info(f"  Inserted {stats['inserted']} entries...")

                    except Exception as e:
                        self.logger.error(f"Row {row_num}: Error processing row: {e}")
                        self.logger.error(f"  Row data: {row}")
                        stats['errors'] += 1

                # Log completion of last book
                if current_book_id is not None:
                    self.logger.info(f"  Book {current_book_id} complete")

        except Exception as e:
            self.logger.error(f"Error reading CSV file {csv_path.name}: {e}")
            stats['errors'] += 1

        return stats

    def process_all_csv_files(self) -> Dict[str, Any]:
        """
        Process all *_toc.csv or toc_*.csv files in the TOC_FOLDER.

        Returns:
            dict: Overall statistics
        """
        # Find all TOC CSV files (supports both naming patterns)
        csv_files = sorted(
            list(self.toc_folder.glob("*_toc.csv")) +
            list(self.toc_folder.glob("toc_*.csv"))
        )

        # Remove duplicates if any
        csv_files = sorted(set(csv_files))

        if not csv_files:
            self.logger.warning(f"No TOC CSV files found in {self.toc_folder}")
            return {}

        self.logger.info(f"Found {len(csv_files)} TOC CSV file(s) to process")
        self.logger.info("=" * 70)

        # Overall statistics
        total_stats = {
            'files_processed': 0,
            'total_inserted': 0,
            'total_errors': 0,
            'books_processed': set()
        }

        # Process each CSV file
        for csv_path in csv_files:
            try:
                stats = self._process_csv_file(csv_path)
                total_stats['files_processed'] += 1
                total_stats['total_inserted'] += stats['inserted']
                total_stats['total_errors'] += stats['errors']
                total_stats['books_processed'].update(stats.get('books_processed', set()))

                books_info = ""
                if 'books_processed' in stats and stats['books_processed']:
                    books_list = sorted(stats['books_processed'])
                    books_info = f" (books: {', '.join(map(str, books_list))})"

                self.logger.info(
                    f"✓ {csv_path.name}: {stats['inserted']} inserted, "
                    f"{stats['errors']} errors{books_info}"
                )

            except Exception as e:
                self.logger.error(f"Error processing {csv_path.name}: {e}")
                total_stats['total_errors'] += 1

        # Print summary
        self.logger.info("\n" + "=" * 70)
        self.logger.info("SUMMARY:")
        self.logger.info(f"  CSV files processed: {total_stats['files_processed']}")
        self.logger.info(f"  Books processed: {len(total_stats['books_processed'])} "
                        f"({', '.join(map(str, sorted(total_stats['books_processed'])))})")
        self.logger.info(f"  TOC entries inserted: {total_stats['total_inserted']}")
        self.logger.info(f"  Errors: {total_stats['total_errors']}")
        self.logger.info("=" * 70)

        return total_stats


def main():
    """Main function to run the TOC loader."""

    # Get TOC folder from environment
    toc_folder = os.getenv("TOC_FOLDER")
    if not toc_folder:
        raise RuntimeError("TOC_FOLDER not set in .env file")

    # Initialize loader
    loader = TOCLoader(toc_folder=toc_folder)

    # Test database connection
    if not loader.db.test_connection():
        print("❌ Failed to connect to database. Check your .env file.")
        return

    # Process all CSV files
    loader.process_all_csv_files()


if __name__ == "__main__":
    main()
