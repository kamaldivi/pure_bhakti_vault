#!/usr/bin/env python3
"""
Sanskrit IAST Transliteration Fix System
=========================================

A comprehensive toolkit for fixing OCR and encoding errors in Sanskrit IAST text.

Main Components:
- transliteration_fix_system: Complete 5-stage pipeline for page processing
- sanskrit_diacritic_utils: Core correction functions for word-level processing

Quick Start:
-----------
For full page processing:
    >>> from sanskrit_utils import process_page, print_page_report
    >>> result = process_page(text, page_number=1)
    >>> print(result.corrected_text)
    >>> print_page_report(result, detailed=True)

For single word correction:
    >>> from sanskrit_utils import correct_sanskrit_diacritics
    >>> corrected, rules = correct_sanskrit_diacritics("kåñṇa")
    >>> print(corrected)  # Output: kṛṣṇa

For batch word processing:
    >>> from sanskrit_utils import correct_sanskrit_words
    >>> words = ["kåñṇa", "Bhagavån", "småti"]
    >>> corrected = correct_sanskrit_words(words)
    >>> print(corrected)  # ['kṛṣṇa', 'Bhagavān', 'smṛti']
"""

# Import from transliteration_fix_system (full pipeline)
from .transliteration_fix_system import (
    # Main processing functions
    process_page,
    print_page_report,

    # Core correction functions
    correct_sanskrit_diacritics,
    apply_global_char_map,

    # Text processing
    tokenize_text,
    analyze_tokens,
    classify_word,
    detect_case_pattern,
    correct_word,

    # Validation
    validate_correction,

    # Text reconstruction
    reconstruct_text,

    # Data structures
    ProcessedPage,
    PageStatistics,
    CorrectionResult,
    ValidationReport,
    ValidationIssue,
    Token,

    # Enums
    WordClass,
    TokenType,

    # Configuration
    GLOBAL_CHAR_MAP,
    VALID_IAST_CHARS,
)

# Import from sanskrit_diacritic_utils (word-level utilities)
from .sanskrit_diacritic_utils import (
    correct_n_diacritic,
    correct_a_diacritic,
)

# Version information
__version__ = '1.0.14'
__author__ = 'Sanskrit Text Processing'
__license__ = 'MIT'

# =============================================================================
# Legacy Compatibility Function
# =============================================================================

def fix_iast_glyphs(text: str, book_id: int = None) -> str:
    """
    Legacy compatibility function for code using old sanskrit_utils.py.

    This is a simple wrapper around apply_global_char_map() to maintain
    backward compatibility with existing code that imports fix_iast_glyphs().

    For NEW code, prefer:
    - apply_global_char_map() - Simple character mapping (same as this function)
    - correct_sanskrit_diacritics() - Intelligent context-aware corrections
    - process_page() - Complete 5-stage pipeline with validation

    Args:
        text (str): Input text with potentially broken glyphs
        book_id (int, optional): Book ID (ignored, kept for compatibility)

    Returns:
        str: Text with corrected IAST characters

    Note:
        The new GLOBAL_CHAR_MAP includes all old mappings PLUS new ones:
        - ˇ → Ṭ (v1.0.8)
        - à → ṁ, À → Ṁ (v1.0.9)
        - ï → ñ, Ï → Ñ (v1.0.9)
        - ì → ṅ, Ì → Ṅ (v1.0.12)

        So this function is actually BETTER than the old fix_iast_glyphs()!

    Example:
        >>> text = "kåñëa says oà"
        >>> fixed = fix_iast_glyphs(text)
        >>> print(fixed)
        kṛṣṇa says oṁ
    """
    if not text:
        return text

    # Use the new global char map (same functionality as old, but better!)
    corrected_text, _ = apply_global_char_map(text)
    return corrected_text

# Define what's available when using "from sanskrit_utils import *"
__all__ = [
    # Main functions
    'process_page',
    'print_page_report',
    'correct_sanskrit_diacritics',
    'correct_sanskrit_words',

    # Legacy compatibility
    'fix_iast_glyphs',  # Wrapper for backward compatibility with old code

    # Utilities
    'correct_n_diacritic',
    'correct_a_diacritic',
    'apply_global_char_map',

    # Text processing
    'tokenize_text',
    'analyze_tokens',
    'classify_word',
    'detect_case_pattern',
    'correct_word',

    # Validation
    'validate_correction',

    # Text reconstruction
    'reconstruct_text',

    # Data structures
    'ProcessedPage',
    'PageStatistics',
    'CorrectionResult',
    'ValidationReport',
    'ValidationIssue',
    'Token',

    # Enums
    'WordClass',
    'TokenType',

    # Configuration
    'GLOBAL_CHAR_MAP',
    'VALID_IAST_CHARS',

    # Testing
    'test_corrections',
]
