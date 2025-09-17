#!/usr/bin/env python3
"""
PDF Page Renderer - Production-ready script for rendering PDF pages to web-ready images

This script reads (book_id, page_number) pairs from PostgreSQL content table
and renders each page to optimized web-ready images with optional thumbnails.

Requirements:
- Python 3.10+
- PyMuPDF (fitz), psycopg2-binary, python-dotenv, tqdm, pillow, click
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import click
import fitz  # PyMuPDF
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from tqdm import tqdm
from PIL import Image, ImageFilter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('pdf_render.log')
    ]
)
logger = logging.getLogger(__name__)


class PDFPageRenderer:
    """Production-ready PDF page renderer with PostgreSQL integration."""

    def __init__(self,
                 pdf_folder: str,
                 page_folder: str,
                 db_config: dict,
                 dpi: int = 150,
                 image_format: str = 'webp',
                 grayscale: bool = True,
                 create_thumbnails: bool = False,
                 thumb_size: Tuple[int, int] = (300, 400),
                 max_workers: int = 4,
                 restart_book_id: Optional[int] = None,
                 cleanup_partial: bool = True):
        """
        Initialize the PDF page renderer.

        Args:
            pdf_folder: Path to folder containing PDF files
            page_folder: Output folder for rendered images
            db_config: Database connection parameters
            dpi: Dots per inch for rendering (default: 150)
            image_format: Output format - 'webp' or 'png' (default: 'webp')
            grayscale: Convert to grayscale for smaller files (default: True)
            create_thumbnails: Generate thumbnail variants (default: False)
            thumb_size: Thumbnail dimensions (width, height)
            max_workers: Number of concurrent rendering threads
            restart_book_id: Skip to this book_id and higher (None = start from beginning)
            cleanup_partial: Clean up partially rendered book folders before starting
        """
        self.pdf_folder = Path(pdf_folder)
        self.page_folder = Path(page_folder)
        self.db_config = db_config
        self.dpi = dpi
        self.image_format = image_format.lower()
        self.grayscale = grayscale
        self.create_thumbnails = create_thumbnails
        self.thumb_size = thumb_size
        self.max_workers = max_workers
        self.restart_book_id = restart_book_id
        self.cleanup_partial = cleanup_partial

        # Validate image format
        if self.image_format not in ['webp', 'png']:
            logger.warning(f"Unsupported format {self.image_format}, falling back to PNG")
            self.image_format = 'png'

        # Test WebP support
        if self.image_format == 'webp' and not self._test_webp_support():
            logger.warning("WebP not supported, falling back to PNG")
            self.image_format = 'png'

        # Ensure output directory exists
        self.page_folder.mkdir(parents=True, exist_ok=True)

        restart_info = f", restart_from_book_id={restart_book_id}" if restart_book_id else ""
        logger.info(f"Initialized renderer: DPI={dpi}, format={self.image_format}, "
                   f"grayscale={grayscale}, thumbnails={create_thumbnails}{restart_info}")

    def _test_webp_support(self) -> bool:
        """Test if PIL supports WebP format."""
        try:
            from PIL import Image
            # Try to create a simple WebP image
            img = Image.new('RGB', (1, 1))
            img.save('/tmp/test.webp', 'WEBP')
            os.remove('/tmp/test.webp')
            return True
        except Exception:
            return False

    def get_database_connection(self) -> psycopg2.extensions.connection:
        """Create database connection with error handling."""
        try:
            conn = psycopg2.connect(**self.db_config)
            return conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def cleanup_partial_books(self, book_ids_to_clean: List[int]) -> None:
        """
        Clean up partially rendered book folders.

        Args:
            book_ids_to_clean: List of book IDs to clean up
        """
        if not book_ids_to_clean:
            return

        logger.info(f"Cleaning up {len(book_ids_to_clean)} partially rendered book folders")

        for book_id in book_ids_to_clean:
            book_folder = self.page_folder / str(book_id)
            if book_folder.exists():
                try:
                    import shutil
                    shutil.rmtree(book_folder)
                    logger.info(f"Cleaned up book folder: {book_folder}")
                except Exception as e:
                    logger.error(f"Failed to clean up book folder {book_folder}: {e}")

    def get_content_pages(self) -> List[Tuple[int, int, str]]:
        """
        Retrieve (book_id, page_number, pdf_name) from content table.
        Applies restart_book_id filtering if configured.

        Returns:
            List of tuples containing (book_id, page_number, pdf_name)
        """
        # Build query with optional WHERE clause for restart
        where_clause = ""
        params = []

        if self.restart_book_id is not None:
            where_clause = "WHERE c.book_id >= %s"
            params = [self.restart_book_id]

        query = f"""
        SELECT
            c.book_id,
            c.page_number,
            b.pdf_name
        FROM content c
        INNER JOIN book b ON c.book_id = b.book_id
        {where_clause}
        ORDER BY c.book_id, c.page_number
        """

        with self.get_database_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                results = cur.fetchall()

        if self.restart_book_id:
            logger.info(f"Found {len(results)} pages to render (starting from book_id >= {self.restart_book_id})")
        else:
            logger.info(f"Found {len(results)} pages to render")

        return [(row['book_id'], row['page_number'], row['pdf_name']) for row in results]

    def get_book_page_counts(self) -> dict:
        """
        Get expected page counts per book from database.

        Returns:
            Dictionary mapping book_id to expected page count
        """
        where_clause = ""
        params = []

        if self.restart_book_id is not None:
            where_clause = "WHERE c.book_id >= %s"
            params = [self.restart_book_id]

        query = f"""
        SELECT
            c.book_id,
            COUNT(*) as expected_pages
        FROM content c
        {where_clause}
        GROUP BY c.book_id
        ORDER BY c.book_id
        """

        with self.get_database_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                results = cur.fetchall()

        return {row['book_id']: row['expected_pages'] for row in results}

    def identify_partial_books(self) -> List[int]:
        """
        Identify books that have been partially rendered.

        Returns:
            List of book_ids that have partial rendering
        """
        if not self.cleanup_partial:
            return []

        expected_counts = self.get_book_page_counts()
        partial_books = []

        for book_id, expected_count in expected_counts.items():
            book_folder = self.page_folder / str(book_id)
            if not book_folder.exists():
                continue

            # Count existing rendered pages (main images only)
            pattern = f"*.{self.image_format}"
            existing_files = list(book_folder.glob(pattern))

            # Filter out thumbnail files
            main_files = [f for f in existing_files if not f.stem.endswith('_thumb')]
            actual_count = len(main_files)

            if 0 < actual_count < expected_count:
                partial_books.append(book_id)
                logger.info(f"Book {book_id}: {actual_count}/{expected_count} pages rendered (partial)")

        return partial_books

    def get_output_path(self, book_id: int, page_number: int, is_thumbnail: bool = False) -> Path:
        """Generate output file path for rendered page."""
        book_folder = self.page_folder / str(book_id)
        book_folder.mkdir(parents=True, exist_ok=True)

        suffix = f"_thumb.{self.image_format}" if is_thumbnail else f".{self.image_format}"
        return book_folder / f"{page_number}{suffix}"

    def render_page(self, pdf_path: Path, page_number: int, output_path: Path) -> bool:
        """
        Render a single PDF page to image.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number to render (1-indexed)
            output_path: Output image path

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if output already exists (idempotent)
            if output_path.exists():
                logger.debug(f"Skipping existing file: {output_path}")
                return True

            # Open PDF
            doc = fitz.open(pdf_path)

            # Validate page number
            if page_number < 1 or page_number > len(doc):
                logger.error(f"Invalid page number {page_number} for {pdf_path.name}")
                doc.close()
                return False

            # Get page (0-indexed in PyMuPDF)
            page = doc[page_number - 1]

            # Calculate matrix for desired DPI
            zoom = self.dpi / 72.0  # 72 DPI is default
            matrix = fitz.Matrix(zoom, zoom)

            # Render page to pixmap
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Convert to PIL Image for processing
            img_data = pix.tobytes("ppm")
            img = Image.open(BytesIO(img_data))

            # Convert to grayscale if requested
            if self.grayscale:
                img = img.convert('L')

            # Save with optimization
            save_kwargs = {
                'optimize': True,
                'quality': 85 if self.image_format == 'webp' else None
            }

            if self.image_format == 'webp':
                save_kwargs['method'] = 6  # Better compression
                save_kwargs['lossless'] = False

            img.save(output_path, self.image_format.upper(), **save_kwargs)

            # Cleanup
            pix = None
            doc.close()

            logger.debug(f"Rendered: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to render {pdf_path}:{page_number} - {e}")
            return False

    def create_thumbnail(self, source_path: Path, thumb_path: Path) -> bool:
        """
        Create thumbnail from rendered page.

        Args:
            source_path: Path to full-size image
            thumb_path: Output thumbnail path

        Returns:
            True if successful, False otherwise
        """
        try:
            if thumb_path.exists():
                logger.debug(f"Skipping existing thumbnail: {thumb_path}")
                return True

            with Image.open(source_path) as img:
                # Maintain aspect ratio while fitting within thumb_size
                img.thumbnail(self.thumb_size, Image.Resampling.LANCZOS)

                # Apply slight sharpening for small images
                if img.size[0] < 400:
                    img = img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=150, threshold=3))

                # Save thumbnail
                save_kwargs = {
                    'optimize': True,
                    'quality': 75 if self.image_format == 'webp' else None
                }

                if self.image_format == 'webp':
                    save_kwargs['method'] = 4
                    save_kwargs['lossless'] = False

                img.save(thumb_path, self.image_format.upper(), **save_kwargs)

            logger.debug(f"Created thumbnail: {thumb_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to create thumbnail {thumb_path} - {e}")
            return False

    def render_single_page_task(self, task: Tuple[int, int, str]) -> Tuple[bool, bool]:
        """
        Render a single page task (for use with ThreadPoolExecutor).

        Args:
            task: Tuple of (book_id, page_number, pdf_name)

        Returns:
            Tuple of (main_success, thumb_success)
        """
        book_id, page_number, pdf_name = task

        # Construct PDF path
        pdf_path = self.pdf_folder / pdf_name
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return False, False

        # Generate output paths
        output_path = self.get_output_path(book_id, page_number)
        thumb_path = self.get_output_path(book_id, page_number, is_thumbnail=True)

        # Render main image
        main_success = self.render_page(pdf_path, page_number, output_path)

        # Create thumbnail if requested and main render succeeded
        thumb_success = True  # Default to success if not creating thumbnails
        if self.create_thumbnails and main_success:
            thumb_success = self.create_thumbnail(output_path, thumb_path)

        return main_success, thumb_success

    def render_all_pages(self) -> dict:
        """
        Render all pages from the content table.
        Handles restart logic and partial book cleanup.

        Returns:
            Dictionary with rendering statistics
        """
        # Step 1: Identify and clean up partial books if requested
        if self.cleanup_partial:
            partial_books = self.identify_partial_books()
            if partial_books:
                logger.warning(f"Found {len(partial_books)} partially rendered books: {partial_books}")
                self.cleanup_partial_books(partial_books)
            else:
                logger.info("No partially rendered books found")

        # Step 2: Get pages to render
        pages = self.get_content_pages()

        if not pages:
            logger.warning("No pages found to render")
            return {'total': 0, 'success': 0, 'failed': 0, 'thumb_success': 0, 'thumb_failed': 0}

        # Step 3: Log restart information
        if self.restart_book_id:
            first_book = min(pages, key=lambda x: x[0])[0]
            last_book = max(pages, key=lambda x: x[0])[0]
            logger.info(f"Restart mode: Processing books {first_book} to {last_book}")

        # Statistics counters
        stats = {
            'total': len(pages),
            'success': 0,
            'failed': 0,
            'thumb_success': 0,
            'thumb_failed': 0,
            'books_processed': set()
        }

        logger.info(f"Starting to render {stats['total']} pages using {self.max_workers} workers")

        # Use ThreadPoolExecutor for concurrent rendering
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {executor.submit(self.render_single_page_task, task): task
                             for task in pages}

            # Process completed tasks with progress bar
            with tqdm(total=len(pages), desc="Rendering pages") as pbar:
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    book_id, page_number, pdf_name = task

                    try:
                        main_success, thumb_success = future.result()

                        # Track books processed
                        stats['books_processed'].add(book_id)

                        if main_success:
                            stats['success'] += 1
                        else:
                            stats['failed'] += 1
                            logger.error(f"Failed to render {pdf_name}:{page_number}")

                        if self.create_thumbnails:
                            if thumb_success:
                                stats['thumb_success'] += 1
                            else:
                                stats['thumb_failed'] += 1

                    except Exception as e:
                        stats['failed'] += 1
                        stats['books_processed'].add(book_id)  # Track even failed attempts
                        logger.error(f"Task failed for {pdf_name}:{page_number} - {e}")

                    pbar.update(1)

        # Log final statistics
        books_count = len(stats['books_processed'])
        logger.info(f"Rendering complete: {stats['success']}/{stats['total']} pages successful across {books_count} books")
        if self.create_thumbnails:
            logger.info(f"Thumbnails: {stats['thumb_success']}/{stats['total']} successful")

        if stats['books_processed']:
            min_book = min(stats['books_processed'])
            max_book = max(stats['books_processed'])
            logger.info(f"Books processed: {min_book} to {max_book}")

        return stats


