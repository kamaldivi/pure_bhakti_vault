"""
Update Book Titles Utility

Reads book titles from a CSV file and updates the book table in the database.
- Reads CSV file specified in BOOK_TITLE_FILE environment variable
- Removes leading and trailing spaces from titles
- Updates original_book_title column in the book table for each book_id

Dependencies:
    pip install psycopg2-binary python-dotenv

Usage:
    python update_book_titles.py
"""

import os
import csv
import logging
from dotenv import load_dotenv
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()


def setup_logger() -> logging.Logger:
    """Setup logging for the utility."""
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


def update_book_title(db: PureBhaktiVaultDB, book_id: int, title: str) -> bool:
    """
    Update original_book_title column for a specific book.

    Args:
        db: Database utility instance
        book_id: The book ID to update
        title: The cleaned title text

    Returns:
        bool: True if update successful, False otherwise
    """
    query = "UPDATE book SET original_book_title = %s WHERE book_id = %s"

    try:
        with db.get_cursor() as cursor:
            cursor.execute(query, (title, book_id))
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                return True
            else:
                logging.warning(f"No book found with ID {book_id}")
                return False

    except Exception as e:
        logging.error(f"Error updating book {book_id}: {e}")
        return False


def process_book_titles():
    """
    Main function to process book titles from CSV and update database.
    """
    logger = setup_logger()

    # Get CSV file path from environment
    csv_file = os.getenv('BOOK_TITLE_FILE')

    if not csv_file:
        logger.error("BOOK_TITLE_FILE not found in .env file")
        return

    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return

    logger.info(f"Reading book titles from: {csv_file}")

    # Initialize database connection
    db = PureBhaktiVaultDB()

    # Test database connection
    if not db.test_connection():
        logger.error("Failed to connect to database")
        return

    # Read CSV file
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            # Read all lines
            lines = f.readlines()

            # Skip the first line if it doesn't look like a proper CSV header
            if lines and 'book_id' not in lines[0].lower():
                logger.info(f"Skipping first line (appears to be sheet name): {lines[0].strip()}")
                lines = lines[1:]

            # Parse CSV from remaining lines
            reader = csv.DictReader(lines)

            # Verify CSV has required columns
            # Check for common variations: book_id, Book Id, etc.
            fieldnames_lower = [f.lower() for f in reader.fieldnames]

            book_id_col = None
            title_col = None

            for field in reader.fieldnames:
                field_lower = field.lower()
                if 'book' in field_lower and 'id' in field_lower:
                    book_id_col = field
                if 'book' in field_lower and 'title' in field_lower:
                    title_col = field

            if not book_id_col or not title_col:
                logger.error(f"CSV must have book_id and title columns. Found: {reader.fieldnames}")
                return

            logger.info(f"CSV columns: {reader.fieldnames}")
            logger.info(f"Using columns - ID: '{book_id_col}', Title: '{title_col}'")

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                book_id_str = row.get(book_id_col, '').strip()
                title = row.get(title_col, '').strip()

                # Skip rows without Book Id
                if not book_id_str:
                    logger.debug(f"Row {row_num}: Skipping - no Book Id")
                    skipped_count += 1
                    continue

                # Convert Book Id to integer
                try:
                    book_id = int(book_id_str)
                except ValueError:
                    logger.warning(f"Row {row_num}: Invalid Book Id '{book_id_str}'")
                    error_count += 1
                    continue

                # Clean title (just strip leading/trailing spaces)
                cleaned_title = title.strip()

                if not cleaned_title:
                    logger.warning(f"Row {row_num}: Book ID {book_id} has empty title")
                    skipped_count += 1
                    continue

                # Update database
                logger.info(f"Updating Book ID {book_id}: '{cleaned_title}'")

                if update_book_title(db, book_id, cleaned_title):
                    updated_count += 1
                    logger.info(f"✓ Successfully updated Book ID {book_id}")
                else:
                    error_count += 1
                    logger.error(f"✗ Failed to update Book ID {book_id}")

    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        return

    # Print summary
    logger.info("=" * 60)
    logger.info("Book Title Update Complete")
    logger.info(f"Successfully updated: {updated_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"Errors: {error_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    process_book_titles()
