"""
Simplified Sanskrit Transliteration Utility

Simple utility to fix broken Sanskrit glyphs in extracted PDF text.
Supports conditional replacements based on book IDs for specific books that need custom mappings.

Usage:
    from sanskrit_utils import fix_iast_glyphs
    cleaned_text = fix_iast_glyphs("text with broken glyphs")
    
    # With book-specific replacements
    cleaned_text = fix_iast_glyphs("text with broken glyphs", book_id=56)

Environment Variables:
    SANSKRIT_CONDITIONAL_BOOK_IDS: Comma-separated list of book IDs that need 'ṛ' → 'ā' replacement
    Example: SANSKRIT_CONDITIONAL_BOOK_IDS=56,78,102
    
Note:
    The conditional replacement is applied AFTER standard glyph fixes. This ensures that
    broken glyphs are first converted to proper IAST characters (e.g., '®' → 'ṛ'), and 
    then for specific books, the 'ṛ' is further converted to 'ā' if needed.
"""

import os
from typing import Optional, Set, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_conditional_replacement_book_ids() -> Set[int]:
    """
    Get set of book IDs that need conditional replacements from environment variables.
    
    Returns:
        Set[int]: Set of book IDs that require 'ṛ' → 'ā' replacement
    """
    book_ids_env = os.getenv('SANSKRIT_CONDITIONAL_BOOK_IDS', '')
    if not book_ids_env.strip():
        return set()
    
    book_ids = set()
    for book_id_str in book_ids_env.split(','):
        try:
            book_id = int(book_id_str.strip())
            if book_id > 0:
                book_ids.add(book_id)
        except ValueError:
            # Skip invalid book IDs
            continue
    
    return book_ids

def fix_iast_glyphs(text: str, book_id: Optional[int] = None) -> str:
    """
    Replace broken glyphs (both lowercase and uppercase) with IAST characters.
    
    This function converts corrupted Unicode characters commonly found in
    PDF extraction back to proper IAST (International Alphabet of Sanskrit 
    Transliteration) diacritical marks.
    
    For specific book IDs configured in SANSKRIT_CONDITIONAL_BOOK_IDS environment variable,
    an additional replacement 'ṛ' → 'ā' is applied after the standard replacements.
    
    Args:
        text (str): Input text with potentially broken glyphs
        book_id (Optional[int]): Book ID for conditional replacements
        
    Returns:
        str: Text with corrected IAST characters
        
    Usage:
        cleaned = fix_iast_glyphs("broken glyph text")
        cleaned = fix_iast_glyphs("text with ṛ", book_id=56)  # May convert ṛ → ā
    """
    if not text:
        return text
    
    # Standard glyph replacements
    replacements = {
        # Lowercase mappings
        'ä': 'ā', 'å': 'ṛ', 'ë': 'ṇ', 'é': 'ī', 'ï': 'ñ', 'ç': 'ś', 'ñ': 'ṣ',
        'ö': 'ṭ', 'ü': 'ū', 'ù': 'ḥ', 'ÿ': 'ṁ', 'à': 'ā',

        # Uppercase equivalents
        'Ä': 'Ā', 'Å': 'Ṛ', 'Ë': 'Ṇ', 'É': 'Ī', 'Ï': 'Ñ', 'Ç': 'Ś', 'Ñ': 'Ṣ',
        'Ö': 'Ṭ', 'Ü': 'Ū', 'Ù': 'Ḥ', 'Ÿ': 'Ṁ', 'À': 'Ā',

        # Special Characters
        '®': 'ṛ',   # vocalic r
        'ß': 'ṣ',   # retroflex s
        '√': 'ś',   # palatal s
        'ò': 'ḍ',   # retroflex d
        '†': 'ṭ',   # retroflex t
        '∫': 'ṅ',   # velar n
        '∂': 'ḍ', 
        'µ': 'ṁ' 
        }

    # Apply standard replacements
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    
    # Apply conditional replacements for specific book IDs
    if book_id is not None:
        conditional_book_ids = get_conditional_replacement_book_ids()
        if book_id in conditional_book_ids:
            # Apply the conditional replacement: ṛ → ā
            text = text.replace('ṛ', 'ā')
            text = text.replace('Ṛ', 'Ā')  # Also handle uppercase
    
    return text