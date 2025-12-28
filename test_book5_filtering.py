#!/usr/bin/env python3
"""
Test Devanagari filtering on Book 5 (Bhagavad-gita 4th edition).
"""

import sys
sys.path.insert(0, 'src/prod_utils')

from pdf_content_transliteration_processor import PDFContentTransliterationProcessor
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_book5():
    """Test on Book 5 which has AARituPlus2-Regular font."""

    processor = PDFContentTransliterationProcessor()

    test_book = "/opt/pbb_static_content/pbb_pdf_files/bhagavad-gita-4ed-eng.pdf"

    # Test page 100 (known to have Devanagari based on font analysis)
    test_page = 100

    print(f"\n{'='*80}")
    print(f"Testing Book 5: bhagavad-gita-4ed-eng.pdf")
    print(f"Page {test_page} (should have AARituPlus2-Regular Devanagari font)")
    print(f"{'='*80}\n")

    # Extract WITH filtering
    print("1. WITH Devanagari filtering (default):")
    print("-" * 80)
    text_filtered = processor.extract_page_content(test_book, test_page)

    if text_filtered:
        print(f"Length: {len(text_filtered)} characters")
        print(f"First 500 chars:\n{text_filtered[:500]}")
    else:
        print("ERROR: No text extracted")

    print("\n")

    # Extract WITHOUT filtering
    print("2. WITHOUT Devanagari filtering:")
    print("-" * 80)
    text_unfiltered = processor.extract_page_content(test_book, test_page, exclude_devanagari=False)

    if text_unfiltered:
        print(f"Length: {len(text_unfiltered)} characters")
        print(f"First 500 chars:\n{text_unfiltered[:500]}")
    else:
        print("ERROR: No text extracted")

    print("\n")

    # Compare
    print("3. Comparison:")
    print("-" * 80)
    if text_filtered and text_unfiltered:
        chars_removed = len(text_unfiltered) - len(text_filtered)
        percent_removed = (chars_removed / len(text_unfiltered) * 100) if text_unfiltered else 0

        print(f"Original length: {len(text_unfiltered)} characters")
        print(f"Filtered length: {len(text_filtered)} characters")
        print(f"Removed: {chars_removed} characters ({percent_removed:.1f}%)")

        if chars_removed > 0:
            print("\n✓ SUCCESS: Devanagari filtering is working on Book 5!")
        else:
            print("\n⚠ WARNING: No Devanagari detected on this page")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    test_book5()
