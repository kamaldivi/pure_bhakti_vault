"""
Extract Book Sections Utility

Extracts TOC, verse, and glossary pages from PDFs based on database metadata.
Creates separate PDFs for each section in organized folders.

Dependencies:
    pip install PyMuPDF psycopg2-binary python-dotenv

Usage:
    python extract_book_sections.py

Environment:
    Requires PDF_FOLDER in .env file
"""

import os
from pathlib import Path
from typing import Optional, Dict, Tuple
import logging
import fitz  # PyMuPDF
from dotenv import load_dotenv
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

# Load environment variables
load_dotenv()


class BookSectionExtractor:
    """
    Extracts specific page ranges (TOC, verse, glossary) from PDFs
    into separate files based on database metadata.
    """

    def __init__(self, pdf_folder: str, db: Optional[PureBhaktiVaultDB] = None):
        """
        Initialize the section extractor.

        Args:
            pdf_folder: Path to folder containing PDF files
            db: Optional PureBhaktiVaultDB instance
        """
        self.pdf_folder = Path(pdf_folder)
        self.db = db or PureBhaktiVaultDB()
        self.logger = self._setup_logger()

        # Create output directories
        self.sfiles_folder = self.pdf_folder / "SFILES"
        self.toc_folder = self.sfiles_folder / "toc"
        self.verse_folder = self.sfiles_folder / "verse"
        self.glossary_folder = self.sfiles_folder / "glossary"

        self._create_output_directories()

        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {pdf_folder}")

    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the extractor."""
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

    def _create_output_directories(self):
        """Create output directory structure."""
        for folder in [self.toc_folder, self.verse_folder, self.glossary_folder]:
            folder.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Output directory ready: {folder}")

    def _extract_pages_to_pdf(
        self,
        source_pdf_path: Path,
        output_pdf_path: Path,
        page_range: Tuple[int, int]
    ) -> bool:
        """
        Extract a range of pages from source PDF to a new PDF.

        Args:
            source_pdf_path: Path to source PDF
            output_pdf_path: Path to output PDF
            page_range: Tuple of (start_page, end_page) inclusive, 1-based

        Returns:
            bool: True if successful, False otherwise
        """
        start_page, end_page = page_range

        try:
            # Open source document
            source_doc = fitz.open(source_pdf_path)

            # Validate page range
            total_pages = len(source_doc)
            if start_page < 1 or end_page > total_pages:
                self.logger.warning(
                    f"Page range [{start_page},{end_page}] out of bounds for "
                    f"{source_pdf_path.name} (total pages: {total_pages})"
                )
                source_doc.close()
                return False

            # Create output document
            output_doc = fitz.open()

            # Extract pages (convert from 1-based to 0-based indexing)
            self.logger.info(
                f"  Extracting pages {start_page}-{end_page} "
                f"({end_page - start_page + 1} pages)"
            )

            for page_num in range(start_page - 1, end_page):
                output_doc.insert_pdf(
                    source_doc,
                    from_page=page_num,
                    to_page=page_num
                )

            # Save output
            output_doc.save(str(output_pdf_path))
            output_doc.close()
            source_doc.close()

            self.logger.info(f"  ✓ Saved to: {output_pdf_path.name}")
            return True

        except Exception as e:
            self.logger.error(f"  ✗ Error extracting pages: {e}")
            return False

    def _process_pdf(self, pdf_path: Path) -> Dict[str, int]:
        """
        Process a single PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            dict: Statistics with counts of extracted sections
        """
        stats = {'toc': 0, 'verse': 0, 'glossary': 0, 'skipped': 0}

        pdf_name = pdf_path.name
        self.logger.info(f"\nProcessing: {pdf_name}")

        # Get book_id from database
        book_id = self.db.get_book_id_by_pdf_name(pdf_name)
        if book_id is None:
            self.logger.warning(f"  Book not found in database: {pdf_name}")
            stats['skipped'] = 1
            return stats

        self.logger.info(f"  Book ID: {book_id}")

        # Get page ranges from database
        toc_pages = self.db.get_toc_pages(book_id)
        verse_pages = self.db.get_verse_pages(book_id)
        glossary_pages = self.db.get_glossary_pages(book_id)

        # Extract TOC pages
        if toc_pages:
            self.logger.info(f"  TOC pages: {toc_pages}")
            output_path = self.toc_folder / f"{book_id}.pdf"
            if self._extract_pages_to_pdf(pdf_path, output_path, toc_pages):
                stats['toc'] = 1
        else:
            self.logger.info("  TOC pages: NULL (skipping)")

        # Extract verse pages
        if verse_pages:
            self.logger.info(f"  Verse pages: {verse_pages}")
            output_path = self.verse_folder / f"{book_id}.pdf"
            if self._extract_pages_to_pdf(pdf_path, output_path, verse_pages):
                stats['verse'] = 1
        else:
            self.logger.info("  Verse pages: NULL (skipping)")

        # Extract glossary pages
        if glossary_pages:
            self.logger.info(f"  Glossary pages: {glossary_pages}")
            output_path = self.glossary_folder / f"{book_id}.pdf"
            if self._extract_pages_to_pdf(pdf_path, output_path, glossary_pages):
                stats['glossary'] = 1
        else:
            self.logger.info("  Glossary pages: NULL (skipping)")

        return stats

    def process_all_pdfs(self) -> Dict[str, int]:
        """
        Process all PDF files in the PDF_FOLDER.

        Returns:
            dict: Overall statistics
        """
        # Find all PDF files
        pdf_files = sorted(self.pdf_folder.glob("*.pdf"))

        if not pdf_files:
            self.logger.warning(f"No PDF files found in {self.pdf_folder}")
            return {}

        self.logger.info(f"Found {len(pdf_files)} PDF files to process")
        self.logger.info("=" * 70)

        # Overall statistics
        total_stats = {
            'processed': 0,
            'skipped': 0,
            'toc_extracted': 0,
            'verse_extracted': 0,
            'glossary_extracted': 0
        }

        # Process each PDF
        for pdf_path in pdf_files:
            try:
                stats = self._process_pdf(pdf_path)
                total_stats['processed'] += 1
                total_stats['skipped'] += stats['skipped']
                total_stats['toc_extracted'] += stats['toc']
                total_stats['verse_extracted'] += stats['verse']
                total_stats['glossary_extracted'] += stats['glossary']

            except Exception as e:
                self.logger.error(f"Error processing {pdf_path.name}: {e}")
                total_stats['skipped'] += 1

        # Print summary
        self.logger.info("\n" + "=" * 70)
        self.logger.info("SUMMARY:")
        self.logger.info(f"  Total PDFs processed: {total_stats['processed']}")
        self.logger.info(f"  Skipped (not in DB):  {total_stats['skipped']}")
        self.logger.info(f"  TOC sections:         {total_stats['toc_extracted']}")
        self.logger.info(f"  Verse sections:       {total_stats['verse_extracted']}")
        self.logger.info(f"  Glossary sections:    {total_stats['glossary_extracted']}")
        self.logger.info("=" * 70)

        return total_stats


def main():
    """Main function to run the section extractor."""

    # Get PDF folder from environment
    pdf_folder = os.getenv("PDF_FOLDER")
    if not pdf_folder:
        raise RuntimeError("PDF_FOLDER not set in .env file")

    # Initialize extractor
    extractor = BookSectionExtractor(pdf_folder=pdf_folder)

    # Test database connection
    if not extractor.db.test_connection():
        print("❌ Failed to connect to database. Check your .env file.")
        return

    # Process all PDFs
    extractor.process_all_pdfs()


if __name__ == "__main__":
    main()
