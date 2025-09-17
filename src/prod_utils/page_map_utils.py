#!/usr/bin/env python3
"""
Page Map Utils — Utility for generating page mapping data

A lightweight utility for processing PDFs and generating page mapping records:
- Can be called by other classes with just book_id
- Returns cleaned matrix of PageMapRecord objects
- No database insertion or header text extraction
"""

import os
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

try:
    import fitz  # PyMuPDF
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from sanskrit_utils import fix_iast_glyphs
except ImportError as e:
    raise RuntimeError(f"Required dependencies not found: {e}") from e


@dataclass
class BookConfig:
    """
    Configuration for a book's page mapping parameters.
    """
    book_id: int
    pdf_name: str
    footer_height: float
    page_label_location: Optional[str]
    

@dataclass 
class PageMapRecord:
    """
    Record for page mapping without header text.
    """
    book_id: int
    page_number: int
    page_label: str
    page_type: str = 'Primary'


class PageMapUtils:
    """
    Utility class for generating page map records from PDFs.
    
    Can be called by other classes with just a book_id to get
    cleaned page mapping data without database operations.
    """
    
    def __init__(self, pdf_folder: str = None, log_level: int = logging.WARNING):
        """
        Initialize the page map utils.
        
        Args:
            pdf_folder: Path to folder containing PDF files (defaults to env var)
            log_level: Logging level (default: WARNING for utility use)
        """
        self.pdf_folder = Path(pdf_folder or os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books'))
        
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger("PageMapUtils")
        
        # Initialize database connection for config lookup only
        try:
            self.db = PureBhaktiVaultDB()
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    def get_book_config(self, book_id: int) -> Optional[BookConfig]:
        """
        Get book configuration from the database by book_id.
        
        Args:
            book_id: The book ID to get configuration for
            
        Returns:
            BookConfig object if found, None otherwise
        """
        query = """
            SELECT book_id, pdf_name, footer_height, page_label_location
            FROM book 
            WHERE book_id = %s AND page_label_location IS NOT NULL
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                if result:
                    config = BookConfig(
                        book_id=result['book_id'],
                        pdf_name=result['pdf_name'],
                        footer_height=float(result['footer_height']) if result['footer_height'] else 0.0,
                        page_label_location=result['page_label_location']
                    )
                    self.logger.debug(f"Loaded config for book_id {book_id}")
                    return config
                else:
                    self.logger.warning(f"No configuration found for book_id {book_id}")
                    return None
                    
        except (DatabaseError, Exception) as e:
            self.logger.error(f"Error loading book configuration for book_id {book_id}: {e}")
            raise
    
    def generate_page_map_records(self, book_id: int) -> List[PageMapRecord]:
        """
        Generate page map records for a book by book_id.
        
        Args:
            book_id: The book ID to process
            
        Returns:
            List of cleaned PageMapRecord objects
        """
        config = self.get_book_config(book_id)
        if not config:
            return []
            
        return self._process_pdf(config)
    
    def _process_pdf(self, config: BookConfig) -> List[PageMapRecord]:
        """
        Process a single PDF and extract page mapping information.
        
        Args:
            config: BookConfig with processing parameters
            
        Returns:
            List of PageMapRecord objects
        """
        pdf_path = self.pdf_folder / config.pdf_name
        
        if not pdf_path.exists():
            self.logger.warning(f"PDF not found: {pdf_path}")
            return []
            
        try:
            doc = fitz.open(pdf_path)
            self.logger.debug(f"Processing {config.pdf_name} (book_id: {config.book_id})")
            
            page_records = []
            
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                page_rect = page.rect
                
                # Extract footer text only if footer height > 0
                footer_text = ""
                if config.footer_height > 0:
                    footer_rect_x0 = page_rect.x0
                    footer_rect_y0 = page_rect.y1 - config.footer_height
                    footer_rect_x1 = page_rect.x1
                    footer_rect_y1 = page_rect.y1
                    
                    footer_text = self._extract_text_from_region(
                        page, footer_rect_x0, footer_rect_y0, footer_rect_x1, footer_rect_y1
                    )
                    
                    # Apply Sanskrit text normalization to footer
                    try:
                        footer_text = fix_iast_glyphs(footer_text) if footer_text else ""
                    except Exception as e:
                        self.logger.debug(f"Sanskrit normalization failed for page {page_num + 1}: {e}")
                
                # Extract page label from footer only
                page_label = self._extract_page_label(footer_text, config.page_label_location)
                
                # Create page record without header text
                record = PageMapRecord(
                    book_id=config.book_id,
                    page_number=page_num + 1,
                    page_label=page_label,
                    page_type='Primary'
                )
                page_records.append(record)
            
            doc.close()
            
            self.logger.debug(f"Generated {len(page_records)} page records from {config.pdf_name}")
            return page_records
            
        except Exception as e:
            self.logger.error(f"Error processing {config.pdf_name}: {e}")
            return []
    
    def _extract_text_from_region(self, page, x0, y0, x1, y1) -> str:
        """
        Extract text from a specific rectangular region of a page.
        
        Args:
            page: PyMuPDF page object
            x0, y0, x1, y1: Rectangle coordinates
            
        Returns:
            str: Extracted text, empty string if extraction fails
        """
        try:
            rect = fitz.Rect(x0, y0, x1, y1)
            text = page.get_text("text", clip=rect).strip()
            return text if text else ""
        except Exception as e:
            self.logger.debug(f"Error extracting text from region: {e}")
            return ""
    
    def _is_valid_page_label(self, label: str) -> bool:
        """
        Validate if the extracted text is a reasonable page label.
        
        Args:
            label: The extracted label text
            
        Returns:
            bool: True if it's a valid page label, False otherwise
        """
        if not label or not label.strip():
            return False
            
        clean_label = label.strip().replace('-', '').replace('.', '').replace('_', '')
        
        if clean_label.isdigit():
            return len(clean_label) <= 10
        
        if re.match(r'^[ivxlcdm]+$', clean_label, re.IGNORECASE):
            return len(clean_label) <= 15
        
        if re.match(r'^[a-z0-9\-_.]+$', clean_label, re.IGNORECASE):
            return len(clean_label) <= 10
        
        return False
    
    def _extract_page_label(self, text: str, page_label_location: Optional[str] = None) -> str:
        """
        Extract page label from text.
        
        Args:
            text: Text to extract label from
            page_label_location: Location hint (preserved for compatibility)
            
        Returns:
            str: Extracted page label or empty string
        """
        # Note: page_label_location parameter preserved for compatibility but not used in simplified version
        if not text:
            return ""
            
        patterns = [
            r'\b([0-9]+(?:\s+[0-9]+)+)\b',
            r'\b([ivxlcdm]+(?:\s+[ivxlcdm]+)+)\b',
            r'\(([0-9]+)\)',
            r'\(([ivxlcdm]+)\)',
            r'\b([0-9]+)\b',
            r'\b([ivxlcdm]+)\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                label = match.group(1).replace(' ', '')
                
                if len(label) <= 20 and self._is_valid_page_label(label):
                    return label
                elif len(label) > 20:
                    self.logger.debug(f"Rejected page label (too long): '{label[:50]}...' (length: {len(label)})")
        
        return ""


def get_page_map_records(book_id: int, pdf_folder: str = None) -> List[PageMapRecord]:
    """
    Utility function to get page map records for a book.
    
    Args:
        book_id: The book ID to process
        pdf_folder: Optional path to PDF folder (uses env var if not provided)
        
    Returns:
        List of cleaned PageMapRecord objects
    """
    utils = PageMapUtils(pdf_folder)
    return utils.generate_page_map_records(book_id)


def get_page_map_tuples(book_id: int, pdf_folder: str = None) -> List[Tuple[int, int, str, str]]:
    """
    Utility function to get page map data as tuples for backward compatibility.
    
    Args:
        book_id: The book ID to process
        pdf_folder: Optional path to PDF folder (uses env var if not provided)
        
    Returns:
        List of tuples: (book_id, page_number, page_label, page_type)
    """
    records = get_page_map_records(book_id, pdf_folder)
    return [(r.book_id, r.page_number, r.page_label, r.page_type) for r in records]