#!/usr/bin/env python3
"""
Update Table of Contents Page Numbers

This script updates the page_number column in the table_of_contents table
by mapping page_label_raw with the corresponding page_label in the page_map table.

Usage:
    python update_toc_page_numbers.py [--book-id BOOK_ID] [--dry-run]

Options:
    --book-id BOOK_ID    Update only specific book (optional, updates all if not specified)
    --dry-run           Show what would be updated without making changes
"""

import sys
import argparse
import logging
from pathlib import Path

# Add the src directory to the path
# sys.path.append('./src/prod_utils')

try:
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Required dependencies not found: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

# Load environment variables
load_dotenv()


class TOCPageNumberUpdater:
    """Updates table_of_contents page_number column using page_map mappings."""

    def __init__(self):
        """Initialize the updater with database connection."""
        self.db = PureBhaktiVaultDB()
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the updater."""
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

    def get_update_candidates(self, book_id: int = None) -> list:
        """
        Get TOC records that can be updated by matching with page_map.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            List of dictionaries with update information
        """
        # Build query with optional book_id filter
        where_clause = "WHERE t.page_label_raw IS NOT NULL AND t.page_label_raw != ''"
        params = []

        if book_id:
            where_clause += " AND t.book_id = %s"
            params.append(book_id)

        query = f"""
            SELECT
                t.toc_id,
                t.book_id,
                t.toc_label,
                t.page_label_raw,
                t.page_number as current_page_number,
                p.page_number as new_page_number
            FROM table_of_contents t
            INNER JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            {where_clause}
            ORDER BY t.book_id, t.toc_id
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

                candidates = [dict(row) for row in results]
                self.logger.info(f"Found {len(candidates)} TOC records that can be updated")
                return candidates

        except DatabaseError as e:
            self.logger.error(f"Error getting update candidates: {e}")
            raise

    def preview_updates(self, book_id: int = None) -> None:
        """
        Preview what would be updated without making changes.

        Args:
            book_id: Optional book ID to filter by
        """
        candidates = self.get_update_candidates(book_id)

        if not candidates:
            print("No TOC records found that can be updated.")
            return

        print(f"\n=== UPDATE PREVIEW ===")
        print(f"Found {len(candidates)} records that would be updated:")
        print()

        # Group by book for better readability
        current_book = None
        for candidate in candidates:
            if candidate['book_id'] != current_book:
                current_book = candidate['book_id']
                print(f"Book ID: {current_book}")
                print("-" * 80)

            print(f"TOC ID: {candidate['toc_id']:4} | "
                  f"Label: {candidate['toc_label'][:40]:40} | "
                  f"Raw: {candidate['page_label_raw']:8} | "
                  f"Current: {candidate['current_page_number']:3} -> "
                  f"New: {candidate['new_page_number']:3}")

        print(f"\n=== SUMMARY ===")
        print(f"Total records to update: {len(candidates)}")

        # Count by update type
        needs_update = [c for c in candidates if c['current_page_number'] != c['new_page_number']]
        already_correct = [c for c in candidates if c['current_page_number'] == c['new_page_number']]

        print(f"Records needing update: {len(needs_update)}")
        print(f"Records already correct: {len(already_correct)}")

    def update_page_numbers(self, book_id: int = None, dry_run: bool = False) -> dict:
        """
        Update page_number column in table_of_contents table.

        Args:
            book_id: Optional book ID to filter by
            dry_run: If True, show what would be updated without making changes

        Returns:
            Dictionary with update statistics
        """
        if dry_run:
            self.preview_updates(book_id)
            return {'dry_run': True}

        candidates = self.get_update_candidates(book_id)

        if not candidates:
            self.logger.info("No TOC records found that can be updated")
            return {'updated': 0, 'skipped': 0, 'errors': 0}

        stats = {'updated': 0, 'skipped': 0, 'errors': 0}

        # Prepare update statement
        update_query = """
            UPDATE table_of_contents
            SET page_number = %s
            WHERE toc_id = %s
        """

        try:
            with self.db.get_cursor() as cursor:
                for candidate in candidates:
                    toc_id = candidate['toc_id']
                    current_page = candidate['current_page_number']
                    new_page = candidate['new_page_number']

                    # Skip if already correct
                    if current_page == new_page:
                        stats['skipped'] += 1
                        self.logger.debug(f"TOC ID {toc_id}: page_number already correct ({current_page})")
                        continue

                    try:
                        cursor.execute(update_query, (new_page, toc_id))
                        stats['updated'] += 1

                        self.logger.info(f"TOC ID {toc_id}: Updated page_number from {current_page} to {new_page}")

                    except Exception as e:
                        stats['errors'] += 1
                        self.logger.error(f"TOC ID {toc_id}: Failed to update - {e}")

                self.logger.info(f"Update completed: {stats['updated']} updated, "
                               f"{stats['skipped']} skipped, {stats['errors']} errors")

        except DatabaseError as e:
            self.logger.error(f"Error during update process: {e}")
            raise

        return stats

    def validate_updates(self, book_id: int = None) -> dict:
        """
        Validate that the updates were successful by checking for remaining mismatches.

        Args:
            book_id: Optional book ID to filter by

        Returns:
            Dictionary with validation results
        """
        # Query to find any remaining mismatches
        where_clause = "WHERE t.page_label_raw IS NOT NULL AND t.page_label_raw != ''"
        params = []

        if book_id:
            where_clause += " AND t.book_id = %s"
            params.append(book_id)

        query = f"""
            SELECT
                t.toc_id,
                t.book_id,
                t.toc_label,
                t.page_label_raw,
                t.page_number as toc_page_number,
                p.page_number as map_page_number
            FROM table_of_contents t
            INNER JOIN page_map p ON (
                t.book_id = p.book_id
                AND TRIM(t.page_label_raw) = TRIM(p.page_label)
            )
            {where_clause}
            AND t.page_number != p.page_number
            ORDER BY t.book_id, t.toc_id
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, params)
                mismatches = cursor.fetchall()

                validation_result = {
                    'validation_passed': len(mismatches) == 0,
                    'remaining_mismatches': len(mismatches),
                    'mismatches': [dict(row) for row in mismatches]
                }

                if validation_result['validation_passed']:
                    self.logger.info("Validation passed: All matching records have correct page numbers")
                else:
                    self.logger.warning(f"Validation failed: {len(mismatches)} mismatches remain")
                    for mismatch in validation_result['mismatches']:
                        self.logger.warning(f"TOC ID {mismatch['toc_id']}: "
                                          f"page_number={mismatch['toc_page_number']} but should be "
                                          f"{mismatch['map_page_number']} (raw='{mismatch['page_label_raw']}')")

                return validation_result

        except DatabaseError as e:
            self.logger.error(f"Error during validation: {e}")
            raise


def main():
    """Main function to handle command line execution."""
    parser = argparse.ArgumentParser(
        description="Update table_of_contents page_number column using page_map mappings"
    )
    parser.add_argument(
        '--book-id',
        type=int,
        help='Update only specific book ID (optional)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only run validation to check current state'
    )

    args = parser.parse_args()

    try:
        updater = TOCPageNumberUpdater()

        # Test database connection
        if not updater.db.test_connection():
            print("Error: Failed to connect to database")
            sys.exit(1)

        if args.validate_only:
            print("Running validation only...")
            validation = updater.validate_updates(args.book_id)
            if not validation['validation_passed']:
                print(f"\nValidation failed: {validation['remaining_mismatches']} mismatches found")
                sys.exit(1)
            else:
                print("Validation passed: All records are correctly mapped")
        else:
            # Run the update
            stats = updater.update_page_numbers(args.book_id, args.dry_run)

            if not args.dry_run:
                print(f"\nUpdate completed:")
                print(f"  Updated: {stats['updated']}")
                print(f"  Skipped: {stats['skipped']}")
                print(f"  Errors: {stats['errors']}")

                # Run validation after update
                print("\nRunning validation...")
                validation = updater.validate_updates(args.book_id)
                if validation['validation_passed']:
                    print("✅ Validation passed: All updates successful")
                else:
                    print(f"❌ Validation failed: {validation['remaining_mismatches']} issues remain")
                    sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()