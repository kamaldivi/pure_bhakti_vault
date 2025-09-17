#!/usr/bin/env python3
"""
Verse/Śloka Index Extractor — Production Version

A comprehensive verse index extraction system with database integration:
- Database-driven PDF mapping from book.verse_pages
- PageContentExtractor integration for clean body text (excludes headers/footers)
- Configurable output modes: database insertion (default) or CSV export
- Batch processing with conflict resolution and error handling
- Modular design for use in other utilities and automated workflows
- Sanskrit text normalization support
"""

from __future__ import annotations
import csv
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from page_content_extractor import PageContentExtractor, ExtractionType
except ImportError as e:
    raise RuntimeError(f"Required dependencies not found: {e}") from e

PageRange = Tuple[int, int]
PdfMapping = Dict[str, PageRange]
Row = Dict[str, object]


@dataclass
class ExtractorDeps:
    """
    Injectable dependencies for database and Sanskrit text processing utilities.
    
    Allows for dependency injection to support testing and different configurations.
    Automatically initializes with production database and Sanskrit utilities if available.
    """
    get_book_id_by_pdf: Optional[Callable[[str], Optional[int]]] = None
    normalize_text: Optional[Callable[[str], str]] = None


class VerseIndexExtractor:
    """
    Production-ready verse index extractor with database integration.
    
    Extracts verse names and page numbers from PDF verse index pages,
    with support for both database insertion and CSV export.
    """
    
    def __init__(
        self,
        pdf_folder: str,
        output_csv: str = "verse_index.csv",
        deps: Optional[ExtractorDeps] = None,
        log_level: int = logging.INFO,
        use_database: bool = True,
    ) -> None:
        """
        Initialize the verse index extractor.
        
        Args:
            pdf_folder: Path to folder containing PDF files
            output_csv: Output CSV filename (used when use_database=False)
            deps: Optional dependency injection for testing/configuration
            log_level: Logging level (default: INFO)
            use_database: If True, insert records into database; if False, write CSV
        """
        self.pdf_folder = Path(pdf_folder)
        self.output_csv = Path(output_csv)
        self.deps = deps or ExtractorDeps()
        self.use_database = use_database

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger("VerseIndexExtractor")

        if self.deps.get_book_id_by_pdf is None:
            try:
                db = PureBhaktiVaultDB()
                self.deps.get_book_id_by_pdf = db.get_book_id_by_pdf_name
            except Exception as e:
                self.logger.warning("DB util not available: %s", e)
        
        # Initialize PageContentExtractor for clean body text extraction
        self.page_extractor = None
        try:
            self.page_extractor = PageContentExtractor()
            self.logger.info("PageContentExtractor initialized - will extract body content excluding headers/footers")
        except Exception as e:
            self.logger.warning("PageContentExtractor not available: %s - falling back to basic extraction", e)

        if self.deps.normalize_text is None:
            try:
                from sanskrit_utils import fix_iast_glyphs
                self.deps.normalize_text = fix_iast_glyphs
            except Exception as e:
                self.logger.info("No Sanskrit normalization: %s", e)

    # ========== MAIN EXTRACTION WORKFLOW ==========
    
    def run_complete_extraction(self, pdf_mapping: PdfMapping) -> None:
        """
        Execute complete verse index extraction workflow for multiple PDFs.
        
        Processes each PDF in the mapping, extracts clean body text using PageContentExtractor,
        parses verse index entries, and outputs results to database or CSV based on configuration.
        
        Args:
            pdf_mapping: Dictionary mapping PDF names to (start_page, end_page) tuples
        """
        all_rows: List[Row] = []

        for pdf_name, page_range in pdf_mapping.items():
            pdf_path = self.pdf_folder / pdf_name
            if not pdf_path.exists():
                self.logger.warning("PDF not found: %s", pdf_path)
                continue

            self.logger.info("Processing %s pages %s", pdf_name, page_range)
            raw_text = self.extract_text_from_pdf_pages(pdf_path, page_range)
            cleaned_text = self.normalize_text_block(raw_text)
            entries = self.parse_verse_index(cleaned_text)

            book_id = self._get_book_id(pdf_name)
            for verse_name, pages in entries:
                for p in pages:
                    all_rows.append({
                        "book_id": book_id,
                        "pdf_name": pdf_name,
                        "verse_name": verse_name,
                        "page_number": p,
                    })

        # Write output based on configuration
        if self.use_database:
            self.write_to_database(all_rows)
        else:
            self.write_csv(all_rows)
            self.logger.info("Wrote %d rows to %s", len(all_rows), self.output_csv)

    # ========== TEXT EXTRACTION ==========
    
    def extract_text_from_pdf_pages(self, pdf_path: Path, page_range: PageRange) -> str:
        """
        Extract text from PDF pages using PageContentExtractor or fallback to basic extraction.
        
        Prioritizes PageContentExtractor for clean body content (excludes headers/footers),
        falls back to basic PyMuPDF text extraction if PageContentExtractor fails.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Tuple of (start_page, end_page) - both inclusive, 1-indexed
            
        Returns:
            str: Extracted text from all pages in range, joined with newlines
        """
        start, end = page_range
        if start < 1 or end < start:
            self.logger.error("Invalid page range for %s", pdf_path.name)
            return ""

        # Use PageContentExtractor if available for clean body content
        if self.page_extractor:
            try:
                pdf_name = pdf_path.name
                chunks = []
                
                for page_num in range(start, end + 1):
                    content = self.page_extractor.extract_page_content(
                        pdf_name, page_num, ExtractionType.BODY
                    )
                    if content:
                        chunks.append(content)
                    else:
                        self.logger.debug("No body content extracted from %s page %d", pdf_name, page_num)
                
                if chunks:
                    self.logger.debug("Extracted clean body content from %d pages using PageContentExtractor", len(chunks))
                    return "\n".join(chunks)
                else:
                    self.logger.warning("No content extracted using PageContentExtractor, falling back to basic extraction")
                    
            except Exception as e:
                self.logger.warning("PageContentExtractor failed for %s: %s - falling back to basic extraction", pdf_path.name, e)
        
        # Fallback to basic text extraction
        doc = fitz.open(pdf_path)
        try:
            s_idx, e_idx = start - 1, min(end - 1, len(doc) - 1)
            chunks = [doc.load_page(i).get_text("text") for i in range(s_idx, e_idx + 1)]
            self.logger.debug("Extracted text from %d pages using basic extraction", len(chunks))
            return "\n".join(chunks)
        finally:
            doc.close()

    # ========== TEXT NORMALIZATION ==========
    
    def normalize_text_block(self, text: str) -> str:
        """
        Normalize extracted text for better parsing.
        
        Applies Sanskrit glyph fixes if available, standardizes dot leaders,
        and removes trailing whitespace from lines.
        
        Args:
            text: Raw extracted text
            
        Returns:
            str: Normalized text ready for verse index parsing
        """
        if self.deps.normalize_text:
            try:
                text = self.deps.normalize_text(text)
            except Exception as e:
                self.logger.warning("Glyph fix failed: %s", e)
        text = re.sub(r"(?:\.\s*){3,}", ".....", text)
        return "\n".join(line.rstrip() for line in text.splitlines())

    # ========== VERSE INDEX PARSING ==========
    
    def parse_verse_index(self, text: str) -> List[Tuple[str, List[int]]]:
        """
        Parse verse index text to extract verse names and page numbers.
        
        Supports multiple formats:
        - Dot leaders: "Verse name ........ 123, 456"
        - Multi-space: "Verse name        123, 456"
        - Two-line: "Verse name" followed by "123, 456" on next line(s)
        - Continuation lines with leader-only patterns
        
        Args:
            text: Normalized text from verse index pages
            
        Returns:
            List of tuples: [(verse_name, [page_numbers])]
        """
        entries = []
        pending_verse, pending_pages = None, []

        dot_leaders = re.compile(r"^([^\d.].*?)\s*(?:\.{2,})\s*(\d+(?:,\s*\d+)*)\s*,?$")
        multi_spaces = re.compile(r"^(.*?\S)\s{2,}(\d+(?:,\s*\d+)*)\s*,?$")
        pages_only = re.compile(r"^(\d+(?:,\s*\d+)*)\s*,?$")
        leader_only = re.compile(r"^(?:\.{2,})\s*(?:(\d+),\s*)?(\d+(?:,\s*\d+)*)\s*,?$")

        def is_header(line: str) -> bool:
            s = line.strip()
            return not s or s in {"Verse Index", "Śloka Index", "Sloka Index"} or \
                   re.fullmatch(r"[A-Z]", s)

        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Leader-only continuation
            m_lo = leader_only.match(line)
            if m_lo and pending_verse:
                if m_lo.group(1):
                    pending_pages.append(int(m_lo.group(1)))
                pending_pages.extend(map(int, m_lo.group(2).split(",")))
                if not line.endswith(","):
                    entries.append((pending_verse, pending_pages))
                    pending_verse, pending_pages = None, []
                i += 1
                continue

            # Dot leaders
            m_dl = dot_leaders.match(line)
            if m_dl and not is_header(line):
                verse = m_dl.group(1).strip()
                pages = list(map(int, m_dl.group(2).split(",")))
                next_line = lines[i+1].strip() if i+1 < len(lines) else ""
                if line.endswith(",") or leader_only.match(next_line):
                    pending_verse, pending_pages = verse, pages
                else:
                    entries.append((verse, pages))
                i += 1
                continue

            # Multi-space
            m_ms = multi_spaces.match(line)
            if m_ms and not is_header(line):
                verse = m_ms.group(1).strip()
                pages = list(map(int, m_ms.group(2).split(",")))
                next_line = lines[i+1].strip() if i+1 < len(lines) else ""
                if line.endswith(",") or leader_only.match(next_line):
                    pending_verse, pending_pages = verse, pages
                else:
                    entries.append((verse, pages))
                i += 1
                continue

            # Two-line: verse then pages
            if not is_header(line) and not pages_only.match(line) and not line.startswith("."):
                pending_verse, pending_pages = line.strip(), []
                i += 1
                while i < len(lines):
                    p_line = lines[i].strip()
                    if leader_only.match(p_line):
                        mlo = leader_only.match(p_line)
                        if mlo.group(1):
                            pending_pages.append(int(mlo.group(1)))
                        pending_pages.extend(map(int, mlo.group(2).split(",")))
                        i += 1
                        if not p_line.endswith(","):
                            break
                        continue
                    m_po = pages_only.match(p_line)
                    if m_po:
                        pending_pages.extend(map(int, m_po.group(1).split(",")))
                        i += 1
                        if not p_line.endswith(","):
                            break
                        continue
                    break
                if pending_pages:
                    entries.append((pending_verse, pending_pages))
                pending_verse, pending_pages = None, []
                continue

            i += 1

        if pending_verse and pending_pages:
            entries.append((pending_verse, pending_pages))

        return entries

    # ========== OUTPUT METHODS ==========
    
    def write_to_database(self, rows: List[Row]) -> None:
        """
        Insert verse index records into the database with batch processing.
        
        Uses batch insert with ON CONFLICT DO NOTHING for duplicate handling.
        Filters out rows with missing book_id and provides detailed logging.
        
        Args:
            rows: List of dictionaries with keys: book_id, verse_name, page_number
            
        Raises:
            DatabaseError: If database insertion fails
        """
        try:
            db = PureBhaktiVaultDB()
            
            # Prepare the insert query
            insert_query = """
                INSERT INTO verse_index (book_id, verse_name, page_number)
                VALUES (%s, %s, %s)
                ON CONFLICT (book_id, verse_name, page_number) DO NOTHING
            """
            
            # Filter out rows with missing book_id
            valid_rows = [row for row in rows if row.get('book_id') is not None]
            invalid_count = len(rows) - len(valid_rows)
            
            if invalid_count > 0:
                self.logger.warning(f"Skipping {invalid_count} rows with missing book_id")
            
            if not valid_rows:
                self.logger.warning("No valid rows to insert into database")
                return
            
            # Prepare batch data
            batch_data = [
                (row['book_id'], row['verse_name'], row['page_number'])
                for row in valid_rows
            ]
            
            # Execute batch insert
            with db.get_cursor() as cursor:
                cursor.executemany(insert_query, batch_data)
                inserted_count = cursor.rowcount
            
            self.logger.info(f"Successfully inserted {inserted_count} verse index records into database")
            
        except (DatabaseError, Exception) as e:
            self.logger.error(f"Error inserting verse index records into database: {e}")
            raise
    
    def write_csv(self, rows: List[Row]) -> None:
        """
        Write verse index records to CSV file.
        
        Creates output directory if needed and writes CSV with headers.
        
        Args:
            rows: List of dictionaries with keys: book_id, pdf_name, verse_name, page_number
        """
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["book_id", "pdf_name", "verse_name", "page_number"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    def _get_book_id(self, pdf_name: str) -> Optional[int]:
        """
        Get book ID for a PDF name using injected database dependency.
        
        Args:
            pdf_name: PDF filename to look up
            
        Returns:
            int: Book ID if found, None otherwise
        """
        if self.deps.get_book_id_by_pdf:
            try:
                return self.deps.get_book_id_by_pdf(pdf_name)
            except Exception as e:
                self.logger.warning("Book ID lookup failed for %s: %s", pdf_name, e)
        return None


# ========== DATABASE-DRIVEN PDF MAPPING ==========

def get_pdf_mapping_from_database() -> PdfMapping:
    """
    Get PDF mapping from database for books where verse_pages IS NOT NULL.
    
    Returns:
        Dictionary mapping PDF names to (start_page, end_page) tuples
    """
    try:
        db = PureBhaktiVaultDB()
        
        # Query for books with verse_pages defined
        query = """
            SELECT pdf_name, verse_pages 
            FROM book 
            WHERE verse_pages IS NOT NULL
            ORDER BY pdf_name
        """
        
        with db.get_cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            
            mapping = {}
            for row in results:
                pdf_name = row['pdf_name']
                verse_pages = row['verse_pages']
                
                # Parse the verse_pages - handle NumericRange objects
                try:
                    if hasattr(verse_pages, 'lower') and hasattr(verse_pages, 'upper'):
                        # This is a psycopg2 NumericRange object
                        start_val = verse_pages.lower if verse_pages.lower is not None else 0
                        end_val = verse_pages.upper if verse_pages.upper is not None else 0
                        
                        # NumericRange upper bound is typically exclusive, convert to inclusive
                        if start_val > 0 and end_val > start_val:
                            page_range = (start_val, end_val - 1)
                            mapping[pdf_name] = page_range
                            print(f"📚 Added {pdf_name}: {page_range}")
                        else:
                            print(f"⚠️  Invalid range for {pdf_name}: {verse_pages}")
                    else:
                        print(f"⚠️  Could not parse verse_pages for {pdf_name}: {verse_pages}")
                except Exception as e:
                    print(f"⚠️  Error parsing {pdf_name}: {e}")
            
            print(f"✅ Loaded {len(mapping)} PDF mappings from database")
            return mapping
            
    except (DatabaseError, Exception) as e:
        print(f"❌ Error loading PDF mapping from database: {e}")
        return {}


def get_pdf_mapping_with_fallback() -> PdfMapping:
    """
    Get PDF mapping from database with manual fallback if needed.
    
    Returns:
        Dictionary mapping PDF names to (start_page, end_page) tuples
    """
    # Try database first
    pdf_mapping_from_db = get_pdf_mapping_from_database()
    
    if pdf_mapping_from_db:
        print(f"🔄 Using database mapping with {len(pdf_mapping_from_db)} PDFs")
        return pdf_mapping_from_db
    
    # Fallback to a minimal manual mapping (only if database fails)
    print("📋 Database mapping failed, using minimal fallback")
    fallback_mapping: PdfMapping = {
        "bhagavad-gita-4ed-eng.pdf": (1099, 1113),
        "Jaiva-dharma-5Ed-2013.pdf": (1027, 1047),
        "BRSB-3Ed-2017.pdf": (327, 333),
    }
    
    print(f"🔄 Using fallback mapping with {len(fallback_mapping)} PDFs")
    return fallback_mapping


# ========== CONVENIENCE FUNCTIONS ==========

def extract_verse_index_to_database(pdf_folder: str = None) -> None:
    """
    Convenience function to extract verse index directly to database.
    
    Args:
        pdf_folder: Path to PDF folder (uses environment variable if None)
    """
    if pdf_folder is None:
        pdf_folder = os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books')
    
    pdf_mapping = get_pdf_mapping_with_fallback()
    
    if not pdf_mapping:
        raise ValueError("No PDF mappings available. Please check database configuration.")
    
    extractor = VerseIndexExtractor(pdf_folder, use_database=True)
    extractor.run_complete_extraction(pdf_mapping)


# ========== MAIN EXECUTION ==========

if __name__ == "__main__":
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not available, using default paths")
    
    # Configuration
    pdf_folder = os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books')
    output_folder = os.getenv('PROCESS_FOLDER', '.')
    output_csv = os.path.join(output_folder, "pure_bhakti_vault_verse_index.csv")
    
    # Output mode configuration - default to database
    use_database = os.getenv('VERSE_OUTPUT_MODE', 'database').lower() != 'csv'
    
    print(f"📋 Output mode: {'Database' if use_database else 'CSV file'}")
    
    # Get PDF mapping from database
    pdf_mapping = get_pdf_mapping_with_fallback()
    
    if not pdf_mapping:
        print("❌ No PDF mappings available. Please check database or add manual mappings.")
        exit(1)
    
    # Run the extraction
    extractor = VerseIndexExtractor(pdf_folder, output_csv, use_database=use_database)
    extractor.run_complete_extraction(pdf_mapping)
