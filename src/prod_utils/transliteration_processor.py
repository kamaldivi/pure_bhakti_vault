#!/usr/bin/env python3
"""
PDF Content Transliteration Processor
======================================

Processes PDF files to extract raw content, apply Sanskrit IAST transliteration fixes,
and store the corrected content in the database.

Features:
- Reads books from database (book_type = 'english-gurudev')
- Extracts content from PDFs using PyMuPDF (fitz)
- Applies transliteration fixes using sanskrit_utils
- Stores corrected content in content.page_content column
- Resume capability: picks up from last unprocessed page
- Header/footer exclusion using book table margins
- Multi-column layout auto-detection with natural reading order sorting
- Support for processing specific books or all books
- Comprehensive logging

Usage:
    # Process all books with default settings (full page, auto-detect columns)
    python transliteration_processor.py

    # Process specific book with full page (default)
    python transliteration_processor.py --book-id 3

    # Process specific book, exclude header/footer, force natural reading order
    python transliteration_processor.py --book-id 3 --full-page no --sort true

    # Process with auto-detection of multi-column layout
    python transliteration_processor.py --book-id 5 --sort auto

Command-Line Arguments:
    --book-id ID         Process specific book ID only (reprocesses all pages)
    --full-page yes|no   Include header/footer? (default: yes - full page)
    --sort true|false|auto  Text extraction order (default: auto - detect multi-column)
    --pdf-folder PATH    Custom PDF folder path

Dependencies:
    pip install PyMuPDF psycopg2-binary python-dotenv

Author: Pure Bhakti Vault Team
Version: 2.1.0
"""

