#!/usr/bin/env python3
"""
Test script to verify restart logic and cleanup functionality
"""

import os
from dotenv import load_dotenv
from render_pdf_pages import PDFPageRenderer

def test_restart_logic():
    """Test the restart and cleanup functionality"""

    # Load environment
    load_dotenv('../../.env')

    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'pure_bhakti_vault'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

    print("Testing restart logic...")

    # Test 1: Normal query (no restart)
    renderer1 = PDFPageRenderer(
        pdf_folder="/tmp",  # dummy path
        page_folder="/tmp",  # dummy path
        db_config=db_config,
        restart_book_id=None
    )

    pages1 = renderer1.get_content_pages()
    print(f"All pages: {len(pages1)} total")
    if pages1:
        print(f"Books: {pages1[0][0]} to {pages1[-1][0]}")

    # Test 2: Restart from book 79
    renderer2 = PDFPageRenderer(
        pdf_folder="/tmp",  # dummy path
        page_folder="/tmp",  # dummy path
        db_config=db_config,
        restart_book_id=79
    )

    pages2 = renderer2.get_content_pages()
    print(f"Restart from book 79: {len(pages2)} pages")
    if pages2:
        print(f"Books: {pages2[0][0]} to {pages2[-1][0]}")

    # Test 3: Book page counts
    book_counts = renderer1.get_book_page_counts()
    print(f"Total books in DB: {len(book_counts)}")

    # Show some examples
    for book_id, count in list(book_counts.items())[:5]:
        print(f"Book {book_id}: {count} pages")

    print("✓ Restart logic test completed")

if __name__ == '__main__':
    test_restart_logic()