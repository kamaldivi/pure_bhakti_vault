#!/usr/bin/env python3
"""
Book Loader - Part 2

Syncs reviewed/enriched data from Google Sheets back to the database.

After content managers review and update data in Google Sheets, this script:
1. Updates book table with enriched metadata
2. Updates page_map table with corrected page labels
3. Inserts table_of_contents entries
4. Inserts glossary entries (if present)
5. Inserts verse_index entries (if present)

Requirements:
    pip install gspread google-auth psycopg2-binary python-dotenv click

Usage:
    # Normal mode
    python book_loader_part2.py

    # Dry-run mode (validation only, no writes)
    python book_loader_part2.py --dry-run

    # Process specific book IDs only
    python book_loader_part2.py --book-ids 121,122,123

    # Verbose logging
    python book_loader_part2.py --verbose
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import logging

import click
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from tqdm import tqdm

# Import our existing utilities
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GoogleSheetsReader:
    """Handles reading data from Google Sheets."""

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]

    def __init__(self, credentials_file: str, sheet_id: str):
        """
        Initialize Google Sheets reader.

        Args:
            credentials_file: Path to service account JSON credentials
            sheet_id: Google Sheet ID to read from
        """
        self.credentials_file = Path(credentials_file)
        self.sheet_id = sheet_id
        self.client = None
        self.spreadsheet = None

        if not self.credentials_file.exists():
            raise FileNotFoundError(f"Credentials file not found: {credentials_file}")

    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        try:
            creds = Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=self.SCOPES
            )
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.sheet_id)
            logger.info("✅ Google Sheets authentication successful")
            return True
        except Exception as e:
            logger.error(f"❌ Google Sheets authentication failed: {e}")
            return False

    def read_sheet_as_dicts(self, sheet_name: str) -> List[Dict[str, Any]]:
        """
        Read a worksheet and return rows as dictionaries.

        Args:
            sheet_name: Name of the worksheet tab

        Returns:
            List of dictionaries (header row as keys)
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            # Get all records as dictionaries (row 1 is headers)
            records = worksheet.get_all_records(head=1, default_blank='')
            logger.info(f"  ✅ Read {len(records)} rows from '{sheet_name}' tab")
            return records
        except Exception as e:
            logger.error(f"  ❌ Failed to read '{sheet_name}': {e}")
            return []


