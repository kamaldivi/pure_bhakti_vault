#!/usr/bin/env python3
"""
PDF to HTML Generator Utility

Converts PDF pages to HTML format with extracted text and images.
Creates a folder structure for each book with individual HTML files per page.

Workflow:
    1. Read PDF_FOLDER (.env config) and loop through all PDFs
    2. Using PDF name, find the book_id from database
    3. For each page: extract text, images, and layout information
    4. Generate semantic HTML with embedded or referenced images
    5. Write to PROCESS_FOLDER/html/book_id/page_number.html

Features:
    - Simple semantic HTML layout (p tags for text blocks)
    - Image extraction with smart embedding (base64 for small, files for large)
    - UTF-8 encoding with support for Sanskrit/IAST text
    - Metadata embedded in HTML (book_id, page_number, page_label)
    - Command-line options: --dry-run, --book-ids, --overwrite

Output Structure:
    PROCESS_FOLDER/html/
    ├── 121/
    │   ├── 1.html
    │   ├── 2.html
    │   └── img/
    │       ├── page_1_img_0.jpg
    │       └── page_2_img_0.png

Dependencies:
    pip install PyMuPDF python-dotenv Pillow

Usage:
    # Dry-run mode (no files written)
    python src/prod_utils/pdf_to_html_generator.py --dry-run

    # Process all PDFs
    python src/prod_utils/pdf_to_html_generator.py

    # Process specific books
    python src/prod_utils/pdf_to_html_generator.py --book-ids 121,122,123

    # Overwrite existing HTML
    python src/prod_utils/pdf_to_html_generator.py --overwrite

Environment:
    Requires PDF_FOLDER and PROCESS_FOLDER in .env file
"""

import os
import sys
import argparse
import base64
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
import logging
from datetime import datetime
from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv
from tqdm import tqdm

# Import database utilities
try:
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
except ImportError:
    print("Error: Cannot import pure_bhakti_vault_db. Ensure it's in the Python path.")
    sys.exit(1)

