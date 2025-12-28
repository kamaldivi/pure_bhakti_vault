#!/usr/bin/env python3
"""
Search for à and ï characters in PDF text to understand their usage.
"""

import fitz
import os
import re

pdf_folder = "/opt/pbb_static_content/pbb_pdf_files/"

# Sample a few PDFs
test_pdfs = [
    "bhagavad-gita-4ed-eng.pdf",  # Book 5 - heavily used
    "hari_kathamrita_vol1.pdf",   # Book 28
    "Essence_of_all_advice_4ed.pdf",  # Book with Sanskrit
]

print("Searching for à and ï in PDFs")
print("=" * 100)

a_grave_examples = []
i_diaeresis_examples = []

for pdf_file in test_pdfs:
    pdf_path = os.path.join(pdf_folder, pdf_file)

    if not os.path.exists(pdf_path):
        continue

    print(f"\nScanning: {pdf_file}")
    print("-" * 100)

    try:
        doc = fitz.open(pdf_path)

        # Sample first 50 pages
        for page_num in range(min(50, len(doc))):
            page = doc[page_num]
            text = page.get_text()

            # Search for à
            if 'à' in text:
                # Get context around the character
                for match in re.finditer(r'.{0,30}à.{0,30}', text):
                    context = match.group(0).replace('\n', ' ').strip()
                    a_grave_examples.append({
                        'pdf': pdf_file,
                        'page': page_num + 1,
                        'context': context
                    })

            # Search for ï
            if 'ï' in text:
                for match in re.finditer(r'.{0,30}ï.{0,30}', text):
                    context = match.group(0).replace('\n', ' ').strip()
                    i_diaeresis_examples.append({
                        'pdf': pdf_file,
                        'page': page_num + 1,
                        'context': context
                    })

        doc.close()

    except Exception as e:
        print(f"Error processing {pdf_file}: {e}")

print("\n" + "=" * 100)
print(f"\n1. FOUND {len(a_grave_examples)} instances of 'à' (a with grave accent)")
print("=" * 100)

if a_grave_examples:
    print("\nFirst 20 examples:")
    for i, example in enumerate(a_grave_examples[:20], 1):
        print(f"\n{i}. {example['pdf']}, Page {example['page']}:")
        # Highlight the character
        highlighted = example['context'].replace('à', '>>à<<')
        print(f"   ...{highlighted}...")

print("\n" + "=" * 100)
print(f"\n2. FOUND {len(i_diaeresis_examples)} instances of 'ï' (i with diaeresis)")
print("=" * 100)

if i_diaeresis_examples:
    print("\nFirst 20 examples:")
    for i, example in enumerate(i_diaeresis_examples[:20], 1):
        print(f"\n{i}. {example['pdf']}, Page {example['page']}:")
        highlighted = example['context'].replace('ï', '>>ï<<')
        print(f"   ...{highlighted}...")

# Analysis
print("\n" + "=" * 100)
print("\nANALYSIS:")
print("=" * 100)

if a_grave_examples:
    print("\nFor 'à' → 'ṁ':")
    # Check if all instances are Sanskrit-like
    sanskrit_pattern = re.compile(r'[āīūṛṝḷḹṅñṭḍṇśṣṁṃḥ]')
    sanskrit_contexts = sum(1 for ex in a_grave_examples if sanskrit_pattern.search(ex['context']))
    print(f"  Total instances: {len(a_grave_examples)}")
    print(f"  Contexts with Sanskrit diacritics: {sanskrit_contexts}")
    print(f"  Percentage in Sanskrit context: {sanskrit_contexts/len(a_grave_examples)*100:.1f}%")

    # Check for French words
    french_indicators = ['déjà', 'voilà', 'café', 'à la', 'là']
    french_contexts = sum(1 for ex in a_grave_examples
                         if any(word in ex['context'].lower() for word in french_indicators))
    if french_contexts > 0:
        print(f"  ⚠️  French contexts found: {french_contexts}")

if i_diaeresis_examples:
    print("\nFor 'ï' → 'ñ':")
    sanskrit_contexts = sum(1 for ex in i_diaeresis_examples if sanskrit_pattern.search(ex['context']))
    print(f"  Total instances: {len(i_diaeresis_examples)}")
    print(f"  Contexts with Sanskrit diacritics: {sanskrit_contexts}")
    print(f"  Percentage in Sanskrit context: {sanskrit_contexts/len(i_diaeresis_examples)*100:.1f}%")

    # Check for legitimate English words
    legitimate_words = ['naïve', 'naïf', 'maïs']
    legit_contexts = sum(1 for ex in i_diaeresis_examples
                        if any(word in ex['context'].lower() for word in legitimate_words))
    if legit_contexts > 0:
        print(f"  ⚠️  Legitimate English/French words found: {legit_contexts}")

print("\n" + "=" * 100)
print("\nRECOMMENDATION:")
print("=" * 100)

if not a_grave_examples and not i_diaeresis_examples:
    print("No instances found in sampled PDFs. Need more data to make recommendation.")
elif a_grave_examples or i_diaeresis_examples:
    print("""
Based on the examples above:

✓ SAFE to add as global mapping IF:
  - 95%+ of instances are in Sanskrit IAST context
  - No legitimate French/Spanish/English words affected

⚠️  NOT SAFE if:
  - Legitimate non-Sanskrit words are present
  - Less than 90% are clear OCR errors

Review the examples above to make the final decision.
""")
