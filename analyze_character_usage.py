#!/usr/bin/env python3
"""
Analyze usage of à and ï in the database to determine if they can be
safely mapped to ṁ and ñ globally.
"""

import psycopg2
import re

conn = psycopg2.connect(
    host='localhost',
    database='pbb',
    user='postgres',
    password='test123'
)

print("Analyzing character usage in database")
print("=" * 100)

# Character 1: à → ṁ
print("\n1. ANALYZING: à (LATIN SMALL LETTER A WITH GRAVE) → ṁ (M WITH DOT ABOVE)")
print("-" * 100)

cur = conn.cursor()

# Search for à in ai_page_content
cur.execute("""
    SELECT book_id, page_number,
           substring(ai_page_content from position('à' in ai_page_content) - 20 for 60) as context
    FROM content
    WHERE ai_page_content LIKE '%à%'
    LIMIT 20
""")

results = cur.fetchall()
print(f"Found {cur.rowcount} pages with 'à' character")

if results:
    print("\nSample contexts (20 examples):")
    print("-" * 100)
    for book_id, page_num, context in results[:20]:
        # Clean up and highlight the character
        context = context.strip() if context else ""
        context_clean = context.replace('\n', ' ').replace('\r', ' ')
        # Highlight à
        context_highlighted = context_clean.replace('à', '**à**')
        print(f"Book {book_id}, Page {page_num}:")
        print(f"  ...{context_highlighted}...")
        print()

# Get total count
cur.execute("SELECT COUNT(*) FROM content WHERE ai_page_content LIKE '%à%'")
total_a_grave = cur.fetchone()[0]
print(f"Total pages with 'à': {total_a_grave}")

# Character 2: ï → ñ
print("\n" + "=" * 100)
print("\n2. ANALYZING: ï (LATIN SMALL LETTER I WITH DIAERESIS) → ñ (N WITH TILDE)")
print("-" * 100)

cur.execute("""
    SELECT book_id, page_number,
           substring(ai_page_content from position('ï' in ai_page_content) - 20 for 60) as context
    FROM content
    WHERE ai_page_content LIKE '%ï%'
    LIMIT 20
""")

results = cur.fetchall()
print(f"Found {cur.rowcount} pages with 'ï' character")

if results:
    print("\nSample contexts (20 examples):")
    print("-" * 100)
    for book_id, page_num, context in results[:20]:
        context = context.strip() if context else ""
        context_clean = context.replace('\n', ' ').replace('\r', ' ')
        context_highlighted = context_clean.replace('ï', '**ï**')
        print(f"Book {book_id}, Page {page_num}:")
        print(f"  ...{context_highlighted}...")
        print()

# Get total count
cur.execute("SELECT COUNT(*) FROM content WHERE ai_page_content LIKE '%ï%'")
total_i_diaeresis = cur.fetchone()[0]
print(f"Total pages with 'ï': {total_i_diaeresis}")

# Analysis: Check for legitimate French/Spanish text
print("\n" + "=" * 100)
print("\n3. CHECKING FOR LEGITIMATE NON-SANSKRIT USAGE")
print("-" * 100)

# French words with à: à, déjà, voilà, là, etc.
# Spanish words with ñ: señor, mañana, niño, etc.
# French words with ï: naïve, Noël (rare in English)

french_words = ['déjà', 'voilà', 'café', 'cliché', 'blasé']
spanish_words = ['señor', 'mañana', 'niño', 'español']

print("\nChecking for common French words with 'à':")
for word in french_words:
    cur.execute(f"SELECT COUNT(*) FROM content WHERE ai_page_content ILIKE '%{word}%'")
    count = cur.fetchone()[0]
    if count > 0:
        print(f"  '{word}': {count} occurrences ⚠️")

print("\nChecking for common Spanish words with 'ñ' (not ï, but related):")
for word in spanish_words:
    cur.execute(f"SELECT COUNT(*) FROM content WHERE ai_page_content ILIKE '%{word}%'")
    count = cur.fetchone()[0]
    if count > 0:
        print(f"  '{word}': {count} occurrences")

print("\nChecking for 'naïve' (legitimate English word with ï):")
cur.execute("SELECT COUNT(*) FROM content WHERE ai_page_content ILIKE '%naïve%'")
count = cur.fetchone()[0]
print(f"  'naïve': {count} occurrences {'⚠️' if count > 0 else ''}")

cur.close()
conn.close()

print("\n" + "=" * 100)
print("\nRECOMMENDATION:")
print("=" * 100)
print("""
Based on the analysis above:

1. **à → ṁ**:
   - If à appears ONLY in Sanskrit IAST context (like 'haà', 'oà', 'Kṛñà', etc.)
   - AND does NOT appear in legitimate French words
   - THEN it's SAFE to add as global mapping

2. **ï → ñ**:
   - If ï appears ONLY as OCR error for ñ in Sanskrit
   - AND does NOT appear in legitimate English/French words like 'naïve'
   - THEN it's SAFE to add as global mapping

If either character appears in legitimate non-Sanskrit contexts, we should NOT
add it as a global mapping (or add it with careful consideration).
""")