class BookLoaderPart2:
    """
    Orchestrator for Part 2 of the book loading process.
    Syncs reviewed data from Google Sheets to database.
    """

    def __init__(self,
                 google_credentials: str,
                 google_sheet_id: str,
                 book_ids: Optional[List[int]] = None,
                 dry_run: bool = False):
        """
        Initialize Book Loader Part 2.

        Args:
            google_credentials: Path to Google service account JSON
            google_sheet_id: Google Sheet ID with reviewed data
            book_ids: Optional list of book IDs to process (None = all)
            dry_run: If True, validate only without writing
        """
        self.dry_run = dry_run
        self.book_ids_filter = set(book_ids) if book_ids else None
        self.db = PureBhaktiVaultDB()
        self.sheets_reader = GoogleSheetsReader(google_credentials, google_sheet_id)

        # Stats tracking
        self.stats = {
            'books_updated': 0,
            'page_maps_updated': 0,
            'toc_entries_inserted': 0,
            'glossary_entries_inserted': 0,
            'verse_entries_inserted': 0,
            'errors': 0,
            'skipped': 0
        }

    @staticmethod
    def _safe_str(value: Any) -> str:
        """
        Safely convert any value to string and strip whitespace.
        Handles None, empty strings, numbers, etc.

        Args:
            value: Any value from Google Sheets

        Returns:
            Stripped string or empty string
        """
        if value is None or value == '':
            return ''
        return str(value).strip()

    def step1_update_books(self, book_data: List[Dict[str, Any]]) -> bool:
        """
        Step 1: Update book table with enriched metadata from Google Sheets.

        Args:
            book_data: List of book records from Google Sheets

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 1: Updating book metadata")
        logger.info("="*70)

        if not book_data:
            logger.info("No book data to update")
            return True

        # Filter by book_ids if specified
        if self.book_ids_filter:
            book_data = [b for b in book_data if b.get('book_id') in self.book_ids_filter]
            logger.info(f"Filtered to {len(book_data)} books based on --book-ids")

        if not book_data:
            logger.info("No books match the filter criteria")
            return True

        for book in tqdm(book_data, desc="Updating books"):
            try:
                book_id = book.get('book_id')
                if not book_id:
                    logger.warning("  ⚠️  Skipping row without book_id")
                    self.stats['skipped'] += 1
                    continue

                # Skip placeholder titles that weren't updated
                original_title_value = book.get('original_book_title', '')
                original_title = str(original_title_value).strip() if original_title_value else ''
                if original_title.startswith('[TO BE ADDED]'):
                    logger.warning(f"  ⚠️  Skipping book_id={book_id}: Title not updated (still placeholder)")
                    self.stats['skipped'] += 1
                    continue

                if self.dry_run:
                    logger.info(f"  [DRY RUN] Would update book_id={book_id}: {original_title}")
                    self.stats['books_updated'] += 1
                    continue

                # Prepare update data (only non-empty values)
                update_fields = []
                update_values = []

                # Map Google Sheet columns to database columns
                field_mapping = {
                    'book_type': 'book_type',
                    'original_book_title': 'original_book_title',
                    'edition': 'edition',
                    'original_author': 'original_author',
                    'commentary_author': 'commentary_author',
                    'header_height': 'header_height',
                    'footer_height': 'footer_height',
                    'book_summary': 'book_summary'
                }

                for sheet_col, db_col in field_mapping.items():
                    raw_value = book.get(sheet_col)

                    # Convert to string if it's a string field, otherwise keep as is
                    if raw_value is not None and raw_value != '':
                        # For string fields, ensure they're strings and stripped
                        if isinstance(raw_value, str):
                            value = raw_value.strip()
                        else:
                            # For numeric fields (like header_height, footer_height), keep as number
                            value = raw_value
                    else:
                        value = None

                    # Only update if value is present
                    if value not in ('', None):
                        update_fields.append(f"{db_col} = %s")
                        update_values.append(value)

                if not update_fields:
                    logger.info(f"  ⏭️  Skipping book_id={book_id}: No fields to update")
                    self.stats['skipped'] += 1
                    continue

                # Build UPDATE query
                update_query = f"""
                    UPDATE book
                    SET {', '.join(update_fields)}
                    WHERE book_id = %s
                """
                update_values.append(book_id)

                # Execute update
                with self.db.get_cursor() as cursor:
                    cursor.execute(update_query, update_values)

                logger.info(f"  ✅ Updated book_id={book_id}: {original_title}")
                self.stats['books_updated'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to update book_id={book.get('book_id')}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Books updated: {self.stats['books_updated']}")
        return True

    def step2_update_page_maps(self, page_map_data: List[Dict[str, Any]]) -> bool:
        """
        Step 2: Update page_map table with corrected page labels.

        Args:
            page_map_data: List of page_map records from Google Sheets

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 2: Updating page maps")
        logger.info("="*70)

        if not page_map_data:
            logger.info("No page map data to update")
            return True

        # Filter by book_ids if specified
        if self.book_ids_filter:
            page_map_data = [pm for pm in page_map_data if pm.get('book_id') in self.book_ids_filter]
            logger.info(f"Filtered to {len(page_map_data)} page maps based on --book-ids")

        if not page_map_data:
            logger.info("No page maps match the filter criteria")
            return True

        # Get existing page maps from database for comparison
        existing_page_maps = {}
        if not self.dry_run:
            try:
                # Build WHERE clause for filtering
                where_clause = ""
                if self.book_ids_filter:
                    book_ids_str = ','.join(map(str, self.book_ids_filter))
                    where_clause = f"WHERE book_id IN ({book_ids_str})"

                query = f"""
                    SELECT book_id, page_number, page_label
                    FROM page_map
                    {where_clause}
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(query)
                    results = cursor.fetchall()

                    for row in results:
                        key = (row['book_id'], row['page_number'])
                        existing_page_maps[key] = row['page_label']

            except Exception as e:
                logger.error(f"Failed to load existing page maps: {e}")
                return False

        # Compare and update only changed page labels
        updates_needed = []
        for pm in page_map_data:
            book_id = pm.get('book_id')
            page_number = pm.get('page_number')

            # Handle page_label - can be string or number
            page_label_value = pm.get('page_label', '')
            if page_label_value not in ('', None):
                new_page_label = str(page_label_value).strip()
            else:
                new_page_label = ''

            if not book_id or not page_number:
                continue

            key = (book_id, page_number)
            existing_label = existing_page_maps.get(key, '')

            # Check if label changed
            if new_page_label != existing_label:
                updates_needed.append({
                    'book_id': book_id,
                    'page_number': page_number,
                    'page_label': new_page_label
                })

        if not updates_needed:
            logger.info("No page label changes detected")
            return True

        logger.info(f"Found {len(updates_needed)} page labels that need updating")

        for pm in tqdm(updates_needed, desc="Updating page maps"):
            try:
                if self.dry_run:
                    logger.debug(f"  [DRY RUN] Would update page_label for book_id={pm['book_id']}, page={pm['page_number']}")
                    self.stats['page_maps_updated'] += 1
                    continue

                update_query = """
                    UPDATE page_map
                    SET page_label = %s
                    WHERE book_id = %s AND page_number = %s
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(update_query, (pm['page_label'], pm['book_id'], pm['page_number']))

                self.stats['page_maps_updated'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to update page_map for book_id={pm['book_id']}, page={pm['page_number']}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Page maps updated: {self.stats['page_maps_updated']}")
        return True

    def step3_insert_table_of_contents(self, toc_data: List[Dict[str, Any]]) -> bool:
        """
        Step 3: Insert table_of_contents entries from Google Sheets.

        Args:
            toc_data: List of TOC records from Google Sheets

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 3: Inserting table of contents")
        logger.info("="*70)

        if not toc_data:
            logger.info("No TOC data to insert")
            return True

        # Filter by book_ids if specified
        if self.book_ids_filter:
            toc_data = [t for t in toc_data if t.get('book_id') in self.book_ids_filter]
            logger.info(f"Filtered to {len(toc_data)} TOC entries based on --book-ids")

        if not toc_data:
            logger.info("No TOC entries match the filter criteria")
            return True

        # Sort by book_id and page_number to maintain proper ordering for hierarchy
        # This ensures TOC entries appear in the order they occur in the book
        toc_data = sorted(toc_data, key=lambda x: (x.get('book_id', 0), x.get('page_number', 0)))

        # Delete existing TOC entries for the books we're processing
        # This is necessary because parent_toc_id relationships need to be rebuilt
        books_to_process = set(t.get('book_id') for t in toc_data if t.get('book_id'))

        if not self.dry_run:
            try:
                for book_id in books_to_process:
                    delete_query = "DELETE FROM table_of_contents WHERE book_id = %s"
                    with self.db.get_cursor() as cursor:
                        cursor.execute(delete_query, (book_id,))
                        deleted_count = cursor.rowcount
                        if deleted_count > 0:
                            logger.info(f"Deleted {deleted_count} existing TOC entries for book_id={book_id}")
            except Exception as e:
                logger.error(f"Failed to delete existing TOC entries: {e}")
                return False

        # Track parent TOC IDs by level for hierarchical insertion
        # Format: parent_stack[book_id][level] = toc_id
        parent_stack: Dict[int, Dict[int, int]] = {}

        logger.info(f"Inserting {len(toc_data)} TOC entries with hierarchical relationships")

        current_book_id = None
        for toc in tqdm(toc_data, desc="Inserting TOC entries"):
            try:
                book_id = toc.get('book_id')
                if not book_id:
                    continue

                # Initialize parent stack for new book
                if current_book_id != book_id:
                    current_book_id = book_id
                    parent_stack[book_id] = {}
                    logger.info(f"Processing TOC for book_id={book_id}")

                toc_label = str(toc.get('toc_label', '')).strip() if toc.get('toc_label') else ''
                page_number = toc.get('page_number')
                toc_level = toc.get('toc_level', 1)

                # Handle page_label - can be string or number
                page_label_value = toc.get('page_label', '')
                if page_label_value not in ('', None):
                    page_label = str(page_label_value).strip()
                else:
                    page_label = ''

                if not toc_label or not page_number:
                    logger.warning(f"Skipping TOC entry: missing toc_label or page_number")
                    continue

                # Determine parent_toc_id based on hierarchy within this book
                parent_toc_id = None
                if toc_level > 1:
                    # Find the immediate parent (last inserted at level - 1 for this book)
                    parent_toc_id = parent_stack[book_id].get(toc_level - 1)
                    if parent_toc_id is None:
                        logger.warning(
                            f"No parent found for book {book_id}, "
                            f"level {toc_level} ('{toc_label[:30]}...'), treating as top-level"
                        )

                if self.dry_run:
                    logger.debug(f"  [DRY RUN] Would insert TOC: {toc_label} (book_id={book_id}, level={toc_level}, parent={parent_toc_id})")
                    self.stats['toc_entries_inserted'] += 1
                    # Simulate toc_id for parent stack in dry-run
                    parent_stack[book_id][toc_level] = 9999
                    continue

                # Insert the TOC entry with parent_toc_id
                insert_query = """
                    INSERT INTO table_of_contents (book_id, toc_level, toc_label, page_number, page_label, parent_toc_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING toc_id
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(insert_query, (
                        book_id,
                        toc_level,
                        toc_label,
                        page_number,
                        page_label if page_label else None,
                        parent_toc_id
                    ))
                    result = cursor.fetchone()
                    if result:
                        toc_id = result['toc_id']

                        # Update parent stack for this book
                        parent_stack[book_id][toc_level] = toc_id

                        # Clear deeper levels from stack (new sibling invalidates children)
                        levels_to_clear = [
                            lvl for lvl in parent_stack[book_id] if lvl > toc_level
                        ]
                        for lvl in levels_to_clear:
                            del parent_stack[book_id][lvl]

                        self.stats['toc_entries_inserted'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to insert TOC entry '{toc.get('toc_label')}': {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 TOC entries inserted: {self.stats['toc_entries_inserted']}")
        return True

    def step4_insert_glossary(self, glossary_data: List[Dict[str, Any]]) -> bool:
        """
        Step 4: Insert glossary entries from Google Sheets.

        Args:
            glossary_data: List of glossary records from Google Sheets

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 4: Inserting glossary entries")
        logger.info("="*70)

        if not glossary_data:
            logger.info("No glossary data to insert")
            return True

        # Filter out empty rows and by book_ids
        glossary_data = [g for g in glossary_data if g.get('term', '').strip()]

        if self.book_ids_filter:
            glossary_data = [g for g in glossary_data if g.get('book_id') in self.book_ids_filter]
            logger.info(f"Filtered to {len(glossary_data)} glossary entries based on --book-ids")

        if not glossary_data:
            logger.info("No glossary entries to insert")
            return True

        # Get existing glossary entries to avoid duplicates
        existing_glossary = set()
        if not self.dry_run:
            try:
                where_clause = ""
                if self.book_ids_filter:
                    book_ids_str = ','.join(map(str, self.book_ids_filter))
                    where_clause = f"WHERE book_id IN ({book_ids_str})"

                query = f"""
                    SELECT book_id, term
                    FROM glossary
                    {where_clause}
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(query)
                    results = cursor.fetchall()

                    for row in results:
                        key = (row['book_id'], row['term'])
                        existing_glossary.add(key)

                logger.info(f"Found {len(existing_glossary)} existing glossary entries")

            except Exception as e:
                logger.error(f"Failed to load existing glossary entries: {e}")
                return False

        # Insert new glossary entries
        new_entries = []
        for g in glossary_data:
            book_id = g.get('book_id')
            term = str(g.get('term', '')).strip() if g.get('term') else ''
            # Read from 'description' column (matching Google Sheets header)
            description = str(g.get('description', '')).strip() if g.get('description') else ''

            if not book_id or not term or not description:
                continue

            key = (book_id, term)
            if key not in existing_glossary:
                new_entries.append({
                    'book_id': book_id,
                    'term': term,
                    'description': description
                })

        if not new_entries:
            logger.info("No new glossary entries to insert (all already exist)")
            return True

        logger.info(f"Inserting {len(new_entries)} new glossary entries")

        for g in tqdm(new_entries, desc="Inserting glossary"):
            try:
                if self.dry_run:
                    logger.debug(f"  [DRY RUN] Would insert glossary term: {g['term']} (book_id={g['book_id']})")
                    self.stats['glossary_entries_inserted'] += 1
                    continue

                insert_query = """
                    INSERT INTO glossary (book_id, term, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (book_id, term) DO UPDATE
                    SET description = EXCLUDED.description
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(insert_query, (
                        g['book_id'],
                        g['term'],
                        g['description']
                    ))

                self.stats['glossary_entries_inserted'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to insert glossary entry '{g.get('term')}': {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Glossary entries inserted: {self.stats['glossary_entries_inserted']}")
        return True

    def step5_insert_verse_index(self, verse_data: List[Dict[str, Any]]) -> bool:
        """
        Step 5: Insert verse_index entries from Google Sheets.

        Args:
            verse_data: List of verse_index records from Google Sheets

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 5: Inserting verse index entries")
        logger.info("="*70)

        if not verse_data:
            logger.info("No verse index data to insert")
            return True

        # Filter out empty rows and by book_ids
        verse_data = [v for v in verse_data if v.get('verse_name', '').strip()]

        if self.book_ids_filter:
            verse_data = [v for v in verse_data if v.get('book_id') in self.book_ids_filter]
            logger.info(f"Filtered to {len(verse_data)} verse entries based on --book-ids")

        if not verse_data:
            logger.info("No verse index entries to insert")
            return True

        # Get existing verse entries to avoid duplicates
        existing_verses = set()
        if not self.dry_run:
            try:
                where_clause = ""
                if self.book_ids_filter:
                    book_ids_str = ','.join(map(str, self.book_ids_filter))
                    where_clause = f"WHERE book_id IN ({book_ids_str})"

                query = f"""
                    SELECT book_id, verse_name, page_number
                    FROM verse_index
                    {where_clause}
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(query)
                    results = cursor.fetchall()

                    for row in results:
                        key = (row['book_id'], row['verse_name'], row['page_number'])
                        existing_verses.add(key)

                logger.info(f"Found {len(existing_verses)} existing verse entries")

            except Exception as e:
                logger.error(f"Failed to load existing verse entries: {e}")
                return False

        # Insert new verse entries
        new_entries = []
        for v in verse_data:
            book_id = v.get('book_id')
            verse_name = str(v.get('verse_name', '')).strip() if v.get('verse_name') else ''
            page_number = v.get('page_number')

            if not book_id or not verse_name or not page_number:
                continue

            key = (book_id, verse_name, page_number)
            if key not in existing_verses:
                new_entries.append({
                    'book_id': book_id,
                    'verse_name': verse_name,
                    'page_number': page_number
                })

        if not new_entries:
            logger.info("No new verse entries to insert (all already exist)")
            return True

        logger.info(f"Inserting {len(new_entries)} new verse entries")

        for v in tqdm(new_entries, desc="Inserting verse index"):
            try:
                if self.dry_run:
                    logger.debug(f"  [DRY RUN] Would insert verse: {v['verse_name']} (book_id={v['book_id']})")
                    self.stats['verse_entries_inserted'] += 1
                    continue

                insert_query = """
                    INSERT INTO verse_index (book_id, verse_name, page_number)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (book_id, verse_name, page_number) DO NOTHING
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(insert_query, (
                        v['book_id'],
                        v['verse_name'],
                        v['page_number']
                    ))

                self.stats['verse_entries_inserted'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to insert verse entry '{v.get('verse_name')}': {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Verse entries inserted: {self.stats['verse_entries_inserted']}")
        return True

    def run(self) -> Dict[str, int]:
        """
        Run the complete Part 2 workflow.

        Returns:
            Dictionary with execution statistics
        """
        start_time = datetime.now()

        logger.info("\n" + "="*70)
        logger.info("📚 BOOK LOADER - PART 2")
        logger.info("="*70)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'PRODUCTION'}")
        if self.book_ids_filter:
            logger.info(f"Processing book IDs: {sorted(self.book_ids_filter)}")
        else:
            logger.info("Processing: ALL books")
        logger.info("="*70)

        try:
            # Authenticate with Google Sheets
            if not self.sheets_reader.authenticate():
                raise Exception("Failed to authenticate with Google Sheets")

            # Read all sheets
            logger.info("\n📖 Reading data from Google Sheets...")
            book_data = self.sheets_reader.read_sheet_as_dicts('book')
            page_map_data = self.sheets_reader.read_sheet_as_dicts('page_map')
            toc_data = self.sheets_reader.read_sheet_as_dicts('table_of_contents')
            glossary_data = self.sheets_reader.read_sheet_as_dicts('glossary')
            verse_data = self.sheets_reader.read_sheet_as_dicts('verse_index')

            # Step 1: Update books
            self.step1_update_books(book_data)

            # Step 2: Update page maps
            self.step2_update_page_maps(page_map_data)

            # Step 3: Insert TOC
            self.step3_insert_table_of_contents(toc_data)

            # Step 4: Insert glossary
            self.step4_insert_glossary(glossary_data)

            # Step 5: Insert verse index
            self.step5_insert_verse_index(verse_data)

        except KeyboardInterrupt:
            logger.warning("\n⚠️  Process interrupted by user")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self.stats['errors'] += 1

        # Print final summary
        elapsed = datetime.now() - start_time
        self.print_summary(elapsed)

        return self.stats

    def print_summary(self, elapsed):
        """Print execution summary."""
        logger.info("\n" + "="*70)
        logger.info("📊 EXECUTION SUMMARY")
        logger.info("="*70)
        logger.info(f"Books updated: {self.stats['books_updated']}")
        logger.info(f"Page maps updated: {self.stats['page_maps_updated']}")
        logger.info(f"TOC entries inserted: {self.stats['toc_entries_inserted']}")
        logger.info(f"Glossary entries inserted: {self.stats['glossary_entries_inserted']}")
        logger.info(f"Verse entries inserted: {self.stats['verse_entries_inserted']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Elapsed time: {elapsed}")
        logger.info("="*70)

        if self.dry_run:
            logger.info("\n⚠️  This was a DRY RUN - no data was written")
        elif self.stats['errors'] == 0:
            total_changes = (self.stats['books_updated'] +
                           self.stats['page_maps_updated'] +
                           self.stats['toc_entries_inserted'] +
                           self.stats['glossary_entries_inserted'] +
                           self.stats['verse_entries_inserted'])

            if total_changes > 0:
                logger.info("\n🎉 Part 2 completed successfully!")
                logger.info("\n📝 Next steps:")
                logger.info("   1. Verify data in database")
                logger.info("   2. Test book display in web app")
                logger.info("   3. Deploy static assets if needed")
            else:
                logger.info("\n✅ No changes needed - all data is up to date")
        else:
            logger.warning(f"\n⚠️  Completed with {self.stats['errors']} errors")


@click.command()
@click.option('--book-ids', help='Comma-separated list of book IDs to process (e.g., 121,122,123)')
@click.option('--dry-run', is_flag=True, help='Validation mode: no database writes')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(book_ids, dry_run, verbose):
    """
    Book Loader Part 2 - Sync reviewed data from Google Sheets to database.

    Reads enriched/reviewed data from Google Sheets and:
    - Updates book table with complete metadata
    - Updates page_map table with corrected page labels
    - Inserts table_of_contents entries
    - Inserts glossary entries (if present)
    - Inserts verse_index entries (if present)
    """

    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    load_dotenv(override=True)

    # Get configuration from environment
    google_credentials = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    google_sheet_id = os.getenv('GOOGLE_BOOK_LOADER_SHEET_ID')

    # Validate configuration
    if not google_credentials:
        logger.error("❌ GOOGLE_SERVICE_ACCOUNT_FILE not set in .env file")
        sys.exit(1)

    if not google_sheet_id:
        logger.error("❌ GOOGLE_BOOK_LOADER_SHEET_ID not set in .env file")
        sys.exit(1)

    # Parse book IDs if provided
    book_ids_list = None
    if book_ids:
        try:
            book_ids_list = [int(bid.strip()) for bid in book_ids.split(',')]
            logger.info(f"Processing specific book IDs: {book_ids_list}")
        except ValueError:
            logger.error("❌ Invalid book IDs format. Use comma-separated integers (e.g., 121,122,123)")
            sys.exit(1)

    try:
        # Initialize loader
        loader = BookLoaderPart2(
            google_credentials=google_credentials,
            google_sheet_id=google_sheet_id,
            book_ids=book_ids_list,
            dry_run=dry_run
        )

        # Run the workflow
        stats = loader.run()

        # Exit with appropriate code
        if stats['errors'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