# Import BytesIO here to avoid circular imports
from io import BytesIO


@click.command()
@click.option('--dpi', default=None, type=int, help='DPI for rendering (default: 150 or from .env)')
@click.option('--format', 'image_format', default=None, type=click.Choice(['webp', 'png']),
              help='Output image format (default: webp or from .env)')
@click.option('--color/--grayscale', default=None, help='Output in color or grayscale (default: grayscale)')
@click.option('--thumbnails/--no-thumbnails', default=None, help='Create thumbnail variants')
@click.option('--thumb-width', default=300, type=int, help='Thumbnail width (default: 300)')
@click.option('--thumb-height', default=400, type=int, help='Thumbnail height (default: 400)')
@click.option('--workers', default=4, type=int, help='Number of concurrent workers (default: 4)')
@click.option('--restart-book-id', type=int, help='Restart from this book_id and higher (overrides .env)')
@click.option('--cleanup/--no-cleanup', default=None, help='Clean up partially rendered books (default: true)')
@click.option('--env-file', default='.env', help='Path to environment file (default: .env)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(dpi, image_format, color, thumbnails, thumb_width, thumb_height, workers, restart_book_id, cleanup, env_file, verbose):
    """
    Render PDF pages to web-ready images based on PostgreSQL content table.

    This script reads (book_id, page_number) pairs from the content table,
    locates the corresponding PDF files, and renders each page to optimized
    web-ready images. Supports WebP and PNG formats with optional thumbnails.

    Restart Support:
    - Use --restart-book-id N to resume from book N onwards
    - Use --cleanup to remove partially rendered books before starting
    - Configure RESTART_BOOK_ID in .env for persistent restart point
    """

    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    load_dotenv(env_file)

    # Get configuration from environment with CLI overrides
    pdf_folder = os.getenv('PDF_FOLDER')
    page_folder = os.getenv('PAGE_FOLDER')

    if not pdf_folder or not page_folder:
        logger.error("PDF_FOLDER and PAGE_FOLDER must be set in .env file")
        sys.exit(1)

    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'pure_bhakti_vault'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

    if not all([db_config['user'], db_config['password']]):
        logger.error("Database credentials (DB_USER, DB_PASSWORD) must be set in .env file")
        sys.exit(1)

    # Rendering configuration with CLI overrides
    render_dpi = dpi or int(os.getenv('RENDER_DPI', 150))
    render_format = image_format or os.getenv('RENDER_FORMAT', 'webp')
    render_grayscale = not color if color is not None else os.getenv('RENDER_GRAYSCALE', 'true').lower() == 'true'
    create_thumbs = thumbnails if thumbnails is not None else os.getenv('CREATE_THUMBNAILS', 'false').lower() == 'true'

    # Restart and cleanup configuration
    restart_from_book = restart_book_id or (int(os.getenv('RESTART_BOOK_ID')) if os.getenv('RESTART_BOOK_ID') else None)
    cleanup_partial = cleanup if cleanup is not None else os.getenv('CLEANUP_PARTIAL', 'true').lower() == 'true'

    logger.info(f"Configuration: PDF={pdf_folder}, Pages={page_folder}, DPI={render_dpi}")
    logger.info(f"Format={render_format}, Grayscale={render_grayscale}, Thumbnails={create_thumbs}")
    if restart_from_book:
        logger.info(f"Restart mode: Starting from book_id >= {restart_from_book}")
    if cleanup_partial:
        logger.info("Partial book cleanup: Enabled")

    try:
        # Initialize renderer
        renderer = PDFPageRenderer(
            pdf_folder=pdf_folder,
            page_folder=page_folder,
            db_config=db_config,
            dpi=render_dpi,
            image_format=render_format,
            grayscale=render_grayscale,
            create_thumbnails=create_thumbs,
            thumb_size=(thumb_width, thumb_height),
            max_workers=workers,
            restart_book_id=restart_from_book,
            cleanup_partial=cleanup_partial
        )

        # Render all pages
        stats = renderer.render_all_pages()

        # Print summary
        click.echo(f"\n=== Rendering Summary ===")
        click.echo(f"Total pages: {stats['total']}")
        click.echo(f"Successful: {stats['success']}")
        click.echo(f"Failed: {stats['failed']}")
        click.echo(f"Books processed: {len(stats['books_processed'])}")

        if create_thumbs:
            click.echo(f"Thumbnails successful: {stats['thumb_success']}")
            click.echo(f"Thumbnails failed: {stats['thumb_failed']}")

        success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
        click.echo(f"Success rate: {success_rate:.1f}%")

        # Show next restart book_id if there were failures
        if stats['failed'] > 0 and stats['books_processed']:
            max_processed = max(stats['books_processed'])
            click.echo(f"\nTo restart from failures, use: --restart-book-id {max_processed}")
            click.echo(f"Or add to .env: RESTART_BOOK_ID={max_processed}")

        if stats['failed'] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Rendering interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()