import os
import sys
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import fitz  # PyMuPDF
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prod_utils.pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from prod_utils.sanskrit_utils import process_page

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class PDFContentTransliterationProcessor:
    """
    Processes PDF files to extract and fix Sanskrit transliteration errors.
    """

    def __init__(
        self,
        pdf_folder: str = "/opt/pbb_static_content/pbb_pdf_files/",
        full_page: bool = True,
        sort_mode: bool | str = 'auto'
    ):
        """
        Initialize the processor.

        Args:
            pdf_folder: Path to folder containing PDF files
            full_page: If True (default), extract full page including header/footer.
                      If False, exclude header/footer using book table margins.
            sort_mode: Text extraction sort order:
                      - 'auto' (default): Auto-detect multi-column layouts
                      - True: Force natural reading order (for multi-column)
                      - False: PDF indexed order
        """
        self.pdf_folder = pdf_folder
        self.full_page = full_page
        self.sort_mode = sort_mode
        self.db = PureBhaktiVaultDB()

        # Verify PDF folder exists
        if not os.path.exists(pdf_folder):
            logger.warning(f"PDF folder does not exist: {pdf_folder}")

        logger.info("PDF Content Transliteration Processor initialized")
        logger.info(f"PDF folder: {pdf_folder}")
        logger.info(f"Full page mode: {full_page}")
        logger.info(f"Sort mode: {sort_mode}")

    def get_books_to_process(self) -> List[Dict]:
        """
        Get list of books to process from database.

        Returns:
            List of dicts with book_id and pdf_name
        """
        query = """
            SELECT book_id, pdf_name
            FROM book
            WHERE book_type = 'english-gurudev'
            ORDER BY book_id
        """

        try:
            books = self.db.execute_query(query, fetch='all')
            logger.info(f"Found {len(books)} books with type 'english-gurudev'")
            return books
        except DatabaseError as e:
            logger.error(f"Failed to get books from database: {e}")
            raise

    def get_last_processed_page(self, book_id: int) -> Optional[int]:
        """
        Get the last processed page for a book (page with page_content populated).

        Args:
            book_id: The book ID

        Returns:
            Page number of last processed page, or None if no pages processed
        """
        query = """
            SELECT MAX(page_number) as last_page
            FROM content
            WHERE book_id = %s
            AND page_content IS NOT NULL
            AND page_content != ''
        """

        try:
            result = self.db.execute_query(query, params=(book_id,), fetch='one')
            last_page = result['last_page'] if result and result['last_page'] else None

            if last_page:
                logger.info(f"Book {book_id}: Last processed page is {last_page}")
            else:
                logger.info(f"Book {book_id}: No pages processed yet")

            return last_page
        except DatabaseError as e:
            logger.error(f"Failed to get last processed page for book {book_id}: {e}")
            return None

    def get_pages_to_process(self, book_id: int, start_page: int = 1, total_pages: int = None) -> List[int]:
        """
        Get list of page numbers that need processing.

        This method combines two approaches:
        1. Pages that exist in content table but have NULL page_content
        2. ALL pages from PDF (1 to total_pages) if total_pages is provided

        The second approach ensures we don't miss pages that aren't in content table yet.

        Args:
            book_id: The book ID
            start_page: Page number to start from (1-based)
            total_pages: Total pages in PDF (if known). If provided, will process ALL pages.

        Returns:
            List of page numbers to process
        """
        if total_pages:
            # Process ALL pages from PDF, checking which ones need page_content
            # This ensures we don't miss pages not in content table
            query = """
                SELECT page_number
                FROM content
                WHERE book_id = %s
                AND page_number >= %s
                AND page_number <= %s
                AND (page_content IS NULL OR page_content = '')
            """

            try:
                results = self.db.execute_query(query, params=(book_id, start_page, total_pages), fetch='all')
                existing_pages_needing_processing = set(r['page_number'] for r in results)

                # Get all pages that should exist (1 to total_pages from PDF)
                all_pages = set(range(start_page, total_pages + 1))

                # Filter existing pages to only include pages that exist in PDF
                # (in case database has incorrect page numbers beyond PDF page count)
                existing_pages_valid = existing_pages_needing_processing & all_pages

                # Pages not in content table at all need processing too
                pages_to_process = sorted(all_pages | existing_pages_valid)

                # Log if we found invalid pages in database
                invalid_pages = existing_pages_needing_processing - all_pages
                if invalid_pages:
                    invalid_list = sorted(invalid_pages)[:10]
                    more_indicator = '...' if len(invalid_pages) > 10 else ''
                    logger.warning(f"Book {book_id}: Found {len(invalid_pages)} pages in content table "
                                 f"beyond PDF page count ({total_pages}): {invalid_list}{more_indicator}")

                if pages_to_process:
                    logger.info(f"Book {book_id}: Found {len(pages_to_process)} pages to process "
                              f"(from page {pages_to_process[0]} to {pages_to_process[-1]})")
                    logger.info(f"  - Pages in content table needing update: {len(existing_pages_valid)}")
                    logger.info(f"  - Pages to be newly inserted: {len(all_pages - existing_pages_valid)}")
                else:
                    logger.info(f"Book {book_id}: No pages to process")

                return pages_to_process

            except DatabaseError as e:
                logger.error(f"Failed to get pages to process for book {book_id}: {e}")
                return []
        else:
            # Fallback: Only process pages that exist in content table
            query = """
                SELECT page_number
                FROM content
                WHERE book_id = %s
                AND page_number >= %s
                AND (page_content IS NULL OR page_content = '')
                ORDER BY page_number
            """

            try:
                results = self.db.execute_query(query, params=(book_id, start_page), fetch='all')
                page_numbers = [r['page_number'] for r in results]

                if page_numbers:
                    logger.info(f"Book {book_id}: Found {len(page_numbers)} pages to process "
                              f"(from page {page_numbers[0]} to {page_numbers[-1]})")
                else:
                    logger.info(f"Book {book_id}: No pages to process (all pages already have page_content)")

                return page_numbers
            except DatabaseError as e:
                logger.error(f"Failed to get pages to process for book {book_id}: {e}")
                return []

    def detect_multi_column(self, pdf_path: str, page_number: int,
                           header_height: float = 0.0, footer_height: float = None) -> bool:
        """
        Detect if a page has a multi-column layout.

        Args:
            pdf_path: Path to the PDF file
            page_number: Page number (1-based)
            header_height: Height of header region in PDF points
            footer_height: Y-coordinate where footer starts

        Returns:
            True if multi-column layout detected, False otherwise
        """
        try:
            doc = fitz.open(pdf_path)
            page_index = page_number - 1

            if page_index < 0 or page_index >= len(doc):
                doc.close()
                return False

            page = doc[page_index]
            page_rect = page.rect

            # Set footer_height to page height if not provided
            if footer_height is None:
                footer_height = page_rect.height

            # Define content rectangle
            if header_height <= 0 and footer_height >= page_rect.height:
                content_rect = None
            else:
                content_x0 = page_rect.x0
                content_y0 = page_rect.y0 + float(header_height or 0.0)
                content_x1 = page_rect.x1
                content_y1 = float(footer_height or page_rect.height)

                if content_y0 >= content_y1:
                    content_rect = None
                else:
                    content_rect = fitz.Rect(content_x0, content_y0, content_x1, content_y1)

            # Get text blocks with positions
            if content_rect:
                text_dict = page.get_text("dict", clip=content_rect)
            else:
                text_dict = page.get_text("dict")

            # Analyze x-positions of text blocks
            x_positions = []
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    bbox = block.get("bbox", [])
                    if bbox:
                        x_positions.append(bbox[0])  # Left x-coordinate

            doc.close()

            # If we have enough blocks, check for distinct columns
            if len(x_positions) < 10:
                return False

            # Sort x-positions and look for a gap (column separator)
            x_positions.sort()
            page_width = page_rect.width
            mid_point = page_width / 2

            # Count blocks on left vs right half
            left_count = sum(1 for x in x_positions if x < mid_point)
            right_count = sum(1 for x in x_positions if x >= mid_point)

            # If roughly balanced between left and right, likely multi-column
            total = len(x_positions)
            left_ratio = left_count / total
            right_ratio = right_count / total

            # Consider multi-column if both sides have at least 30% of blocks
            is_multi = (left_ratio >= 0.3 and right_ratio >= 0.3)

            if is_multi:
                logger.debug(f"Page {page_number}: Multi-column detected "
                           f"(left: {left_ratio:.1%}, right: {right_ratio:.1%})")

            return is_multi

        except Exception as e:
            logger.error(f"Failed to detect multi-column on page {page_number}: {e}")
            return False

    def is_devanagari_font(self, font_name: str) -> bool:
        """
        Check if a font name indicates Devanagari/Hindi/Bengali script.

        Args:
            font_name: Name of the font

        Returns:
            True if font is for Devanagari script
        """
        if not font_name:
            return False

        font_lower = font_name.lower()
        devanagari_indicators = [
            'devanagari', 'sanskrit', 'hindi', 'bengali', 'mangal',
            'siddhanta', 'chandas', 'aaritu', 'narad', 'kruti'
        ]

        return any(indicator in font_lower for indicator in devanagari_indicators)

    def extract_page_content(self, pdf_path: str, page_number: int,
                            header_height: float = 0.0, footer_height: float = None,
                            exclude_devanagari: bool = True, sort_text: bool = False) -> Optional[str]:
        """
        Extract raw text content from a PDF page using PyMuPDF, excluding header/footer.

        Args:
            pdf_path: Path to the PDF file
            page_number: Page number (1-based)
            header_height: Height of header region in PDF points (from top). Default 0.
            footer_height: Y-coordinate where footer starts (from top). If None, uses page height.
            exclude_devanagari: If True, exclude text in Devanagari/Sanskrit fonts (default: True)
            sort_text: If True, sort text blocks in natural reading order (for multi-column). Default False.

        Returns:
            Extracted text content, or None if extraction fails
        """
        try:
            # Open PDF
            doc = fitz.open(pdf_path)

            # Convert to 0-based index for PyMuPDF
            page_index = page_number - 1

            # Check if page exists
            if page_index < 0 or page_index >= len(doc):
                logger.error(f"Page {page_number} out of range (PDF has {len(doc)} pages)")
                doc.close()
                return None

            # Get page
            page = doc[page_index]
            page_rect = page.rect

            # Set footer_height to page height if not provided
            if footer_height is None:
                footer_height = page_rect.height

            # Convert header_height and footer_height to floats
            header_height = float(header_height or 0.0)
            footer_height = float(footer_height or page_rect.height)

            # Define content rectangle for header/footer exclusion
            if header_height <= 0 and footer_height >= page_rect.height:
                content_rect = None  # No clipping - use full page
            else:
                # Exclude header/footer - extract only content region
                content_x0 = page_rect.x0
                content_y0 = page_rect.y0 + header_height  # Start below header
                content_x1 = page_rect.x1
                content_y1 = footer_height  # End at footer start

                # Ensure valid content area
                if content_y0 >= content_y1:
                    logger.warning(f"Invalid content area for page {page_number}: "
                                 f"header={header_height}, footer={footer_height}, page_height={page_rect.height}")
                    content_rect = None  # Fallback to full page
                else:
                    # Create rectangle for main content area
                    content_rect = fitz.Rect(content_x0, content_y0, content_x1, content_y1)
                    logger.debug(f"Page {page_number}: Excluded header={header_height}pt, "
                               f"footer start={footer_height}pt, content height={content_y1-content_y0}pt")

            # Extract text with optional Devanagari filtering
            if exclude_devanagari:
                text = self._extract_text_excluding_devanagari(page, content_rect, page_number, sort_text)
            else:
                # Standard extraction (backward compatible)
                if content_rect:
                    text = page.get_text("text", clip=content_rect, sort=sort_text)
                else:
                    text = page.get_text("text", sort=sort_text)

            # Close document
            doc.close()

            return text

        except Exception as e:
            logger.error(f"Failed to extract content from page {page_number}: {e}")
            return None

    def _extract_text_excluding_devanagari(self, page, content_rect, page_number: int, sort_text: bool = False) -> str:
        """
        Extract text from page, excluding Devanagari script blocks.

        Uses get_text("dict") to access font metadata and filters out
        text spans that use Devanagari/Sanskrit fonts.

        Args:
            page: PyMuPDF page object
            content_rect: Optional rectangle to clip extraction area
            page_number: Page number for logging
            sort_text: If True, sort text blocks by position (natural reading order)

        Returns:
            Extracted text with Devanagari blocks excluded
        """
        try:
            # Get text blocks with font information
            if content_rect:
                text_dict = page.get_text("dict", clip=content_rect)
            else:
                text_dict = page.get_text("dict")

            # Track statistics
            total_spans = 0
            devanagari_spans = 0
            collected_lines = []  # Store tuples of (y_position, x_position, text)

            # Process blocks
            for block in text_dict.get("blocks", []):
                # Skip image blocks
                if block.get("type") != 0:
                    continue

                # Process lines in text block
                for line in block.get("lines", []):
                    line_text = []
                    line_bbox = line.get("bbox", [0, 0, 0, 0])  # [x0, y0, x1, y1]

                    # Process spans in line
                    for span in line.get("spans", []):
                        total_spans += 1
                        font_name = span.get("font", "")
                        text = span.get("text", "")

                        # Check if this span uses Devanagari font
                        if self.is_devanagari_font(font_name):
                            devanagari_spans += 1
                            logger.debug(f"Page {page_number}: Excluding Devanagari text '{text[:50]}...' "
                                       f"(font: {font_name})")
                        else:
                            # Keep non-Devanagari text
                            line_text.append(text)

                    # Add line text with position if any
                    if line_text:
                        y_pos = line_bbox[1]  # Top y-coordinate
                        x_pos = line_bbox[0]  # Left x-coordinate
                        collected_lines.append((y_pos, x_pos, "".join(line_text)))

            # Sort lines if requested (for multi-column layouts)
            if sort_text:
                # Sort by y-position first (top to bottom), then x-position (left to right)
                # Small tolerance for y-position to handle lines on same row
                collected_lines.sort(key=lambda item: (round(item[0] / 5) * 5, item[1]))
                logger.debug(f"Page {page_number}: Sorted {len(collected_lines)} lines by position")

            # Extract just the text (discard position info)
            collected_text = [line[2] for line in collected_lines]

            # Log summary
            if devanagari_spans > 0:
                logger.info(f"Page {page_number}: Excluded {devanagari_spans}/{total_spans} Devanagari text spans")

            # Reconstruct text with newlines between lines
            return "\n".join(collected_text)

        except Exception as e:
            logger.error(f"Failed to extract text excluding Devanagari on page {page_number}: {e}")
            # Fallback to standard extraction
            if content_rect:
                return page.get_text("text", clip=content_rect)
            else:
                return page.get_text()

    def apply_transliteration_fix(self, raw_text: str, page_number: int) -> Tuple[str, Dict]:
        """
        Apply transliteration fixes to raw text.

        Args:
            raw_text: Raw text extracted from PDF
            page_number: Page number for tracking

        Returns:
            Tuple of (corrected_text, statistics_dict)
        """
        try:
            # Process the page using sanskrit_utils
            result = process_page(raw_text, page_number=page_number)

            # Extract statistics
            stats = {
                'total_words': result.statistics.total_words,
                'words_corrected': result.statistics.words_corrected,
                'processing_time_ms': result.processing_time * 1000,
                'high_confidence': result.statistics.high_confidence,
                'needs_review': result.statistics.needs_manual_review,
            }

            return result.corrected_text, stats

        except Exception as e:
            logger.error(f"Failed to apply transliteration fix: {e}")
            # Return original text if processing fails
            return raw_text, {'error': str(e)}

    def upsert_page_content(self, book_id: int, page_number: int, page_content: str) -> bool:
        """
        Insert or update page_content in the content table.

        Args:
            book_id: The book ID
            page_number: The page number (1-based)
            page_content: The corrected content to store

        Returns:
            True if successful, False otherwise
        """
        # Use INSERT ... ON CONFLICT UPDATE pattern for upsert
        query = """
            INSERT INTO content (book_id, page_number, page_content, created_at, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (book_id, page_number)
            DO UPDATE SET
                page_content = EXCLUDED.page_content,
                updated_at = CURRENT_TIMESTAMP
        """

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id, page_number, page_content))

            logger.debug(f"Upserted page_content for book {book_id}, page {page_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert page_content for book {book_id}, "
                        f"page {page_number}: {e}")
            return False

    def process_book(self, book_id: int, pdf_name: str, force_reprocess: bool = False) -> Tuple[int, int, List[int]]:
        """
        Process a single book - extract and fix transliteration for all pages.

        Args:
            book_id: The book ID
            pdf_name: The PDF filename
            force_reprocess: If True, reprocess ALL pages even if they already have page_content

        Returns:
            Tuple of (total_pages_processed, successful_pages, failed_pages_list)
        """
        logger.info("="*80)
        logger.info(f"Processing Book ID {book_id}: {pdf_name}")
        logger.info("="*80)

        # Construct PDF path
        pdf_path = os.path.join(self.pdf_folder, pdf_name)

        # Check if PDF exists
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file not found: {pdf_path}")
            return 0, 0, []

        # Get book metadata (including header/footer heights)
        try:
            book_info = self.db.get_book_by_id(book_id)
            if not book_info:
                logger.warning(f"No book metadata found for ID: {book_id}")
                header_height = 0.0
                footer_height = None
            else:
                # Get header/footer heights from book table
                db_header_height = book_info.get('header_height', 0.0)
                db_footer_height = book_info.get('footer_height', None)

                # Apply full_page setting
                if self.full_page:
                    # Full page mode: ignore header/footer settings
                    header_height = 0.0
                    footer_height = None
                    logger.info(f"Book {book_id}: Full page mode - including header/footer")
                else:
                    # Body only mode: use header/footer settings from book table
                    header_height = db_header_height
                    footer_height = db_footer_height

                    if header_height or footer_height:
                        logger.info(f"Book {book_id}: Body only mode - excluding header_height={header_height}pt, "
                                  f"footer_height={footer_height}pt")
                    else:
                        logger.info(f"Book {book_id}: No header/footer settings in database - extracting full pages")
        except Exception as e:
            logger.warning(f"Failed to get book metadata: {e}. Using default settings.")
            header_height = 0.0
            footer_height = None

        # Get total pages from PDF
        try:
            doc = fitz.open(pdf_path)
            total_pages_in_pdf = len(doc)
            doc.close()
            logger.info(f"Book {book_id}: PDF has {total_pages_in_pdf} pages")
        except Exception as e:
            logger.error(f"Failed to open PDF to get page count: {e}")
            return 0, 0, []

        # Determine pages to process
        if force_reprocess:
            # Force reprocessing: process ALL pages from 1 to total_pages_in_pdf
            pages_to_process = list(range(1, total_pages_in_pdf + 1))
            logger.info(f"Book {book_id}: Force reprocess mode - processing ALL {len(pages_to_process)} pages")
        else:
            # Normal mode: resume from last processed page
            last_processed = self.get_last_processed_page(book_id)
            start_page = (last_processed + 1) if last_processed else 1

            # Get pages that need processing (passing total_pages to process ALL pages)
            pages_to_process = self.get_pages_to_process(book_id, start_page, total_pages_in_pdf)

            if not pages_to_process:
                logger.info(f"Book {book_id}: All pages already processed. Skipping.")
                return 0, 0, []

        # Process each page
        total_processed = 0
        successful = 0
        failed_pages = []

        for page_num in pages_to_process:
            try:
                logger.info(f"  Processing page {page_num}/{pages_to_process[-1]}...")

                # Determine sort mode for this page
                if self.sort_mode == 'auto':
                    # Auto-detect multi-column layout
                    use_sort = self.detect_multi_column(pdf_path, page_num, header_height, footer_height)
                    if use_sort:
                        logger.info(f"  Page {page_num}: Multi-column detected - using natural reading order")
                else:
                    # Use explicit sort setting
                    use_sort = self.sort_mode

                # Extract raw content (excluding header/footer if configured, with sort if needed)
                raw_content = self.extract_page_content(
                    pdf_path, page_num, header_height, footer_height,
                    exclude_devanagari=True, sort_text=use_sort
                )

                if raw_content is None:
                    logger.error(f"  ✗ Failed to extract content from page {page_num}")
                    failed_pages.append(page_num)
                    # STOP processing on failure as per requirements
                    logger.error(f"STOPPING: Failed page {page_num} - Book ID {book_id}")
                    break

                # Apply transliteration fix
                corrected_content, stats = self.apply_transliteration_fix(raw_content, page_num)

                # Store in database
                if self.upsert_page_content(book_id, page_num, corrected_content):
                    successful += 1
                    logger.info(f"  ✓ Page {page_num} processed: "
                              f"{stats.get('words_corrected', 0)} words corrected, "
                              f"{stats.get('processing_time_ms', 0):.2f}ms")
                else:
                    logger.error(f"  ✗ Failed to store content for page {page_num}")
                    failed_pages.append(page_num)
                    # STOP processing on failure
                    logger.error(f"STOPPING: Failed to store page {page_num} - Book ID {book_id}")
                    break

                total_processed += 1

            except Exception as e:
                logger.error(f"  ✗ Unexpected error processing page {page_num}: {e}")
                failed_pages.append(page_num)
                # STOP processing on failure
                logger.error(f"STOPPING: Error on page {page_num} - Book ID {book_id}")
                break

        # Log completion
        logger.info("-"*80)
        logger.info(f"Book {book_id} ({pdf_name}): "
                   f"Processed {total_processed} pages, "
                   f"Successful: {successful}, "
                   f"Failed: {len(failed_pages)}")

        if failed_pages:
            logger.error(f"Failed pages: {failed_pages}")
        else:
            logger.info(f"✓ Book {book_id} completed successfully!")

        logger.info("="*80)

        return total_processed, successful, failed_pages

    def run(self, book_id: Optional[int] = None):
        """
        Main execution method - processes all books or a specific book.

        Args:
            book_id: Optional book ID to process. If None, processes all books.
        """
        logger.info("="*80)
        logger.info("PDF CONTENT TRANSLITERATION PROCESSOR - STARTING")
        logger.info("="*80)
        logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # Test database connection
        if not self.db.test_connection():
            logger.error("Failed to connect to database. Exiting.")
            return

        # Get books to process
        force_reprocess = False  # Track if we should force reprocess
        try:
            if book_id:
                # Process specific book - FORCE REPROCESS ALL PAGES
                logger.info(f"Processing specific book ID: {book_id}")
                book_info = self.db.get_book_by_id(book_id)
                if not book_info:
                    logger.error(f"Book ID {book_id} not found in database")
                    return
                books = [book_info]
                force_reprocess = True  # Force reprocess when specific book_id is given
            else:
                # Process all books
                books = self.get_books_to_process()
        except Exception as e:
            logger.error(f"Failed to get books to process: {e}")
            return

        if not books:
            logger.warning("No books found to process")
            return

        # Process each book
        total_books = len(books)
        books_completed = 0
        books_failed = 0

        for idx, book in enumerate(books, 1):
            current_book_id = book['book_id']
            pdf_name = book['pdf_name']

            logger.info(f"\n[{idx}/{total_books}] Starting book {current_book_id}: {pdf_name}")

            try:
                total_pages, successful_pages, failed_pages = self.process_book(
                    current_book_id, pdf_name, force_reprocess=force_reprocess
                )

                if failed_pages:
                    books_failed += 1
                    logger.error(f"✗ Book {current_book_id} FAILED - stopping processing")
                    # STOP entire process on book failure
                    break
                elif successful_pages > 0:
                    books_completed += 1
                    logger.info(f"✓ Book {current_book_id} COMPLETED - {successful_pages} pages processed")
                else:
                    logger.info(f"○ Book {current_book_id} SKIPPED - no pages to process")

            except Exception as e:
                logger.error(f"✗ Book {current_book_id} FAILED with exception: {e}")
                books_failed += 1
                # STOP entire process on book failure
                break

        # Final summary
        logger.info("")
        logger.info("="*80)
        logger.info("PROCESSING SUMMARY")
        logger.info("="*80)
        logger.info(f"Total books in queue: {total_books}")
        logger.info(f"Books completed: {books_completed}")
        logger.info(f"Books failed: {books_failed}")
        logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)


