#!/usr/bin/env python3
"""
Test script to verify Devanagari font filtering in PDF extraction.

Tests the new exclude_devanagari parameter on books known to contain
Devanagari/Sanskrit fonts.
"""

import sys
sys.path.insert(0, 'src/prod_utils')

from pdf_content_transliteration_processor import PDFContentTransliterationProcessor
import logging

# Set up logging to see detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_devanagari_filtering():
    """Test Devanagari filtering on a known book."""

    processor = PDFContentTransliterationProcessor()

    # Test Book 100: SriBrihad-Bhagavatamrtam-Canto Oneeng-part1.pdf
    # Known to have AARituPlus2-Bold font (Devanagari)
    test_book = "/opt/pbb_static_content/pbb_pdf_files/SriBrihad-Bhagavatamrtam-Canto Oneeng-part1.pdf"
    test_page = 50  # Test page with Devanagari Sanskrit verses

    print(f"\n{'='*80}")
    print(f"Testing Devanagari Filtering on {test_book} Page {test_page}")
    print(f"{'='*80}\n")

    # Extract WITH Devanagari filtering (default)
    print("1. Extracting WITH Devanagari filtering (exclude_devanagari=True):")
    print("-" * 80)
    text_filtered = processor.extract_page_content(
        test_book,
        test_page,
        exclude_devanagari=True
    )

    if text_filtered:
        print(f"Length: {len(text_filtered)} characters")
        print(f"First 500 chars:\n{text_filtered[:500]}")
    else:
        print("ERROR: No text extracted")

    print("\n")

    # Extract WITHOUT Devanagari filtering
    print("2. Extracting WITHOUT Devanagari filtering (exclude_devanagari=False):")
    print("-" * 80)
    text_unfiltered = processor.extract_page_content(
        test_book,
        test_page,
        exclude_devanagari=False
    )

    if text_unfiltered:
        print(f"Length: {len(text_unfiltered)} characters")
        print(f"First 500 chars:\n{text_unfiltered[:500]}")
    else:
        print("ERROR: No text extracted")

    print("\n")

    # Compare results
    print("3. Comparison:")
    print("-" * 80)
    if text_filtered and text_unfiltered:
        chars_removed = len(text_unfiltered) - len(text_filtered)
        percent_removed = (chars_removed / len(text_unfiltered) * 100) if text_unfiltered else 0

        print(f"Original length: {len(text_unfiltered)} characters")
        print(f"Filtered length: {len(text_filtered)} characters")
        print(f"Removed: {chars_removed} characters ({percent_removed:.1f}%)")

        # Check for garbled characters (indication of Devanagari)
        garbled_before = sum(1 for c in text_unfiltered if ord(c) > 0x0900 and ord(c) < 0x097F)
        garbled_after = sum(1 for c in text_filtered if ord(c) > 0x0900 and ord(c) < 0x097F)

        print(f"\nDevanagari Unicode range characters:")
        print(f"  Before filtering: {garbled_before}")
        print(f"  After filtering: {garbled_after}")

        if chars_removed > 0:
            print("\n✓ SUCCESS: Devanagari filtering is working!")
        else:
            print("\n⚠ WARNING: No characters were filtered on this page")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    test_devanagari_filtering()