# Load environment variables
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PDFToHTMLGenerator:
    """
    Converts PDF pages to HTML format with extracted text and images.
    """

    # Image size threshold for base64 embedding (50KB)
    IMAGE_EMBED_THRESHOLD = 50 * 1024

    def __init__(
        self,
        pdf_folder: str,
        output_folder: str,
        db: Optional[PureBhaktiVaultDB] = None,
        dry_run: bool = False,
        overwrite: bool = False,
        book_ids_filter: Optional[List[int]] = None
    ):
        """
        Initialize the PDF to HTML generator.

        Args:
            pdf_folder: Path to folder containing PDF files
            output_folder: Path to PROCESS_FOLDER for HTML output
            db: Optional database instance
            dry_run: If True, don't write any files
            overwrite: If True, regenerate existing HTML
            book_ids_filter: Optional list of book IDs to process
        """
        self.pdf_folder = Path(pdf_folder)
        self.output_folder = Path(output_folder) / "html"
        self.db = db or PureBhaktiVaultDB()
        self.dry_run = dry_run
        self.overwrite = overwrite
        self.book_ids_filter = book_ids_filter

        # Statistics
        self.stats = {
            'pdfs_found': 0,
            'pdfs_processed': 0,
            'pdfs_skipped': 0,
            'pages_converted': 0,
            'images_extracted': 0,
            'images_embedded': 0,
            'errors': 0
        }

        # Validate folders
        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {pdf_folder}")

        if not self.dry_run:
            self.output_folder.mkdir(parents=True, exist_ok=True)

    def _get_book_id_by_pdf_name(self, pdf_name: str) -> Optional[int]:
        """
        Get book_id from database using PDF filename.

        Args:
            pdf_name: PDF filename

        Returns:
            book_id or None if not found
        """
        query = "SELECT book_id FROM book WHERE pdf_name = %s"
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (pdf_name,))
                result = cursor.fetchone()
                return result['book_id'] if result else None
        except Exception as e:
            logger.error(f"Error querying book_id for {pdf_name}: {e}")
            return None

    def _get_page_label(self, book_id: int, page_number: int) -> str:
        """
        Get page_label from page_map table.

        Args:
            book_id: Book ID
            page_number: Page number

        Returns:
            page_label or str(page_number) if not found
        """
        query = """
            SELECT page_label FROM page_map
            WHERE book_id = %s AND page_number = %s
        """
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id, page_number))
                result = cursor.fetchone()
                if result and result['page_label']:
                    return result['page_label']
                return str(page_number)
        except Exception as e:
            logger.warning(f"Error getting page_label for book {book_id}, page {page_number}: {e}")
            return str(page_number)

    def _extract_images_from_page(
        self,
        page: fitz.Page,
        book_id: int,
        page_number: int,
        img_folder: Path,
        image_hashes: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Extract unique images from a PDF page (skips duplicates).

        Args:
            page: PyMuPDF page object
            book_id: Book ID
            page_number: Page number
            img_folder: Path to image output folder
            image_hashes: Set of image hashes to track duplicates

        Returns:
            List of image dictionaries with 'html' key (either <img> tag or data URI)
        """
        images = []
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # Calculate hash to detect duplicates
                img_hash = hashlib.md5(image_bytes).hexdigest()

                # Skip if we've already seen this image
                if img_hash in image_hashes:
                    continue

                # Add to seen images
                image_hashes.add(img_hash)

                # Determine if we should embed or save to file
                if len(image_bytes) < self.IMAGE_EMBED_THRESHOLD:
                    # Embed as base64
                    base64_data = base64.b64encode(image_bytes).decode('utf-8')
                    mime_type = f"image/{image_ext}"
                    img_html = f'<img src="data:{mime_type};base64,{base64_data}" alt="Image {img_index}" class="page-image">'
                    images.append({
                        'html': img_html,
                        'embedded': True,
                        'size': len(image_bytes)
                    })
                    self.stats['images_embedded'] += 1
                else:
                    # Save to file with unique name based on hash
                    img_filename = f"{img_hash[:16]}.{image_ext}"
                    img_path = img_folder / img_filename

                    if not self.dry_run:
                        # Only write if file doesn't exist
                        if not img_path.exists():
                            with open(img_path, 'wb') as img_file:
                                img_file.write(image_bytes)

                    img_html = f'<img src="img/{img_filename}" alt="Image {img_index}" class="page-image">'
                    images.append({
                        'html': img_html,
                        'embedded': False,
                        'size': len(image_bytes),
                        'path': img_path
                    })

                self.stats['images_extracted'] += 1

            except Exception as e:
                logger.warning(f"Failed to extract image {img_index} from page {page_number}: {e}")
                continue

        return images

    def _extract_formatted_content(self, page: fitz.Page) -> str:
        """
        Extract text from page with formatting preserved (headings, bold, italic).

        Args:
            page: PyMuPDF page object

        Returns:
            HTML content string with proper formatting
        """
        # Get text with detailed formatting information
        text_dict = page.get_text("dict")
        html_content = []

        for block in text_dict.get('blocks', []):
            # Skip image blocks
            if block.get('type') != 0:
                continue

            block_html = []

            for line in block.get('lines', []):
                line_html = []
                line_styles = set()

                for span in line.get('spans', []):
                    text = span.get('text', '').strip()
                    if not text:
                        continue

                    font_size = span.get('size', 11)
                    font_name = span.get('font', '')
                    flags = span.get('flags', 0)

                    # Detect styling from font flags
                    # flags: bit 0 = superscript, bit 1 = italic, bit 2 = serifed, bit 3 = monospaced, bit 4 = bold
                    is_bold = (flags & 16) != 0 or 'Bold' in font_name
                    is_italic = (flags & 2) != 0 or 'Italic' in font_name

                    # Detect headings by font size
                    if font_size > 14:
                        line_styles.add('h1')
                    elif font_size > 12:
                        line_styles.add('h2')

                    # Apply inline styling
                    if is_bold and is_italic:
                        text = f'<strong><em>{text}</em></strong>'
                    elif is_bold:
                        text = f'<strong>{text}</strong>'
                    elif is_italic:
                        text = f'<em>{text}</em>'

                    line_html.append(text)

                if line_html:
                    line_text = ' '.join(line_html)

                    # Wrap in appropriate tag based on detected style
                    if 'h1' in line_styles:
                        block_html.append(f'<h1>{line_text}</h1>')
                    elif 'h2' in line_styles:
                        block_html.append(f'<h2>{line_text}</h2>')
                    else:
                        block_html.append(line_text)

            # Join lines in block and wrap in paragraph if not heading
            if block_html:
                # Check if block contains headings
                has_heading = any('<h1>' in line or '<h2>' in line for line in block_html)

                if has_heading:
                    # Don't wrap headings in <p>
                    html_content.extend(block_html)
                else:
                    # Join lines and wrap in <p>
                    paragraph_text = '<br>'.join(block_html)
                    html_content.append(f'<p>{paragraph_text}</p>')

        return '\n'.join(html_content)

    def _generate_html(
        self,
        book_id: int,
        page_number: int,
        page_label: str,
        formatted_content: str,
        images: List[Dict[str, Any]],
        book_title: str = ""
    ) -> str:
        """
        Generate HTML for a single page.

        Args:
            book_id: Book ID
            page_number: Page number
            page_label: Page label
            formatted_content: Formatted HTML content
            images: List of image dictionaries
            book_title: Optional book title

        Returns:
            Complete HTML string
        """
        # Build image HTML
        images_html = "\n".join([img['html'] for img in images])

        # Generate HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="book-id" content="{book_id}">
    <meta name="page-number" content="{page_number}">
    <meta name="page-label" content="{page_label}">
    <title>{book_title} - Page {page_label}</title>
    <style>
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #f9f9f9;
        }}
        .page-container {{
            background-color: white;
            padding: 40px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            font-size: 1.8em;
            margin: 0.5em 0;
            color: #2c3e50;
            font-weight: bold;
        }}
        h2 {{
            font-size: 1.4em;
            margin: 0.5em 0;
            color: #34495e;
            font-weight: bold;
        }}
        p {{
            margin: 1em 0;
            text-align: justify;
            line-height: 1.8;
        }}
        strong {{
            font-weight: bold;
        }}
        em {{
            font-style: italic;
        }}
        .page-image {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }}
        .images-section {{
            margin: 30px 0;
        }}
        .content-section {{
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="page-container">
        <div class="content-section">
{formatted_content}
        </div>

        <div class="images-section">
{images_html}
        </div>
    </div>
</body>
</html>
"""
        return html

    def _convert_page_to_html(
        self,
        doc: fitz.Document,
        page_num: int,
        book_id: int,
        book_title: str,
        output_dir: Path,
        image_hashes: set
    ) -> bool:
        """
        Convert a single PDF page to HTML.

        Args:
            doc: PyMuPDF document
            page_num: Page number (0-indexed)
            book_id: Book ID
            book_title: Book title
            output_dir: Output directory for this book
            image_hashes: Set of image hashes to track duplicates

        Returns:
            True if successful
        """
        try:
            page = doc[page_num]
            page_number = page_num + 1  # Convert to 1-indexed

            # Get page label from database
            page_label = self._get_page_label(book_id, page_number)

            # Create image folder
            img_folder = output_dir / "img"
            if not self.dry_run:
                img_folder.mkdir(exist_ok=True)

            # Extract images (with deduplication)
            images = self._extract_images_from_page(page, book_id, page_number, img_folder, image_hashes)

            # Extract formatted content
            formatted_content = self._extract_formatted_content(page)

            # Generate HTML
            html_content = self._generate_html(
                book_id=book_id,
                page_number=page_number,
                page_label=page_label,
                formatted_content=formatted_content,
                images=images,
                book_title=book_title
            )

            # Write HTML file
            html_filename = f"{page_number}.html"
            html_path = output_dir / html_filename

            if not self.dry_run:
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

            self.stats['pages_converted'] += 1
            return True

        except Exception as e:
            logger.error(f"Error converting page {page_num + 1}: {e}")
            self.stats['errors'] += 1
            return False

    def _process_pdf(self, pdf_path: Path) -> bool:
        """
        Process a single PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if successful
        """
        pdf_name = pdf_path.name
        logger.info(f"\nProcessing: {pdf_name}")

        # Get book_id from database
        book_id = self._get_book_id_by_pdf_name(pdf_name)
        if not book_id:
            logger.warning(f"  ⚠️  Book not found in database: {pdf_name}")
            self.stats['pdfs_skipped'] += 1
            return False

        # Filter by book_ids if specified
        if self.book_ids_filter and book_id not in self.book_ids_filter:
            logger.info(f"  ⏭️  Skipping book_id={book_id} (not in filter)")
            self.stats['pdfs_skipped'] += 1
            return False

        # Get book title from database
        query = "SELECT original_book_title FROM book WHERE book_id = %s"
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                book_title = result['original_book_title'] if result else f"Book {book_id}"
        except Exception as e:
            logger.warning(f"Error getting book title: {e}")
            book_title = f"Book {book_id}"

        # Create output directory
        output_dir = self.output_folder / str(book_id)

        # Check if already exists
        if not self.overwrite and output_dir.exists():
            logger.info(f"  ⏭️  Skipping book_id={book_id} (HTML already exists, use --overwrite to regenerate)")
            self.stats['pdfs_skipped'] += 1
            return False

        if not self.dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)

        # Open PDF
        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            logger.info(f"  📄 Book ID: {book_id}, Pages: {num_pages}")

            # Track image hashes to deduplicate images across pages
            image_hashes = set()

            # Process each page
            for page_num in tqdm(range(num_pages), desc=f"Converting pages for book {book_id}"):
                self._convert_page_to_html(doc, page_num, book_id, book_title, output_dir, image_hashes)

            doc.close()
            self.stats['pdfs_processed'] += 1
            logger.info(f"  ✅ Completed book_id={book_id}: {num_pages} pages converted")
            return True

        except Exception as e:
            logger.error(f"  ❌ Failed to process {pdf_name}: {e}")
            self.stats['errors'] += 1
            return False

    def process_all_pdfs(self) -> Dict[str, int]:
        """
        Process all PDF files in PDF_FOLDER.

        Returns:
            Statistics dictionary
        """
        # Find all PDF files
        pdf_files = sorted(self.pdf_folder.glob("*.pdf"))
        self.stats['pdfs_found'] = len(pdf_files)

        if not pdf_files:
            logger.warning(f"No PDF files found in {self.pdf_folder}")
            return self.stats

        logger.info(f"\n{'='*70}")
        logger.info(f"PDF TO HTML GENERATOR")
        logger.info(f"{'='*70}")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'PRODUCTION'}")
        logger.info(f"PDF Folder: {self.pdf_folder}")
        logger.info(f"Output Folder: {self.output_folder}")
        logger.info(f"Found {len(pdf_files)} PDF files")
        if self.book_ids_filter:
            logger.info(f"Filtering: book_ids={self.book_ids_filter}")
        logger.info(f"{'='*70}\n")

        # Process each PDF
        for pdf_path in pdf_files:
            self._process_pdf(pdf_path)

        # Print summary
        self._print_summary()

        return self.stats

    def _print_summary(self):
        """Print execution summary."""
        logger.info(f"\n{'='*70}")
        logger.info("📊 EXECUTION SUMMARY")
        logger.info(f"{'='*70}")
        logger.info(f"PDFs found: {self.stats['pdfs_found']}")
        logger.info(f"PDFs processed: {self.stats['pdfs_processed']}")
        logger.info(f"PDFs skipped: {self.stats['pdfs_skipped']}")
        logger.info(f"Pages converted: {self.stats['pages_converted']}")
        logger.info(f"Images extracted: {self.stats['images_extracted']}")
        logger.info(f"  - Embedded (base64): {self.stats['images_embedded']}")
        logger.info(f"  - Saved to files: {self.stats['images_extracted'] - self.stats['images_embedded']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"{'='*70}")

        if self.dry_run:
            logger.info("\n🔍 DRY-RUN MODE: No files were written")
        elif self.stats['pdfs_processed'] > 0:
            logger.info(f"\n✅ HTML files written to: {self.output_folder}")
        else:
            logger.info("\n⚠️  No PDFs were processed")


def main():
    """Main function to run the PDF to HTML generator."""
    parser = argparse.ArgumentParser(
        description='Convert PDF pages to HTML format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run mode (no files written)
  python src/prod_utils/pdf_to_html_generator.py --dry-run

  # Process all PDFs
  python src/prod_utils/pdf_to_html_generator.py

  # Process specific books
  python src/prod_utils/pdf_to_html_generator.py --book-ids 121,122,123

  # Overwrite existing HTML
  python src/prod_utils/pdf_to_html_generator.py --overwrite

  # Verbose logging
  python src/prod_utils/pdf_to_html_generator.py --verbose
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validation mode: show what would be done without writing files'
    )
    parser.add_argument(
        '--book-ids',
        type=str,
        help='Comma-separated list of book IDs to process (e.g., "121,122,123")'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Regenerate HTML even if it already exists'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse book_ids filter
    book_ids_filter = None
    if args.book_ids:
        try:
            book_ids_filter = [int(bid.strip()) for bid in args.book_ids.split(',')]
        except ValueError:
            print("❌ Error: --book-ids must be comma-separated integers")
            sys.exit(1)

    # Get folders from environment
    pdf_folder = os.getenv('PDF_FOLDER')
    process_folder = os.getenv('PROCESS_FOLDER')

    if not pdf_folder:
        print("❌ Error: PDF_FOLDER not set in .env file")
        sys.exit(1)

    if not process_folder:
        print("❌ Error: PROCESS_FOLDER not set in .env file")
        sys.exit(1)

    # Initialize generator
    try:
        generator = PDFToHTMLGenerator(
            pdf_folder=pdf_folder,
            output_folder=process_folder,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            book_ids_filter=book_ids_filter
        )

        # Test database connection
        if not generator.db.test_connection():
            print("❌ Failed to connect to database. Check your .env file.")
            sys.exit(1)

        # Process all PDFs
        start_time = datetime.now()
        stats = generator.process_all_pdfs()
        elapsed = datetime.now() - start_time

        logger.info(f"\n⏱️  Elapsed time: {elapsed}")

        if stats['errors'] > 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
