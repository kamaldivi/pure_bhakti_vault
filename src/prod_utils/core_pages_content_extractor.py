#!/usr/bin/env python3
"""
Core Pages Content Extractor

Utility to extract content from core pages of all books and populate the content table.

This utility:
1. Scans PDF_FOLDER for all PDF files
2. Maps PDFs to book_ids using the database
3. Queries page_map table for pages with page_type='Core'
4. Uses PageContentExtractor to extract body content (with automatic Sanskrit glyph fixes)
5. Inserts extracted content into the content table

USAGE:
    python core_pages_content_extractor.py                     # Process all books
    python core_pages_content_extractor.py --book-id 5         # Process only book ID 5
    python core_pages_content_extractor.py --dry-run           # Preview without database changes

ENVIRONMENT VARIABLES:
    TEST_BOOK_ID: If set, processes only the specified book ID (overridden by --book-id)

OUTPUT:
    - Direct database insertion into PostgreSQL content table
    - Progress tracking and statistics
    - Error reporting for failed extractions

Table Structure:
    content (content_id, book_id, page_number, page_content, created_at, updated_at)
    Unique constraint on (book_id, page_number)
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import utilities
from page_content_extractor import PageContentExtractor, ExtractionType
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError

class CorePagesContentExtractor:
    """
    Utility to extract content from core pages and populate the content table.
    """
    
    def __init__(self, db_params: Optional[Dict[str, str]] = None):
        """Initialize the core pages content extractor."""
        self.db = PureBhaktiVaultDB(db_params)
        self.page_extractor = PageContentExtractor()
        
        # Get PDF folder from environment
        self.pdf_folder = Path(os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books/'))
        
        if not self.pdf_folder.exists():
            raise ValueError(f"PDF folder does not exist: {self.pdf_folder}")
            
        print(f"📁 PDF Folder: {self.pdf_folder}")
    
    def get_all_books_with_pdfs(self) -> List[Dict[str, Any]]:
        """
        Get all books that have corresponding PDF files in the PDF folder.
        
        Returns:
            List of book information dictionaries
        """
        try:
            # Get all books from database
            books = self.db.get_all_books()
            
            # Filter books that have PDFs in the folder
            books_with_pdfs = []
            for book in books:
                pdf_path = self.pdf_folder / book['pdf_name']
                if pdf_path.exists():
                    books_with_pdfs.append(book)
                else:
                    print(f"⚠️  PDF not found for book {book['book_id']}: {book['pdf_name']}")
            
            print(f"📚 Found {len(books_with_pdfs)} books with PDFs out of {len(books)} total books")
            return books_with_pdfs
            
        except DatabaseError as e:
            print(f"❌ Error getting books from database: {e}")
            return []
    
    def get_core_pages_for_book(self, book_id: int) -> List[int]:
        """
        Get all core page numbers for a specific book.
        
        Args:
            book_id: The book ID to get core pages for
            
        Returns:
            List of page numbers that are marked as 'Core' pages
        """
        query = """
            SELECT page_number 
            FROM page_map 
            WHERE book_id = %s AND page_type = 'Core'
            ORDER BY page_number
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                results = cursor.fetchall()
                
                core_pages = [row['page_number'] for row in results]
                return core_pages
                
        except DatabaseError as e:
            print(f"❌ Error getting core pages for book {book_id}: {e}")
            return []
    
    def insert_page_content(self, book_id: int, page_number: int, content: str) -> bool:
        """
        Insert extracted page content into the content table.
        
        Args:
            book_id: Book ID
            page_number: Page number
            content: Extracted page content
            
        Returns:
            bool: True if successful, False otherwise
        """
        insert_query = """
            INSERT INTO content (book_id, page_number, page_content, created_at, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(insert_query, (book_id, page_number, content))
                return True
                
        except Exception as e:
            print(f"  ❌ Error inserting content for book {book_id}, page {page_number}: {e}")
            return False
    
    def extract_content_for_book(self, book: Dict[str, Any], dry_run: bool = False) -> Tuple[int, int, int]:
        """
        Extract content from all core pages of a book.
        
        Args:
            book: Book information dictionary
            dry_run: If True, don't actually insert to database
            
        Returns:
            Tuple of (total_pages, successful_extractions, successful_inserts)
        """
        book_id = book['book_id']
        pdf_name = book['pdf_name']
        book_title = book['original_book_title']
        
        print(f"\n📖 Processing Book {book_id}: {book_title}")
        print(f"   PDF: {pdf_name}")
        
        # Get core pages for this book
        core_pages = self.get_core_pages_for_book(book_id)
        
        if not core_pages:
            print(f"   ⚠️  No core pages found for book {book_id}")
            return (0, 0, 0)
        
        print(f"   📄 Found {len(core_pages)} core pages: {core_pages[:10]}{'...' if len(core_pages) > 10 else ''}")
        
        successful_extractions = 0
        successful_inserts = 0
        
        for page_number in core_pages:
            try:
                # Extract content using PageContentExtractor with BODY type
                content = self.page_extractor.extract_page_content(
                    pdf_name=pdf_name,
                    page_number=page_number,
                    extraction_type=ExtractionType.BODY,
                    apply_sanskrit_fixes=True
                )
                
                if content and content.strip():
                    successful_extractions += 1
                    content_length = len(content)
                    
                    if not dry_run:
                        # Insert into database
                        if self.insert_page_content(book_id, page_number, content):
                            successful_inserts += 1
                            print(f"   ✅ Page {page_number}: {content_length} chars extracted and inserted")
                        else:
                            print(f"   ❌ Page {page_number}: extraction successful but database insert failed")
                    else:
                        successful_inserts += 1  # Count as success for dry run
                        print(f"   🔍 Page {page_number}: {content_length} chars extracted (dry run)")
                else:
                    print(f"   ⚠️  Page {page_number}: No content extracted")
                    
            except Exception as e:
                print(f"   ❌ Page {page_number}: Error during extraction - {e}")
        
        print(f"   📊 Summary: {successful_extractions}/{len(core_pages)} extractions successful, {successful_inserts}/{len(core_pages)} inserts successful")
        
        return (len(core_pages), successful_extractions, successful_inserts)
    
    def process_all_books(self, specific_book_id: Optional[int] = None, dry_run: bool = False):
        """
        Process all books or a specific book to extract core page content.
        
        Args:
            specific_book_id: If provided, process only this book
            dry_run: If True, don't actually insert to database
        """
        print("🚀 Starting Core Pages Content Extraction")
        print("=" * 60)
        
        if dry_run:
            print("🔍 DRY RUN MODE: No database inserts will be performed")
        
        if specific_book_id:
            print(f"🎯 Processing specific book ID: {specific_book_id}")
        
        # Get all books with PDFs
        all_books = self.get_all_books_with_pdfs()
        
        if not all_books:
            print("❌ No books with PDFs found")
            return
        
        # Filter to specific book if requested
        if specific_book_id:
            all_books = [book for book in all_books if book['book_id'] == specific_book_id]
            if not all_books:
                print(f"❌ Book ID {specific_book_id} not found or has no PDF")
                return
        
        # Statistics
        total_books = len(all_books)
        total_pages_processed = 0
        total_extractions_successful = 0
        total_inserts_successful = 0
        
        # Process each book
        for i, book in enumerate(all_books, 1):
            print(f"\n{'='*20} Book {i}/{total_books} {'='*20}")
            
            pages, extractions, inserts = self.extract_content_for_book(book, dry_run)
            
            total_pages_processed += pages
            total_extractions_successful += extractions
            total_inserts_successful += inserts
        
        # Final summary
        print(f"\n🎉 Processing Complete!")
        print("=" * 60)
        print(f"📊 Final Statistics:")
        print(f"   • Books processed: {total_books}")
        print(f"   • Total core pages: {total_pages_processed}")
        print(f"   • Successful extractions: {total_extractions_successful} ({total_extractions_successful/max(total_pages_processed,1)*100:.1f}%)")
        print(f"   • Successful database inserts: {total_inserts_successful} ({total_inserts_successful/max(total_pages_processed,1)*100:.1f}%)")
        
        if dry_run:
            print(f"   • Mode: DRY RUN (no actual database changes)")
        else:
            print(f"   • Content table populated with {total_inserts_successful} records")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Core Pages Content Extractor - Extract content from core pages and populate content table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python core_pages_content_extractor.py                    # Process all books
  python core_pages_content_extractor.py --book-id 5        # Process only book ID 5
  python core_pages_content_extractor.py --dry-run          # Preview without database changes
  python core_pages_content_extractor.py --help             # Show this help message

Environment Variables:
  TEST_BOOK_ID=41                                           # Process only book ID 41 (overridden by --book-id)

The script will:
1. Scan PDF_FOLDER for available PDF files
2. Query page_map table for pages with page_type='Core'
3. Extract body content using PageContentExtractor (handles Sanskrit fixes automatically)
4. Insert extracted content into the content table

Priority for book selection: --book-id > TEST_BOOK_ID > process all books
        """
    )
    
    parser.add_argument(
        "--book-id", 
        type=int,
        help="Process only the specified book ID (default: process all books)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview extraction without inserting into database"
    )
    
    return parser.parse_args()

def main():
    """Main function."""
    # Parse command line arguments
    args = parse_arguments()

    try:
        # Initialize the extractor
        extractor = CorePagesContentExtractor()

        # Test database connection
        if not extractor.db.test_connection():
            print("❌ Failed to connect to database. Check your connection parameters.")
            return

        print("✅ Database connection successful")

        # Check for TEST_BOOK_ID environment variable
        test_book_id = int(os.getenv('TEST_BOOK_ID')) if os.getenv('TEST_BOOK_ID') else None

        # Determine which book_id to use (priority: command line arg > TEST_BOOK_ID > process all)
        target_book_id = args.book_id or test_book_id

        if test_book_id and not args.book_id:
            print(f"🎯 TEST_BOOK_ID detected: Processing only book_id = {test_book_id}")

        # Process books
        extractor.process_all_books(
            specific_book_id=target_book_id,
            dry_run=args.dry_run
        )
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()