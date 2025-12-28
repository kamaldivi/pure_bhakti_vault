#!/usr/bin/env python3
"""
Analyze fonts on a specific page to understand Devanagari text blocks.
"""

import sys
sys.path.insert(0, 'src/prod_utils')
import fitz  # PyMuPDF

def analyze_page_fonts(pdf_path, page_num):
    """Analyze all fonts used on a specific page."""

    print(f"\nAnalyzing fonts on page {page_num} of:")
    print(f"{pdf_path}\n")
    print("=" * 100)

    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]  # 0-indexed

    # Get text with font information
    text_dict = page.get_text("dict")

    font_spans = {}
    total_spans = 0

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                total_spans += 1
                font_name = span.get("font", "Unknown")
                text = span.get("text", "")

                if font_name not in font_spans:
                    font_spans[font_name] = []

                font_spans[font_name].append({
                    'text': text[:100],  # First 100 chars
                    'size': span.get("size", 0),
                })

    # Print summary
    print(f"Total text spans: {total_spans}")
    print(f"Unique fonts: {len(font_spans)}")
    print("=" * 100)

    # Print details for each font
    for font_name, spans in sorted(font_spans.items()):
        print(f"\nFont: {font_name}")
        print(f"Spans: {len(spans)}")
        print("-" * 100)

        # Show first 3 examples
        for i, span in enumerate(spans[:3]):
            print(f"  Example {i+1}: {span['text'][:80]}...")
            print(f"              Size: {span['size']:.1f}pt")

    doc.close()


if __name__ == "__main__":
    # Test on Book 100 which has visible Devanagari
    analyze_page_fonts(
        "/opt/pbb_static_content/pbb_pdf_files/SriBrihad-Bhagavatamrtam-Canto Oneeng-part1.pdf",
        50
    )

    print("\n" + "=" * 100)
    print("\nNow testing Book 28:")
    print("=" * 100)

    analyze_page_fonts(
        "/opt/pbb_static_content/pbb_pdf_files/hari_kathamrita_vol1.pdf",
        55
    )
