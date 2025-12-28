"""
Update Book Summaries Utility

Reads book summaries from a CSV file and updates the book table in the database.
- Reads CSV file specified in BOOK_SUMMARY_FILE environment variable
- Cleans up summary text (leading/trailing spaces, whitespace, line breaks)
- Updates book_summary column in the book table for each book_id

Dependencies:
    pip install psycopg2-binary python-dotenv pandas

Usage:
    python update_book_summaries.py
"""

import os
import re
import csv
import logging
from typing import Optional
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


def clean_summary_text(text: str) -> str:
    """
    Clean up book summary text.

    - Removes leading/trailing whitespace
    - Normalizes internal whitespace
    - Removes redundant line breaks
    - Collapses multiple spaces to single space

    Args:
        text: Raw summary text

    Returns:
        str: Cleaned summary text
    """
    if not text:
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()

    # Replace multiple line breaks with double line break
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Replace tabs with spaces
    text = text.replace('\t', ' ')

    # Collapse multiple spaces to single space (except after newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)

    # Remove spaces at start/end of lines
    text = '\n'.join(line.strip() for line in text.split('\n'))

    # Remove empty lines from start and end
    lines = text.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    text = '\n'.join(lines)

    return text


def update_book_summary(db: PureBhaktiVaultDB, book_id: int, summary: str) -> bool:
    """
    Update book_summary column for a specific book.

    Args:
        db: Database utility instance
        book_id: The book ID to update
        summary: The cleaned summary text

    Returns:
        bool: True if update successful, False otherwise
    """
    query = "UPDATE book SET book_summary = %s WHERE book_id = %s"

    try:
        with db.get_cursor() as cursor:
            cursor.execute(query, (summary, book_id))
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                return True
            else:
                logging.warning(f"No book found with ID {book_id}")
                return False

    except Exception as e:
        logging.error(f"Error updating book {book_id}: {e}")
        return False


def process_book_summaries():
    """
    Main function to process book summaries from CSV and update database.
    """
    logger = setup_logger()

    # Get CSV file path from environment
    csv_file = os.getenv('BOOK_SUMMARY_FILE')

    if not csv_file:
        logger.error("BOOK_SUMMARY_FILE not found in .env file")
        return

    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return

    logger.info(f"Reading book summaries from: {csv_file}")

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
            # (e.g., if it's a sheet name like "PBB_Book_Summaries - Sheet1")
            if lines and 'Book Id' not in lines[0]:
                logger.info(f"Skipping first line (appears to be sheet name): {lines[0].strip()}")
                lines = lines[1:]

            # Parse CSV from remaining lines
            reader = csv.DictReader(lines)

            # Verify CSV has required columns
            if 'Book Id' not in reader.fieldnames or 'Book Summary' not in reader.fieldnames:
                logger.error(f"CSV must have 'Book Id' and 'Book Summary' columns. Found: {reader.fieldnames}")
                return

            logger.info(f"CSV columns: {reader.fieldnames}")

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                book_id_str = row.get('Book Id', '').strip()
                summary = row.get('Book Summary', '').strip()

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

                # Clean summary text
                cleaned_summary = clean_summary_text(summary)

                if not cleaned_summary:
                    logger.warning(f"Row {row_num}: Book ID {book_id} has empty summary")
                    skipped_count += 1
                    continue

                # Update database
                logger.info(f"Updating Book ID {book_id} (summary length: {len(cleaned_summary)} chars)")

                if update_book_summary(db, book_id, cleaned_summary):
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
    logger.info("Book Summary Update Complete")
    logger.info(f"Successfully updated: {updated_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"Errors: {error_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    process_book_summaries()
