#!/usr/bin/env python3
"""
Book Loader - Part 1

Automates the initial book loading process:
1. Scans PDF_FOLDER for new PDFs
2. Creates minimal book records in database (only new PDFs)
3. Writes book metadata to Google Sheets for manual enrichment
4. Generates page maps (database + Google Sheets)
5. Extracts TOC from PDF bookmarks (writes to Google Sheets only)
6. Renders WebP images for all new books

After Part 1, content managers can:
- Add missing book metadata in Google Sheets (book_type, title, author, etc.)
- Review/correct page labels
- Review/edit extracted TOC entries
- Add glossary and verse index entries

Requirements:
    pip install gspread google-auth PyMuPDF psycopg2-binary python-dotenv tqdm click

Usage:
    # Normal mode
    python book_loader_part1.py

    # Dry-run mode (validation only, no writes)
    python book_loader_part1.py --dry-run

    # Verbose logging
    python book_loader_part1.py --verbose
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

import click
import fitz  # PyMuPDF
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from tqdm import tqdm

# Import our existing utilities
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from page_map_builder import PageMapBuilderRef, normalize_page_label
from render_pdf_pages import PDFPageRenderer
from bookmark_extractor import BookmarkExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GoogleSheetsWriter:
    """Handles writing data to Google Sheets for manual review."""

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]

    def __init__(self, credentials_file: str, sheet_id: str):
        """
        Initialize Google Sheets writer.

        Args:
            credentials_file: Path to service account JSON credentials
            sheet_id: Google Sheet ID to write to
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

    def append_rows(self, sheet_name: str, rows: List[List[Any]]) -> bool:
        """
        Append rows to a worksheet.

        Args:
            sheet_name: Name of the worksheet tab
            rows: List of rows to append

        Returns:
            True if successful
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            if rows:
                worksheet.append_rows(rows, value_input_option='USER_ENTERED')
                logger.info(f"  ✅ Wrote {len(rows)} rows to '{sheet_name}' tab")
            return True
        except Exception as e:
            logger.error(f"  ❌ Failed to write to '{sheet_name}': {e}")
            return False


class BookLoaderPart1:
    """
    Orchestrator for Part 1 of the book loading process.
    Handles PDF scanning, database inserts, Google Sheets writing, and image rendering.
    """

    def __init__(self,
                 pdf_folder: str,
                 page_folder: str,
                 google_credentials: str,
                 google_sheet_id: str,
                 dry_run: bool = False):
        """
        Initialize Book Loader Part 1.

        Args:
            pdf_folder: Folder containing PDF files
            page_folder: Output folder for WebP images
            google_credentials: Path to Google service account JSON
            google_sheet_id: Google Sheet ID for manual review
            dry_run: If True, validate only without writing
        """
        self.pdf_folder = Path(pdf_folder)
        self.page_folder = Path(page_folder)
        self.dry_run = dry_run
        self.db = PureBhaktiVaultDB()
        self.sheets_writer = GoogleSheetsWriter(google_credentials, google_sheet_id)

        # Validate folders
        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {pdf_folder}")

        self.page_folder.mkdir(parents=True, exist_ok=True)

        # Stats tracking
        self.stats = {
            'pdfs_scanned': 0,
            'pdfs_skipped_existing': 0,
            'books_created': 0,
            'page_maps_created': 0,
            'toc_entries_extracted': 0,
            'images_rendered': 0,
            'errors': 0
        }

    def step1_scan_pdfs(self) -> List[Dict[str, Any]]:
        """
        Step 1: Scan PDF_FOLDER and extract metadata.

        Returns:
            List of PDF metadata dictionaries
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 1: Scanning PDF folder for new books")
        logger.info("="*70)

        pdf_files = sorted(self.pdf_folder.glob("*.pdf"))
        self.stats['pdfs_scanned'] = len(pdf_files)

        if not pdf_files:
            logger.warning(f"No PDF files found in {self.pdf_folder}")
            return []

        logger.info(f"Found {len(pdf_files)} PDF files")

        pdf_metadata = []
        for pdf_path in tqdm(pdf_files, desc="Extracting PDF metadata"):
            try:
                # Check if PDF already exists in database
                existing_book_id = self.db.get_book_id_by_pdf_name(pdf_path.name)
                if existing_book_id:
                    logger.debug(f"  ⏭️  Skipping existing: {pdf_path.name} (book_id={existing_book_id})")
                    self.stats['pdfs_skipped_existing'] += 1
                    continue

                # Extract metadata
                stat = pdf_path.stat()
                file_size_bytes = stat.st_size

                # Get page count
                doc = fitz.open(pdf_path)
                number_of_pages = len(doc)
                doc.close()

                pdf_metadata.append({
                    'pdf_name': pdf_path.name,
                    'file_size_bytes': file_size_bytes,
                    'number_of_pages': number_of_pages,
                    'pdf_path': pdf_path
                })

            except Exception as e:
                logger.error(f"  ❌ Error processing {pdf_path.name}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Scan complete:")
        logger.info(f"   Total PDFs found: {self.stats['pdfs_scanned']}")
        logger.info(f"   Already in database: {self.stats['pdfs_skipped_existing']}")
        logger.info(f"   New PDFs to process: {len(pdf_metadata)}")

        return pdf_metadata

    def step2_create_book_records(self, pdf_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Step 2: Create database book records for new PDFs.

        Args:
            pdf_metadata: List of PDF metadata from step 1

        Returns:
            List of created book records with book_ids
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 2: Creating database book records")
        logger.info("="*70)

        if not pdf_metadata:
            logger.info("No new books to create")
            return []

        new_books = []

        for pdf in tqdm(pdf_metadata, desc="Creating book records"):
            try:
                if self.dry_run:
                    logger.info(f"  [DRY RUN] Would create book: {pdf['pdf_name']}")
                    # Assign dummy book_id for dry-run
                    new_books.append({
                        **pdf,
                        'book_id': 9999,  # Dummy ID
                        'original_book_title': f"[TO BE ADDED] {pdf['pdf_name']}"
                    })
                else:
                    # Insert into database
                    # Use pdf_name as placeholder for original_book_title (required field)
                    insert_query = """
                        INSERT INTO book (pdf_name, original_book_title, number_of_pages, file_size_bytes)
                        VALUES (%s, %s, %s, %s)
                        RETURNING book_id
                    """

                    with self.db.get_cursor() as cursor:
                        cursor.execute(insert_query, (
                            pdf['pdf_name'],
                            f"[TO BE ADDED] {pdf['pdf_name']}",  # Placeholder title
                            pdf['number_of_pages'],
                            pdf['file_size_bytes']
                        ))
                        result = cursor.fetchone()
                        book_id = result['book_id']

                        logger.info(f"  ✅ Created book_id={book_id}: {pdf['pdf_name']}")

                        new_books.append({
                            **pdf,
                            'book_id': book_id,
                            'original_book_title': f"[TO BE ADDED] {pdf['pdf_name']}"
                        })

                        self.stats['books_created'] += 1

            except Exception as e:
                logger.error(f"  ❌ Failed to create book for {pdf['pdf_name']}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Books created: {len(new_books)}")
        return new_books

    def step3_write_to_google_sheets_books(self, new_books: List[Dict[str, Any]]) -> bool:
        """
        Step 3: Write book metadata to Google Sheets book tab.

        Args:
            new_books: List of created book records

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 3: Writing book metadata to Google Sheets")
        logger.info("="*70)

        if not new_books:
            logger.info("No books to write")
            return True

        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {len(new_books)} books to Google Sheets 'book' tab")
            return True

        # Authenticate
        if not self.sheets_writer.authenticate():
            return False

        # Prepare rows for Google Sheets
        # Columns in sheet: book_id, pdf_name, book_type, original_book_title, edition,
        #                   original_author, commentary_author, header_height, footer_height, book_summary
        rows = []
        for book in new_books:
            rows.append([
                book['book_id'],
                book['pdf_name'],
                '',  # book_type - empty for manual entry
                book['original_book_title'],  # Placeholder title
                '',  # edition - empty for manual entry
                '',  # original_author - empty for manual entry
                '',  # commentary_author - empty for manual entry
                '',  # header_height - empty for manual entry
                '',  # footer_height - empty for manual entry
                ''   # book_summary - empty for manual entry
            ])

        return self.sheets_writer.append_rows('book', rows)

    def step4_generate_page_maps(self, new_books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Step 4: Generate page maps for new books (database + Google Sheets).

        Args:
            new_books: List of created book records

        Returns:
            List of all page_map entries created
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 4: Generating page maps")
        logger.info("="*70)

        if not new_books:
            logger.info("No books to process")
            return []

        all_page_maps = []

        for book in tqdm(new_books, desc="Generating page maps"):
            try:
                pdf_path = book['pdf_path']
                book_id = book['book_id']

                if self.dry_run:
                    logger.info(f"  [DRY RUN] Would generate page map for book_id={book_id}")
                    continue

                # Use existing page_map_builder logic
                builder = PageMapBuilderRef(str(self.pdf_folder))
                builder.process_pdf(pdf_path.name)

                # Read back the page maps we just created
                query = """
                    SELECT book_id, page_number, page_label, page_type
                    FROM page_map
                    WHERE book_id = %s
                    ORDER BY page_number
                """

                with self.db.get_cursor() as cursor:
                    cursor.execute(query, (book_id,))
                    page_maps = cursor.fetchall()

                    for pm in page_maps:
                        all_page_maps.append(dict(pm))

                    self.stats['page_maps_created'] += len(page_maps)
                    logger.info(f"  ✅ Generated {len(page_maps)} page maps for book_id={book_id}")

            except Exception as e:
                logger.error(f"  ❌ Failed to generate page maps for book_id={book.get('book_id')}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 Page maps created: {len(all_page_maps)}")
        return all_page_maps

    def step4b_write_page_maps_to_sheets(self, page_maps: List[Dict[str, Any]]) -> bool:
        """
        Step 4b: Write page maps to Google Sheets.

        Args:
            page_maps: List of page_map entries

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 4b: Writing page maps to Google Sheets")
        logger.info("="*70)

        if not page_maps:
            logger.info("No page maps to write")
            return True

        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {len(page_maps)} page maps to Google Sheets")
            return True

        # Prepare rows
        # Columns: book_id, page_number, page_label, page_type
        rows = []
        for pm in page_maps:
            rows.append([
                pm['book_id'],
                pm['page_number'],
                pm['page_label'] or '',
                pm['page_type']
            ])

        return self.sheets_writer.append_rows('page_map', rows)

    def step5_extract_toc_from_bookmarks(self, new_books: List[Dict[str, Any]], page_maps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Step 5: Extract TOC from PDF bookmarks (write to Google Sheets only).

        Args:
            new_books: List of created book records
            page_maps: List of page_map entries for page_number -> page_label mapping

        Returns:
            List of TOC entries extracted
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 5: Extracting TOC from PDF bookmarks")
        logger.info("="*70)

        if not new_books:
            logger.info("No books to process")
            return []

        # Create page_number -> page_label mapping by book_id
        page_label_map = {}
        for pm in page_maps:
            book_id = pm['book_id']
            if book_id not in page_label_map:
                page_label_map[book_id] = {}
            page_label_map[book_id][pm['page_number']] = pm['page_label'] or str(pm['page_number'])

        all_toc_entries = []

        for book in tqdm(new_books, desc="Extracting bookmarks"):
            try:
                pdf_path = book['pdf_path']
                book_id = book['book_id']
                pdf_name = book['pdf_name']

                # Extract bookmarks
                doc = fitz.open(pdf_path)
                toc = doc.get_toc(simple=False)
                doc.close()

                if not toc:
                    logger.info(f"  ⚠️  No bookmarks found in {pdf_name}")
                    continue

                # Convert to our format
                for entry in toc:
                    level = entry[0]
                    title = entry[1].strip() if entry[1] else ""
                    page_number = entry[2]

                    # Map page_number to page_label
                    page_label = page_label_map.get(book_id, {}).get(page_number, str(page_number))

                    all_toc_entries.append({
                        'book_id': book_id,
                        'pdf_name': pdf_name,
                        'toc_level': level,
                        'toc_label': title,
                        'page_number': page_number,
                        'page_label': page_label
                    })

                self.stats['toc_entries_extracted'] += len(toc)
                logger.info(f"  ✅ Extracted {len(toc)} TOC entries from {pdf_name}")

            except Exception as e:
                logger.error(f"  ❌ Failed to extract TOC from {book.get('pdf_name')}: {e}")
                self.stats['errors'] += 1

        logger.info(f"\n📊 TOC entries extracted: {len(all_toc_entries)}")
        return all_toc_entries

    def step5b_write_toc_to_sheets(self, toc_entries: List[Dict[str, Any]]) -> bool:
        """
        Step 5b: Write TOC entries to Google Sheets.

        Args:
            toc_entries: List of TOC entries

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 5b: Writing TOC entries to Google Sheets")
        logger.info("="*70)

        if not toc_entries:
            logger.info("No TOC entries to write")
            return True

        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {len(toc_entries)} TOC entries to Google Sheets")
            return True

        # Prepare rows
        # Columns: book_id, pdf_name, toc_level, toc_label, page_number, page_label
        rows = []
        for toc in toc_entries:
            rows.append([
                toc['book_id'],
                toc['pdf_name'],
                toc['toc_level'],
                toc['toc_label'],
                toc['page_number'],
                toc['page_label']
            ])

        return self.sheets_writer.append_rows('table_of_contents', rows)

    def step6_render_webp_images(self, new_books: List[Dict[str, Any]]) -> bool:
        """
        Step 6: Render WebP images for new books.

        Args:
            new_books: List of created book records

        Returns:
            True if successful
        """
        logger.info("\n" + "="*70)
        logger.info("STEP 6: Rendering WebP images")
        logger.info("="*70)

        if not new_books:
            logger.info("No books to render")
            return True

        if self.dry_run:
            logger.info(f"[DRY RUN] Would render images for {len(new_books)} books")
            return True

        # Extract book_ids
        book_ids = [book['book_id'] for book in new_books]

        try:
            # Database configuration
            db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', 5432)),
                'database': os.getenv('DB_NAME', 'pure_bhakti_vault'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD')
            }

            # Initialize renderer
            renderer = PDFPageRenderer(
                pdf_folder=str(self.pdf_folder),
                page_folder=str(self.page_folder),
                db_config=db_config,
                dpi=int(os.getenv('RENDER_DPI', 150)),
                image_format=os.getenv('RENDER_FORMAT', 'webp'),
                grayscale=os.getenv('RENDER_GRAYSCALE', 'false').lower() == 'true',
                create_thumbnails=False,  # No thumbnails as per requirement
                max_workers=4,
                selected_book_ids=book_ids,
                cleanup_partial=False
            )

            # Render all pages
            stats = renderer.render_all_pages()

            self.stats['images_rendered'] = stats['success']

            logger.info(f"\n📊 Image rendering complete:")
            logger.info(f"   Total pages: {stats['total']}")
            logger.info(f"   Successful: {stats['success']}")
            logger.info(f"   Failed: {stats['failed']}")

            return stats['failed'] == 0

        except Exception as e:
            logger.error(f"  ❌ Image rendering failed: {e}")
            self.stats['errors'] += 1
            return False

    def run(self) -> Dict[str, int]:
        """
        Run the complete Part 1 workflow.

        Returns:
            Dictionary with execution statistics
        """
        start_time = datetime.now()

        logger.info("\n" + "="*70)
        logger.info("📚 BOOK LOADER - PART 1")
        logger.info("="*70)
        logger.info(f"PDF Folder: {self.pdf_folder}")
        logger.info(f"Page Folder: {self.page_folder}")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'PRODUCTION'}")
        logger.info("="*70)

        try:
            # Step 1: Scan PDFs
            pdf_metadata = self.step1_scan_pdfs()

            # Step 2: Create book records
            new_books = self.step2_create_book_records(pdf_metadata)

            # Step 3: Write books to Google Sheets
            self.step3_write_to_google_sheets_books(new_books)

            # Step 4: Generate page maps
            page_maps = self.step4_generate_page_maps(new_books)

            # Step 4b: Write page maps to Google Sheets
            self.step4b_write_page_maps_to_sheets(page_maps)

            # Step 5: Extract TOC from bookmarks
            toc_entries = self.step5_extract_toc_from_bookmarks(new_books, page_maps)

            # Step 5b: Write TOC to Google Sheets
            self.step5b_write_toc_to_sheets(toc_entries)

            # Step 6: Render WebP images
            self.step6_render_webp_images(new_books)

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
        logger.info(f"PDFs scanned: {self.stats['pdfs_scanned']}")
        logger.info(f"PDFs skipped (existing): {self.stats['pdfs_skipped_existing']}")
        logger.info(f"Books created: {self.stats['books_created']}")
        logger.info(f"Page maps created: {self.stats['page_maps_created']}")
        logger.info(f"TOC entries extracted: {self.stats['toc_entries_extracted']}")
        logger.info(f"Images rendered: {self.stats['images_rendered']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Elapsed time: {elapsed}")
        logger.info("="*70)

        if self.dry_run:
            logger.info("\n⚠️  This was a DRY RUN - no data was written")
        elif self.stats['errors'] == 0 and self.stats['books_created'] > 0:
            logger.info("\n🎉 Part 1 completed successfully!")
            logger.info("\n📝 Next steps:")
            logger.info("   1. Open Google Sheets to review/update book metadata")
            logger.info("   2. Fill in: book_type, original_book_title, edition, authors, etc.")
            logger.info("   3. Review/correct page_label values in page_map tab")
            logger.info("   4. Review/edit TOC entries in table_of_contents tab")
            logger.info("   5. Run Part 2 to sync changes back to database")
        elif self.stats['books_created'] == 0:
            logger.info("\n✅ No new books to process")
        else:
            logger.warning(f"\n⚠️  Completed with {self.stats['errors']} errors")


@click.command()
@click.option('--dry-run', is_flag=True, help='Validation mode: no database or Google Sheets writes')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(dry_run, verbose):
    """
    Book Loader Part 1 - Automate initial book loading process.

    Scans PDFs, creates minimal database records, generates page maps,
    extracts TOC from bookmarks, and renders WebP images.
    Writes metadata to Google Sheets for content manager review.
    """

    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    load_dotenv(override=True)

    # Get configuration from environment
    pdf_folder = os.getenv('PDF_FOLDER')
    page_folder = os.getenv('PAGE_FOLDER')
    google_credentials = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    google_sheet_id = os.getenv('GOOGLE_BOOK_LOADER_SHEET_ID')

    # Validate configuration
    if not pdf_folder:
        logger.error("❌ PDF_FOLDER not set in .env file")
        sys.exit(1)

    if not page_folder:
        logger.error("❌ PAGE_FOLDER not set in .env file")
        sys.exit(1)

    if not google_credentials:
        logger.error("❌ GOOGLE_SERVICE_ACCOUNT_FILE not set in .env file")
        sys.exit(1)

    if not google_sheet_id:
        logger.error("❌ GOOGLE_BOOK_LOADER_SHEET_ID not set in .env file")
        sys.exit(1)

    try:
        # Initialize loader
        loader = BookLoaderPart1(
            pdf_folder=pdf_folder,
            page_folder=page_folder,
            google_credentials=google_credentials,
            google_sheet_id=google_sheet_id,
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
