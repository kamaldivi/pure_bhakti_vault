"""
Page Content Extractor Utility

A reusable utility for extracting clean page content from PDFs by excluding
headers and footers based on database-stored dimensions.

Dependencies:
    pip install psycopg2-binary python-dotenv PyMuPDF

Usage:
    from page_content_extractor import PageContentExtractor
    
    extractor = PageContentExtractor()
    content = extractor.extract_page_content("sample_book.pdf", 25)
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from enum import Enum
import fitz  # PyMuPDF
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
from sanskrit_utils import fix_iast_glyphs


class ExtractionType(Enum):
    """Types of content extraction supported."""
    BODY = "body"
    HEADER = "header"  
    FOOTER = "footer"


class ContentExtractionError(Exception):
    """Custom exception for content extraction related errors"""
    pass


class PageContentExtractor:
    """
    Utility for extracting clean page content from PDFs, excluding headers and footers.
    
    This class integrates with the Pure Bhakti Vault database to retrieve book metadata
    and uses stored header/footer heights to extract only the main content area.
    """
    
    def __init__(self, pdf_folder_path: Optional[str] = None, db_connection_params: Optional[Dict[str, str]] = None):
        """
        Initialize the content extractor.
        
        Args:
            pdf_folder_path: Path to folder containing PDF files. 
                           If None, uses PDF_FOLDER from environment variables.
            db_connection_params: Optional database connection parameters.
                                If None, uses environment variables.
        """
        self.pdf_folder_path = pdf_folder_path or os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/Gurudev_Books/')
        self.db = PureBhaktiVaultDB(connection_params=db_connection_params)
        self.logger = self._setup_logger()
        
        # Validate PDF folder path
        if not os.path.exists(self.pdf_folder_path):
            raise ContentExtractionError(f"PDF folder path does not exist: {self.pdf_folder_path}")
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the content extractor."""
        logger = logging.getLogger(f"{__name__}.PageContentExtractor")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _get_pdf_path(self, pdf_name: str) -> str:
        """
        Get the full path to the PDF file.
        
        Args:
            pdf_name: Name of the PDF file
            
        Returns:
            str: Full path to the PDF file
            
        Raises:
            ContentExtractionError: If PDF file is not found
        """
        pdf_path = os.path.join(self.pdf_folder_path, pdf_name)
        
        if not os.path.exists(pdf_path):
            raise ContentExtractionError(f"PDF file not found: {pdf_path}")
        
        return pdf_path
    
    def _extract_content_region(self, page: fitz.Page, header_height: float, footer_height: float) -> str:
        """
        Extract text content from the main content area, excluding header and footer.
        
        Args:
            page: PyMuPDF page object
            header_height: Height of header region in PDF points (from top)
            footer_height: Height of footer region in PDF points (from bottom)
            
        Returns:
            str: Extracted text content from the main area
        """
        try:
            page_rect = page.rect
            
            # Calculate main content area coordinates
            # Note: PDF coordinate system has (0,0) at bottom-left, but PyMuPDF uses top-left
            content_x0 = page_rect.x0
            content_y0 = page_rect.y0 + header_height  # Start below header
            content_x1 = page_rect.x1
            content_y1 = footer_height  # End at footer start coordinate
            
            # Ensure we have a valid content area
            if content_y0 >= content_y1:
                self.logger.warning(f"Invalid content area: header_height={header_height}, footer_height={footer_height}, page_height={page_rect.height}")
                return ""
            
            # Create rectangle for main content area
            content_rect = fitz.Rect(content_x0, content_y0, content_x1, content_y1)
            
            # Extract text from the content area
            content_text = page.get_text("text", clip=content_rect).strip()
            
            return content_text
            
        except Exception as e:
            self.logger.error(f"Error extracting content region: {e}")
            return ""

    def _extract_header_region(self, page: fitz.Page, header_height: float) -> str:
        """
        Extract text content from the header region.
        
        Args:
            page: PyMuPDF page object
            header_height: Height of header region in PDF points (from top)
            
        Returns:
            str: Extracted text content from the header area
        """
        try:
            if header_height <= 0:
                return ""
                
            page_rect = page.rect
            
            # Calculate header area coordinates
            header_x0 = page_rect.x0
            header_y0 = page_rect.y0  # Start from top
            header_x1 = page_rect.x1
            header_y1 = page_rect.y0 + header_height  # End at header height
            
            # Create rectangle for header area
            header_rect = fitz.Rect(header_x0, header_y0, header_x1, header_y1)
            
            # Extract text from the header area
            header_text = page.get_text("text", clip=header_rect).strip()
            
            return header_text
            
        except Exception as e:
            self.logger.error(f"Error extracting header region: {e}")
            return ""

    def _extract_footer_region(self, page: fitz.Page, footer_height: float) -> str:
        """
        Extract text content from the footer region.
        
        Args:
            page: PyMuPDF page object
            footer_height: Y-coordinate where footer starts (from top of page)
            
        Returns:
            str: Extracted text content from the footer area
        """
        try:
            page_rect = page.rect
            
            if footer_height <= 0 or footer_height >= page_rect.height:
                return ""
                
            # Calculate footer area coordinates
            footer_x0 = page_rect.x0
            footer_y0 = footer_height  # Start at footer Y coordinate
            footer_x1 = page_rect.x1
            footer_y1 = page_rect.y1  # End at bottom of page
            
            # Ensure we have a valid footer area
            if footer_y0 >= footer_y1:
                return ""
                
            # Create rectangle for footer area
            footer_rect = fitz.Rect(footer_x0, footer_y0, footer_x1, footer_y1)
            
            # Extract text from the footer area
            footer_text = page.get_text("text", clip=footer_rect).strip()
            
            return footer_text
            
        except Exception as e:
            self.logger.error(f"Error extracting footer region: {e}")
            return ""
    
    def get_book_metadata(self, pdf_name: str) -> Optional[Dict[str, Any]]:
        """
        Get book metadata including header and footer heights.
        
        Args:
            pdf_name: Name of the PDF file
            
        Returns:
            dict: Book metadata if found, None otherwise
            
        Raises:
            ContentExtractionError: If database query fails
        """
        try:
            # Get book ID first
            book_id = self.db.get_book_id_by_pdf_name(pdf_name)
            if not book_id:
                self.logger.warning(f"No book found for PDF: {pdf_name}")
                return None
            
            # Get complete book information
            book_info = self.db.get_book_by_id(book_id)
            if not book_info:
                self.logger.warning(f"No book metadata found for ID: {book_id}")
                return None
            
            self.logger.info(f"Retrieved metadata for book: {book_info['original_book_title']}")
            return book_info
            
        except DatabaseError as e:
            self.logger.error(f"Database error retrieving book metadata for {pdf_name}: {e}")
            raise ContentExtractionError(f"Failed to retrieve book metadata: {e}")
    
    def extract_page_content(self, pdf_name: str, page_number: int, extraction_type: ExtractionType = ExtractionType.BODY, apply_sanskrit_fixes: bool = True) -> Optional[str]:
        """
        Extract content from specified region of a page (body, header, or footer).
        
        Args:
            pdf_name: Name of the PDF file
            page_number: Page number to extract (1-indexed)
            extraction_type: Type of content to extract (BODY, HEADER, or FOOTER)
            apply_sanskrit_fixes: Whether to apply Sanskrit glyph corrections
            
        Returns:
            str: Extracted content if successful, None if extraction fails or region not available
            
        Raises:
            ContentExtractionError: If extraction fails
        """
        try:
            self.logger.info(f"Starting {extraction_type.value} extraction for {pdf_name}, page {page_number}")
            
            # 1. Get book metadata from database
            book_metadata = self.get_book_metadata(pdf_name)
            if not book_metadata:
                return None
            
            book_id = book_metadata['book_id']
            header_height = book_metadata['header_height']
            footer_height = book_metadata['footer_height']
            
            # 2. Check if requested extraction type is available
            if extraction_type == ExtractionType.HEADER and header_height is None:
                self.logger.warning(f"Header extraction requested but header_height not available for {pdf_name}")
                return None
            elif extraction_type == ExtractionType.FOOTER and footer_height is None:
                self.logger.warning(f"Footer extraction requested but footer_height not available for {pdf_name}")
                return None
            
            # 3. Get PDF file path
            pdf_path = self._get_pdf_path(pdf_name)
            
            # 4. Open PDF and extract content
            doc = fitz.open(pdf_path)
            
            # Validate page number (PyMuPDF uses 0-indexed)
            if page_number < 1 or page_number > doc.page_count:
                doc.close()
                raise ContentExtractionError(f"Invalid page number {page_number}. PDF has {doc.page_count} pages.")
            
            # Load the specific page (convert to 0-indexed)
            page = doc.load_page(page_number - 1)
            page_rect = page.rect
            
            # Convert to float, handling None values appropriately
            # For header: if NULL, assume no header (start from top of page)
            header_height = float(header_height or 0.0)
            # For footer: if NULL, assume no footer (extract to bottom of page)
            footer_height = float(footer_height or page_rect.height)
            
            self.logger.info(f"Book ID: {book_id}, Header: {header_height}pt, Footer: {footer_height}pt")
            
            # 5. Extract content based on extraction type
            if extraction_type == ExtractionType.HEADER:
                raw_content = self._extract_header_region(page, header_height)
            elif extraction_type == ExtractionType.FOOTER:
                raw_content = self._extract_footer_region(page, footer_height)
            else:  # BODY
                raw_content = self._extract_content_region(page, header_height, footer_height)
            
            doc.close()
            
            if not raw_content.strip():
                self.logger.warning(f"No {extraction_type.value} content extracted from {pdf_name}, page {page_number}")
                return ""
            
            # 6. Apply Sanskrit glyph fixes if requested
            if apply_sanskrit_fixes:
                cleaned_content = fix_iast_glyphs(raw_content, book_id=book_id)
                self.logger.info(f"Applied Sanskrit glyph corrections")
            else:
                cleaned_content = raw_content
            
            self.logger.info(f"Successfully extracted {len(cleaned_content)} characters from {extraction_type.value} of {pdf_name}, page {page_number}")
            return cleaned_content
            
        except fitz.FileDataError as e:
            self.logger.error(f"PDF file error for {pdf_name}: {e}")
            raise ContentExtractionError(f"PDF file error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error extracting content from {pdf_name}, page {page_number}: {e}")
            raise ContentExtractionError(f"Content extraction failed: {e}")
    
    def extract_page_content_with_metadata(self, pdf_name: str, page_number: int, extraction_type: ExtractionType = ExtractionType.BODY) -> Optional[Dict[str, Any]]:
        """
        Extract page content along with metadata information.
        
        Args:
            pdf_name: Name of the PDF file
            page_number: Page number to extract (1-indexed)
            extraction_type: Type of content to extract (BODY, HEADER, or FOOTER)
            
        Returns:
            dict: Content and metadata if successful, None otherwise
        """
        try:
            book_metadata = self.get_book_metadata(pdf_name)
            if not book_metadata:
                return None
            
            content = self.extract_page_content(pdf_name, page_number, extraction_type)
            if content is None:
                return None
            
            # Check availability status for the requested extraction type
            header_available = book_metadata['header_height'] is not None
            footer_available = book_metadata['footer_height'] is not None
            
            return {
                'book_id': book_metadata['book_id'],
                'book_title': book_metadata['original_book_title'],
                'english_title': book_metadata['english_book_title'],
                'pdf_name': pdf_name,
                'page_number': page_number,
                'extraction_type': extraction_type.value,
                'content': content,
                'content_length': len(content),
                'header_height': book_metadata['header_height'],
                'footer_height': book_metadata['footer_height'],
                'header_available': header_available,
                'footer_available': footer_available,
                'extraction_successful': True
            }
            
        except ContentExtractionError as e:
            self.logger.error(f"Failed to extract content with metadata: {e}")
            return {
                'book_id': None,
                'book_title': None,
                'english_title': None,
                'pdf_name': pdf_name,
                'page_number': page_number,
                'extraction_type': extraction_type.value,
                'content': None,
                'content_length': 0,
                'header_height': None,
                'footer_height': None,
                'header_available': False,
                'footer_available': False,
                'extraction_successful': False,
                'error': str(e)
            }
    
    def batch_extract_pages(self, pdf_name: str, page_range: tuple = None) -> Dict[int, str]:
        """
        Extract content from multiple pages in a single PDF.
        
        Args:
            pdf_name: Name of the PDF file
            page_range: Tuple of (start_page, end_page) both inclusive and 1-indexed.
                       If None, extracts all pages.
            
        Returns:
            dict: Dictionary mapping page numbers to extracted content
        """
        results = {}
        
        try:
            # Get book metadata
            book_metadata = self.get_book_metadata(pdf_name)
            if not book_metadata:
                self.logger.error(f"Cannot perform batch extraction without book metadata for {pdf_name}")
                return results
            
            # Determine page range
            if page_range:
                start_page, end_page = page_range
            else:
                # Get total pages from database or PDF
                pdf_path = self._get_pdf_path(pdf_name)
                doc = fitz.open(pdf_path)
                start_page = 1
                end_page = doc.page_count
                doc.close()
            
            self.logger.info(f"Starting batch extraction for {pdf_name}, pages {start_page}-{end_page}")
            
            # Extract each page
            successful_extractions = 0
            for page_num in range(start_page, end_page + 1):
                try:
                    content = self.extract_page_content(pdf_name, page_num)
                    if content is not None:
                        results[page_num] = content
                        successful_extractions += 1
                    else:
                        results[page_num] = ""  # Empty content for failed extractions
                except ContentExtractionError as e:
                    self.logger.warning(f"Failed to extract page {page_num}: {e}")
                    results[page_num] = ""
            
            self.logger.info(f"Batch extraction completed: {successful_extractions}/{len(results)} pages successful")
            
        except Exception as e:
            self.logger.error(f"Batch extraction failed for {pdf_name}: {e}")
        
        return results
    
    def test_connection(self) -> bool:
        """Test database connection and PDF folder access."""
        try:
            # Test database connection
            if not self.db.test_connection():
                return False
            
            # Test PDF folder access
            if not os.path.exists(self.pdf_folder_path):
                self.logger.error(f"PDF folder not accessible: {self.pdf_folder_path}")
                return False
            
            self.logger.info("Connection test successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False


# =====================================================
# EXAMPLE USAGE AND TESTING
# =====================================================

def main():
    """Example usage of the PageContentExtractor utility."""
    
    # Initialize the extractor
    extractor = PageContentExtractor()
    
    # Test connection
    if not extractor.test_connection():
        print("Failed to establish connections. Check your configuration.")
        return
    
    try:
        pdf_name = "Rupa_Goswami_2ed_2014.pdf"  # Replace with actual PDF name
        page_number = 6
        
        # Example 1: Extract body content (default)
        print(f"=== Extracting BODY content from {pdf_name}, page {page_number} ===")
        body_content = extractor.extract_page_content(pdf_name, page_number, ExtractionType.BODY)
        if body_content:
            print(f"Body content length: {len(body_content)} characters")
            print(f"Body content preview: {body_content[:200]}...")
        else:
            print("No body content extracted")
        
        # Example 2: Extract header content
        print(f"\n=== Extracting HEADER content from {pdf_name}, page {page_number} ===")
        header_content = extractor.extract_page_content(pdf_name, page_number, ExtractionType.HEADER)
        if header_content:
            print(f"Header content length: {len(header_content)} characters")
            print(f"Header content: {header_content}")
        elif header_content is None:
            print("Header extraction not available (header_height is null in database)")
        else:
            print("No header content extracted")
            
        # Example 3: Extract footer content
        print(f"\n=== Extracting FOOTER content from {pdf_name}, page {page_number} ===")
        footer_content = extractor.extract_page_content(pdf_name, page_number, ExtractionType.FOOTER)
        if footer_content:
            print(f"Footer content length: {len(footer_content)} characters")
            print(f"Footer content: {footer_content}")
        elif footer_content is None:
            print("Footer extraction not available (footer_height is null in database)")
        else:
            print("No footer content extracted")
        
        # Example 4: Extract with metadata for different types
        print(f"\n=== Extracting with metadata for all types ===")
        for extraction_type in [ExtractionType.BODY, ExtractionType.HEADER, ExtractionType.FOOTER]:
            print(f"\n--- {extraction_type.value.upper()} with metadata ---")
            result = extractor.extract_page_content_with_metadata(pdf_name, page_number, extraction_type)
            
            if result and result['extraction_successful']:
                print(f"Book: {result['book_title']}")
                print(f"Extraction Type: {result['extraction_type']}")
                print(f"Content Length: {result['content_length']} characters")
                print(f"Header Available: {result['header_available']}")
                print(f"Footer Available: {result['footer_available']}")
            elif result:
                print(f"Extraction failed: {result.get('error', 'Unknown error')}")
                print(f"Header Available: {result['header_available']}")
                print(f"Footer Available: {result['footer_available']}")
            else:
                print("No metadata result")
            
    except ContentExtractionError as e:
        print(f"Extraction error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()