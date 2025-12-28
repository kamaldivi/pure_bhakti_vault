#!/usr/bin/env python3
"""
Test script for PDF Content Transliteration Processor

This script tests the processor without actually processing all pages.
It validates:
1. Database connection
2. Book retrieval
3. PDF access
4. Single page extraction and processing
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prod_utils.pdf_content_transliteration_processor import PDFContentTransliterationProcessor
from prod_utils.pure_bhakti_vault_db import PureBhaktiVaultDB

def test_database_connection():
    """Test database connectivity."""
    print("\n" + "="*80)
    print("TEST 1: Database Connection")
    print("="*80)

    db = PureBhaktiVaultDB()
    if db.test_connection():
        print("✓ Database connection successful")
        return True
    else:
        print("✗ Database connection failed")
        return False


def test_get_books():
    """Test retrieving books from database."""
    print("\n" + "="*80)
    print("TEST 2: Retrieve Books")
    print("="*80)

    processor = PDFContentTransliterationProcessor()
    books = processor.get_books_to_process()

    if books:
        print(f"✓ Found {len(books)} books with type 'english-gurudev'")
        print("\nFirst 5 books:")
        for idx, book in enumerate(books[:5], 1):
            print(f"  {idx}. Book ID {book['book_id']:3d}: {book['pdf_name']}")
        return books
    else:
        print("✗ No books found")
        return []


def test_pdf_access(books):
    """Test PDF file access."""
    print("\n" + "="*80)
    print("TEST 3: PDF File Access")
    print("="*80)

    processor = PDFContentTransliterationProcessor()

    if not books:
        print("✗ No books to test")
        return None

    # Test first book
    book = books[0]
    book_id = book['book_id']
    pdf_name = book['pdf_name']
    pdf_path = os.path.join(processor.pdf_folder, pdf_name)

    print(f"Testing Book ID {book_id}: {pdf_name}")
    print(f"PDF path: {pdf_path}")

    if os.path.exists(pdf_path):
        print(f"✓ PDF file exists")

        # Try to open with PyMuPDF
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
            print(f"✓ PDF readable, {page_count} pages")
            return book
        except Exception as e:
            print(f"✗ Failed to open PDF: {e}")
            return None
    else:
        print(f"✗ PDF file not found")
        print(f"   Expected at: {pdf_path}")
        return None


def test_page_extraction(book):
    """Test extracting content from a single page."""
    print("\n" + "="*80)
    print("TEST 4: Single Page Content Extraction")
    print("="*80)

    if not book:
        print("✗ No book to test")
        return

    processor = PDFContentTransliterationProcessor()
    book_id = book['book_id']
    pdf_name = book['pdf_name']

    # Get pages to process
    pages = processor.get_pages_to_process(book_id, start_page=1)

    if not pages:
        print(f"✓ No pages need processing for book {book_id} (all pages already processed)")
        return

    # Test first page
    test_page = pages[0]
    print(f"Testing extraction of page {test_page} from book {book_id}")

    pdf_path = os.path.join(processor.pdf_folder, pdf_name)
    raw_content = processor.extract_page_content(pdf_path, test_page)

    if raw_content:
        print(f"✓ Extracted {len(raw_content)} characters")
        print(f"\nFirst 200 characters:")
        print("-"*80)
        print(raw_content[:200])
        print("-"*80)

        # Test transliteration fix
        print(f"\nApplying transliteration fix...")
        corrected_content, stats = processor.apply_transliteration_fix(raw_content, test_page)

        print(f"✓ Transliteration fix applied")
        print(f"  Words corrected: {stats.get('words_corrected', 0)}")
        print(f"  Processing time: {stats.get('processing_time_ms', 0):.2f}ms")
        print(f"  High confidence: {stats.get('high_confidence', 0)}")

        if stats.get('words_corrected', 0) > 0:
            print(f"\nFirst 200 characters of corrected text:")
            print("-"*80)
            print(corrected_content[:200])
            print("-"*80)
    else:
        print(f"✗ Failed to extract content")


def test_database_operations(book):
    """Test database insert/update operations."""
    print("\n" + "="*80)
    print("TEST 5: Database Operations (DRY RUN)")
    print("="*80)

    if not book:
        print("✗ No book to test")
        return

    processor = PDFContentTransliterationProcessor()
    book_id = book['book_id']

    # Get last processed page
    last_page = processor.get_last_processed_page(book_id)
    print(f"Book {book_id} - Last processed page: {last_page}")

    # Get pages to process
    pages = processor.get_pages_to_process(book_id, start_page=1)

    if pages:
        print(f"Book {book_id} - Pages needing processing: {len(pages)}")
        print(f"  First page: {pages[0]}")
        print(f"  Last page: {pages[-1]}")
    else:
        print(f"Book {book_id} - No pages need processing")

    print("\n✓ Database operations test completed (no actual writes performed)")


def run_all_tests():
    """Run all tests."""
    print("="*80)
    print("PDF CONTENT TRANSLITERATION PROCESSOR - TEST SUITE")
    print("="*80)

    # Test 1: Database connection
    if not test_database_connection():
        print("\n✗ Database connection failed. Cannot continue tests.")
        return

    # Test 2: Get books
    books = test_get_books()
    if not books:
        print("\n✗ No books found. Cannot continue tests.")
        return

    # Test 3: PDF access
    test_book = test_pdf_access(books)

    # Test 4: Page extraction (if we have a valid book)
    if test_book:
        test_page_extraction(test_book)
        test_database_operations(test_book)

    # Final summary
    print("\n" + "="*80)
    print("TEST SUITE COMPLETED")
    print("="*80)
    print("\nIf all tests passed, you can run the full processor:")
    print("  python src/prod_utils/pdf_content_transliteration_processor.py")
    print("="*80)


if __name__ == "__main__":
    run_all_tests()
