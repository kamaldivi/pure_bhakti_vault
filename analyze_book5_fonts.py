#!/usr/bin/env python3
"""
Analyze all fonts used in bhagavad-gita-4ed-eng.pdf (Book 5).
"""

import fitz

pdf_path = "/opt/pbb_static_content/pbb_pdf_files/bhagavad-gita-4ed-eng.pdf"

print(f"Analyzing: {pdf_path}")
print("=" * 100)

doc = fitz.open(pdf_path)

# Collect all unique fonts across all pages
all_fonts = set()
font_pages = {}  # Track which pages use which fonts

for page_num in range(len(doc)):
    page = doc[page_num]

    # Get fonts for this page
    fonts_dict = page.get_fonts(full=True)

    for font_info in fonts_dict:
        # font_info is a tuple: (xref, ext, type, basefont, name, encoding, embedded)
        font_name = font_info[3]  # basefont

        if font_name:
            all_fonts.add(font_name)

            if font_name not in font_pages:
                font_pages[font_name] = []
            font_pages[font_name].append(page_num + 1)  # 1-indexed

doc.close()

# Print summary
print(f"\nTotal unique fonts: {len(all_fonts)}")
print("=" * 100)

# Check for Devanagari fonts
devanagari_indicators = [
    'devanagari', 'sanskrit', 'hindi', 'bengali', 'mangal',
    'siddhanta', 'chandas', 'aaritu', 'narad', 'kruti'
]

devanagari_fonts_found = []

for font in sorted(all_fonts):
    font_lower = font.lower()
    is_devanagari = any(indicator in font_lower for indicator in devanagari_indicators)

    if is_devanagari:
        devanagari_fonts_found.append(font)
        pages = font_pages[font]
        page_range = f"{min(pages)}-{max(pages)}" if len(pages) > 1 else str(pages[0])
        print(f"✓ DEVANAGARI: {font}")
        print(f"  Pages: {page_range} ({len(pages)} total pages)")
    else:
        print(f"  Regular: {font}")

print("\n" + "=" * 100)
if devanagari_fonts_found:
    print(f"FOUND {len(devanagari_fonts_found)} DEVANAGARI FONTS:")
    for font in devanagari_fonts_found:
        print(f"  - {font}")
else:
    print("❌ NO DEVANAGARI FONTS DETECTED")
    print("\nChecking for fonts that might be Devanagari but not in our patterns...")

    # Look for fonts that might be Devanagari based on unusual names
    suspicious_fonts = []
    for font in sorted(all_fonts):
        # Skip common English fonts
        common_fonts = ['times', 'arial', 'helvetica', 'garamond', 'palatino',
                       'courier', 'gothic', 'minion', 'myriad', 'calibri',
                       'aver', 'gaudiya', 'copperplate']

        is_common = any(common in font.lower() for common in common_fonts)

        if not is_common:
            suspicious_fonts.append(font)

    if suspicious_fonts:
        print("\nSUSPICIOUS/UNKNOWN FONTS (might be Devanagari):")
        for font in suspicious_fonts:
            pages = font_pages[font]
            page_range = f"{min(pages)}-{max(pages)}" if len(pages) > 1 else str(pages[0])
            print(f"  - {font}")
            print(f"    Pages: {page_range} ({len(pages)} total pages)")