def main():
    """
    Main entry point for the script.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='Process PDF files to extract and fix Sanskrit transliteration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all books with default settings (full page, auto-detect columns)
  python transliteration_processor.py

  # Process specific book (full page by default)
  python transliteration_processor.py --book-id 3

  # Process specific book, exclude header/footer, enable natural reading order
  python transliteration_processor.py --book-id 3 --full-page no --sort true

  # Process specific book with auto-detection of multi-column layout
  python transliteration_processor.py --book-id 5 --sort auto

  # Custom PDF folder
  python transliteration_processor.py --pdf-folder /path/to/pdfs

Note:
  - Default full-page: yes (includes header/footer; use --full-page no to exclude)
  - Default sort: auto (auto-detects multi-column layouts and enables natural reading order)
  - When --book-id is specified, ALL pages for that book will be reprocessed
        """
    )

    parser.add_argument(
        '--book-id',
        type=int,
        help='Process specific book ID only (reprocesses all pages)'
    )

    parser.add_argument(
        '--full-page',
        choices=['yes', 'no'],
        default='yes',
        help='Include header/footer? yes=full page, no=body only (default: yes)'
    )

    parser.add_argument(
        '--sort',
        choices=['true', 'false', 'auto'],
        default='auto',
        help='Text extraction order: true=natural reading order, false=PDF order, auto=detect (default: auto)'
    )

    parser.add_argument(
        '--pdf-folder',
        default='/opt/pbb_static_content/pbb_pdf_files/',
        help='Path to PDF files folder (default: /opt/pbb_static_content/pbb_pdf_files/)'
    )

    args = parser.parse_args()

    # Convert string arguments to boolean
    full_page = args.full_page == 'yes'
    if args.sort == 'auto':
        sort_mode = 'auto'
    else:
        sort_mode = args.sort == 'true'

    # Create and run processor
    processor = PDFContentTransliterationProcessor(
        pdf_folder=args.pdf_folder,
        full_page=full_page,
        sort_mode=sort_mode
    )
    processor.run(book_id=args.book_id)


if __name__ == "__main__":
    main()
