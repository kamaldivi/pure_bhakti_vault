#!/usr/bin/env python3
"""
Populate Missing TOC Page Labels

This script populates empty page_label_raw values in the table_of_contents table
by using the lowest toc_id child's page_label_raw value. Generates error reports
for records that cannot be resolved.

Usage:
    python populate_toc_page_labels.py [--dry-run] [--book-id BOOK_ID]

Options:
    --dry-run           Show what would be updated without making changes
    --book-id BOOK_ID   Process only specific book (optional, processes all if not specified)
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Add the src directory to the path
sys.path.append('./src/prod_utils')

try:
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Required dependencies not found: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

# Load environment variables
load_dotenv()


class TOCPageLabelPopulator:
    """Populates missing page_label_raw values using child TOC hierarchy."""

    def __init__(self):
        """Initialize the populator with database connection."""
        self.db = PureBhaktiVaultDB()
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the populator."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def get_empty_page_label_records(self, book_id: Optional[int] = None) -> List[Dict]:
        """
        Get TOC records with empty page_label_raw values.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            List of dictionaries with TOC record information
        """
        where_clause = "WHERE (page_label_raw IS NULL OR TRIM(page_label_raw) = '')"
        params = []

        if book_id:
            where_clause += " AND book_id = %s"
            params.append(book_id)

        query = f"""
            SELECT
                toc_id,
                book_id,
                toc_label,
                toc_level,
                parent_toc_id,
                page_label_raw
            FROM table_of_contents
            {where_clause}
            ORDER BY book_id, toc_id
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

                empty_records = [dict(row) for row in results]
                self.logger.info(f"Found {len(empty_records)} records with empty page_label_raw")
                return empty_records

        except DatabaseError as e:
            self.logger.error(f"Error getting empty page label records: {e}")
            raise

    def get_child_with_lowest_toc_id(self, parent_toc_id: int, book_id: int) -> Optional[Dict]:
        """
        Get the child record with the lowest toc_id for a given parent.

        Args:
            parent_toc_id: Parent TOC ID
            book_id: Book ID

        Returns:
            Dictionary with child record info, or None if no children found
        """
        query = """
            SELECT
                toc_id,
                book_id,
                toc_label,
                toc_level,
                parent_toc_id,
                page_label_raw
            FROM table_of_contents
            WHERE parent_toc_id = %s
            AND book_id = %s
            AND page_label_raw IS NOT NULL
            AND TRIM(page_label_raw) != ''
            ORDER BY toc_id ASC
            LIMIT 1
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (parent_toc_id, book_id))
                result = cursor.fetchone()

                if result:
                    return dict(result)
                else:
                    # Also check if there are any children at all (even with empty labels)
                    count_query = """
                        SELECT COUNT(*) as child_count
                        FROM table_of_contents
                        WHERE parent_toc_id = %s AND book_id = %s
                    """
                    cursor.execute(count_query, (parent_toc_id, book_id))
                    count_result = cursor.fetchone()

                    if count_result and count_result['child_count'] > 0:
                        self.logger.debug(f"Parent {parent_toc_id} has {count_result['child_count']} children, but none have page_label_raw")

                    return None

        except DatabaseError as e:
            self.logger.error(f"Error getting child for parent {parent_toc_id}: {e}")
            return None

    def analyze_resolvable_records(self, book_id: Optional[int] = None) -> Tuple[List[Dict], List[Dict]]:
        """
        Analyze which records can be resolved and which cannot.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Tuple of (resolvable_records, error_records)
        """
        empty_records = self.get_empty_page_label_records(book_id)

        resolvable_records = []
        error_records = []

        for record in empty_records:
            toc_id = record['toc_id']
            book_id_current = record['book_id']

            # Try to find a child with lowest toc_id that has page_label_raw
            child = self.get_child_with_lowest_toc_id(toc_id, book_id_current)

            if child:
                # Record can be resolved
                resolution_info = {
                    **record,
                    'child_toc_id': child['toc_id'],
                    'child_toc_label': child['toc_label'],
                    'child_page_label_raw': child['page_label_raw'],
                    'new_page_label_raw': child['page_label_raw']
                }
                resolvable_records.append(resolution_info)

                self.logger.debug(f"TOC {toc_id} can be resolved using child {child['toc_id']} with label '{child['page_label_raw']}'")
            else:
                # Record cannot be resolved
                error_info = {
                    **record,
                    'error_reason': 'No children with valid page_label_raw found'
                }
                error_records.append(error_info)

                self.logger.debug(f"TOC {toc_id} cannot be resolved - no suitable children")

        self.logger.info(f"Analysis complete: {len(resolvable_records)} resolvable, {len(error_records)} errors")
        return resolvable_records, error_records

    def populate_page_labels(self, book_id: Optional[int] = None, dry_run: bool = False) -> Dict:
        """
        Populate missing page_label_raw values.

        Args:
            book_id: Optional book ID to filter by
            dry_run: If True, show what would be updated without making changes

        Returns:
            Dictionary with operation statistics
        """
        self.logger.info("Starting page label population process...")

        # Analyze which records can be resolved
        resolvable_records, error_records = self.analyze_resolvable_records(book_id)

        if dry_run:
            self.logger.info("=== DRY RUN MODE ===")
            self._preview_updates(resolvable_records, error_records)
            return {
                'dry_run': True,
                'resolvable': len(resolvable_records),
                'errors': len(error_records)
            }

        # Perform actual updates
        stats = {
            'updated': 0,
            'errors': len(error_records),
            'failed_updates': 0
        }

        if not resolvable_records:
            self.logger.info("No records to update")
            return stats

        # Update records
        update_query = """
            UPDATE table_of_contents
            SET page_label_raw = %s
            WHERE toc_id = %s
        """

        try:
            with self.db.get_cursor() as cursor:
                for record in resolvable_records:
                    toc_id = record['toc_id']
                    new_label = record['new_page_label_raw']

                    try:
                        cursor.execute(update_query, (new_label, toc_id))
                        stats['updated'] += 1

                        self.logger.info(f"Updated TOC {toc_id}: page_label_raw = '{new_label}' "
                                       f"(from child {record['child_toc_id']})")

                    except Exception as e:
                        stats['failed_updates'] += 1
                        self.logger.error(f"Failed to update TOC {toc_id}: {e}")

                self.logger.info(f"Population completed: {stats['updated']} updated, "
                               f"{stats['failed_updates']} failed, {stats['errors']} unresolvable")

        except DatabaseError as e:
            self.logger.error(f"Error during update process: {e}")
            raise

        # Generate error report
        if error_records:
            self._generate_error_report(error_records)

        return stats

    def _preview_updates(self, resolvable_records: List[Dict], error_records: List[Dict]):
        """Preview what would be updated in dry-run mode."""
        print(f"\n=== RESOLVABLE RECORDS ({len(resolvable_records)}) ===")
        if resolvable_records:
            print("Records that would be updated:")
            for record in resolvable_records[:10]:  # Show first 10
                print(f"  TOC ID {record['toc_id']} (Book {record['book_id']}): "
                      f"'{record['toc_label'][:50]}...' → "
                      f"page_label_raw = '{record['new_page_label_raw']}' "
                      f"(from child {record['child_toc_id']})")

            if len(resolvable_records) > 10:
                print(f"  ... and {len(resolvable_records) - 10} more")
        else:
            print("  None")

        print(f"\n=== ERROR RECORDS ({len(error_records)}) ===")
        if error_records:
            print("Records that cannot be resolved:")
            for record in error_records[:10]:  # Show first 10
                print(f"  TOC ID {record['toc_id']} (Book {record['book_id']}): "
                      f"'{record['toc_label'][:50]}...' → "
                      f"Error: {record['error_reason']}")

            if len(error_records) > 10:
                print(f"  ... and {len(error_records) - 10} more")
        else:
            print("  None")

    def _generate_error_report(self, error_records: List[Dict]):
        """Generate and save error report for unresolvable records."""
        if not error_records:
            return

        report_file = Path("toc_page_label_errors.txt")

        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("=== TOC Page Label Population Error Report ===\n")
                f.write(f"Generated: {self.logger.handlers[0].formatter.converter(None)}\n")
                f.write(f"Total unresolvable records: {len(error_records)}\n\n")

                # Group by book
                books = {}
                for record in error_records:
                    book_id = record['book_id']
                    if book_id not in books:
                        books[book_id] = []
                    books[book_id].append(record)

                for book_id in sorted(books.keys()):
                    records = books[book_id]
                    f.write(f"Book ID {book_id}: {len(records)} unresolvable records\n")
                    f.write("-" * 60 + "\n")

                    for record in records:
                        f.write(f"TOC ID: {record['toc_id']}\n")
                        f.write(f"Level: {record['toc_level']}\n")
                        f.write(f"Label: {record['toc_label']}\n")
                        f.write(f"Parent: {record['parent_toc_id']}\n")
                        f.write(f"Error: {record['error_reason']}\n")
                        f.write("\n")

                    f.write("\n")

            self.logger.info(f"Error report saved to: {report_file}")

        except Exception as e:
            self.logger.error(f"Failed to generate error report: {e}")

    def get_statistics(self, book_id: Optional[int] = None) -> Dict:
        """Get statistics about page label population status."""
        where_book = ""
        params = []
        if book_id:
            where_book = "WHERE book_id = %s"
            params = [book_id]

        queries = {
            'total_records': f"SELECT COUNT(*) as count FROM table_of_contents {where_book}",
            'empty_labels': f"SELECT COUNT(*) as count FROM table_of_contents {where_book} {'AND' if book_id else 'WHERE'} (page_label_raw IS NULL OR TRIM(page_label_raw) = '')",
            'populated_labels': f"SELECT COUNT(*) as count FROM table_of_contents {where_book} {'AND' if book_id else 'WHERE'} (page_label_raw IS NOT NULL AND TRIM(page_label_raw) != '')"
        }

        stats = {}
        for stat_name, query in queries.items():
            try:
                result = self.db.execute_query(query, params, 'one')
                stats[stat_name] = result['count'] if result else 0
            except Exception as e:
                self.logger.error(f"Error getting {stat_name}: {e}")
                stats[stat_name] = 0

        return stats


def main():
    """Main function to handle command line execution."""
    parser = argparse.ArgumentParser(
        description="Populate missing page_label_raw values using child TOC hierarchy"
    )
    parser.add_argument(
        '--book-id',
        type=int,
        help='Process only specific book ID (optional)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show statistics without making changes'
    )

    args = parser.parse_args()

    try:
        populator = TOCPageLabelPopulator()

        # Test database connection
        if not populator.db.test_connection():
            print("Error: Failed to connect to database")
            sys.exit(1)

        if args.stats_only:
            # Show statistics only
            print("=== Current Statistics ===")
            stats = populator.get_statistics(args.book_id)

            total = stats['total_records']
            empty = stats['empty_labels']
            populated = stats['populated_labels']

            print(f"Total TOC records: {total}")
            print(f"Empty page_label_raw: {empty} ({empty/total*100:.1f}%)")
            print(f"Populated page_label_raw: {populated} ({populated/total*100:.1f}%)")

            if args.book_id:
                print(f"(Statistics for Book ID {args.book_id} only)")

            return

        # Run the population process
        results = populator.populate_page_labels(args.book_id, args.dry_run)

        if not args.dry_run:
            print(f"\n=== Population Results ===")
            print(f"Updated: {results['updated']}")
            print(f"Unresolvable errors: {results['errors']}")
            print(f"Failed updates: {results['failed_updates']}")

            if results['errors'] > 0:
                print(f"\nError report saved to: toc_page_label_errors.txt")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()