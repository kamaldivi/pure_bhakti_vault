#!/usr/bin/env python3
"""
Comprehensive scan of ALL 98 books for Devanagari fonts.
This time scan ALL pages (or at least sample more pages).
"""

import fitz
import os

pdf_folder = "/opt/pbb_static_content/pbb_pdf_files/"

# Devanagari font indicators
devanagari_indicators = [
    'devanagari', 'sanskrit', 'hindi', 'bengali', 'mangal',
    'siddhanta', 'chandas', 'aaritu', 'narad', 'kruti'
]

def has_devanagari_fonts(pdf_path, sample_pages=20):
    """Check if PDF has Devanagari fonts by sampling pages."""
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # Sample evenly distributed pages
        if total_pages <= sample_pages:
            pages_to_check = range(total_pages)
        else:
            step = total_pages // sample_pages
            pages_to_check = range(0, total_pages, step)

        devanagari_fonts_found = set()

        for page_num in pages_to_check:
            page = doc[page_num]
            fonts_dict = page.get_fonts(full=True)

            for font_info in fonts_dict:
                font_name = font_info[3]  # basefont
                if font_name:
                    font_lower = font_name.lower()
                    if any(indicator in font_lower for indicator in devanagari_indicators):
                        devanagari_fonts_found.add(font_name)

        doc.close()
        return list(devanagari_fonts_found)

    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return []


print("Comprehensive Devanagari Font Scan")
print("=" * 100)
print("Scanning all PDFs in /opt/pbb_static_content/pbb_pdf_files/")
print("Sampling 20 pages per book for Devanagari fonts...")
print("=" * 100)

# Get all PDF files
pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith('.pdf')]
pdf_files.sort()

books_with_devanagari = []

for i, pdf_file in enumerate(pdf_files, 1):
    pdf_path = os.path.join(pdf_folder, pdf_file)
    print(f"[{i}/{len(pdf_files)}] Scanning: {pdf_file}...", end=" ")

    fonts = has_devanagari_fonts(pdf_path)

    if fonts:
        print(f"✓ FOUND Devanagari!")
        books_with_devanagari.append({
            'file': pdf_file,
            'fonts': fonts
        })
    else:
        print("No Devanagari")

print("\n" + "=" * 100)
print(f"SUMMARY: {len(books_with_devanagari)} books with Devanagari fonts")
print("=" * 100)

for i, book in enumerate(books_with_devanagari, 1):
    print(f"\n{i}. {book['file']}")
    for font in book['fonts']:
        print(f"   - {font}")
