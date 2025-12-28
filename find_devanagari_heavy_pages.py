#!/usr/bin/env python3
"""
Find pages in Book 5 with heavy Devanagari content.
"""

import fitz

pdf_path = "/opt/pbb_static_content/pbb_pdf_files/bhagavad-gita-4ed-eng.pdf"

print(f"Scanning: {pdf_path}")
print("Looking for pages with high Devanagari font usage...\n")

doc = fitz.open(pdf_path)

pages_with_devanagari = []

# Check pages 71-150 (where Devanagari starts)
for page_num in range(70, min(150, len(doc))):
    page = doc[page_num]

    # Get text with font info
    text_dict = page.get_text("dict")

    total_spans = 0
    devanagari_spans = 0

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                total_spans += 1
                font_name = span.get("font", "")

                if 'aaritu' in font_name.lower():
                    devanagari_spans += 1

    if devanagari_spans > 0:
        percent = (devanagari_spans / total_spans * 100) if total_spans > 0 else 0
        pages_with_devanagari.append({
            'page': page_num + 1,  # 1-indexed
            'total': total_spans,
            'devanagari': devanagari_spans,
            'percent': percent
        })

doc.close()

# Sort by percentage of Devanagari content
pages_with_devanagari.sort(key=lambda x: x['percent'], reverse=True)

print("Top 10 pages with most Devanagari content:")
print("=" * 80)
print(f"{'Page':<8} {'Total Spans':<15} {'Devanagari':<15} {'Percent':<10}")
print("-" * 80)

for i, page_info in enumerate(pages_with_devanagari[:10]):
    print(f"{page_info['page']:<8} {page_info['total']:<15} {page_info['devanagari']:<15} {page_info['percent']:.1f}%")

if pages_with_devanagari:
    print("\n" + "=" * 80)
    print(f"Try testing on page {pages_with_devanagari[0]['page']} which has {pages_with_devanagari[0]['percent']:.1f}% Devanagari")
