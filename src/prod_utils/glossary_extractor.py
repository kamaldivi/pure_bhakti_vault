#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Clean Database-Integrated Glossary Extractor

SIMPLIFIED APPROACH:
- Queries the book database for books with non-null glossary_pages ranges (int4range format)
- Reads original PDFs from PDF_FOLDER environment variable  
- Uses PageContentExtractor to extract clean content from ONLY glossary page ranges
- Automatically excludes headers/footers based on precise database metadata
- Simple text-based glossary segmentation (ready for improvement)

FEATURES:
- Database-driven processing (no manual PDF splitting needed)
- Precise page range extraction using PageContentExtractor utility
- Clean, simplified codebase without complex legacy processing
- Sanskrit glyph correction via PageContentExtractor with conditional book ID support
- Single combined CSV output

USAGE:
    python glossary_extractor.py [--verbose]

OUTPUT:
    - Appends to Google Sheets 'glossary' tab
    - Structured format: book_id, pdf_name, term, description
    - All entries appended for manual review (no duplicate checking)
    - Enhanced parsing separates terms from descriptions

FEATURES OF ENHANCED PARSING:
    - Intelligent term/description separation using multiple heuristics
    - Noise filtering (removes section headers, page numbers, decorations)
    - Alphabetical consistency checking to reduce false positives
    - Handles both inline separators (term: description) and multi-line entries
"""

from __future__ import annotations
import re
import os
import sys
import argparse
import unicodedata
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()

# ---------- Paths ----------
PDF_FOLDER = Path(os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books/'))
OUT_DIR = Path("/Users/kamaldivi/Development/process_folder/SFILES/GLOSSARY/py_extracted")

# Import utilities
from page_content_extractor import PageContentExtractor, ExtractionType
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError


# ---------- Config knobs ----------
MAX_TERM_WORDS = 8          # term candidate lines with <= this many words

# Enhanced parsing configuration
MAX_TERM_WORDS_ENHANCED = 10              # term-only fallback: max words to still look like a term
MAX_TERM_LEN = 150                        # hard cap: prevents absorbing whole paragraphs as "term"
SOFT_ENDERS = ('.', '?', '!', ';', '।', ')')  # treat as sentence-ish closers

# Regexes for noise filtering
RE_GLOSSARY_HEADER = re.compile(r'(?i)^\s*g[\.\s-]*l[\.\s-]*o[\.\s-]*s[\.\s-]*s[\.\s-]*a[\.\s-]*r[\.\s-]*y\s*:?\s*$')
RE_SINGLE_LETTER  = re.compile(r'^[A-Za-z]$')
RE_ALPHA_BANNER   = re.compile(r'^\s*[\-–—•\*]?\s*[A-Za-z]\s*[\-–—•\*]?\s*$')
RE_AZ_GUIDE       = re.compile(r'^\s*[A-Za-z]\s*([/\-–—]|to)\s*[A-Za-z]\s*$')
RE_PAGE_MARK      = re.compile(r'^\s*\(?[ivxlcdmIVXLCDM\d]+\)?\s*$')
RE_ORNAMENT       = re.compile(r'^[\-\–\—\_\=\.\·\•\*]{3,}\s*$')

# Separator characters for term/definition splitting
SEP_CHARS = {':', '-', '–', '—'}
# ----------------------------------------------------


def clean_text(s: str) -> str:
    """Basic text cleaning for extracted content."""
    s = re.sub(r"[·•∙⋅]", "", s)      # bullets
    s = re.sub(r"\.{3,}", "…", s)     # ellipsis
    s = re.sub(r"[ \t]+", " ", s)     # collapse spaces
    return s.strip()


def is_alpha_section_header(s: str) -> bool:
    """Check if text is a single letter section header (A, B, C, etc.)"""
    return bool(re.fullmatch(r"[A-Z]", s))


def is_probable_page_number(s: str) -> bool:
    """Check if text looks like a page number."""
    # Simple numeric or roman numeral check
    return bool(re.fullmatch(r"\d{1,4}", s) or re.fullmatch(r"[ivxlcdmIVXLCDM]+", s))


class GlossaryExtractor:
    """Enhanced glossary extractor that works with the database to find books with glossary ranges."""
    
    def __init__(self, db_params: Optional[Dict[str, str]] = None):
        """Initialize the glossary extractor."""
        self.db = PureBhaktiVaultDB(db_params)
        self.page_extractor = PageContentExtractor()
        self.pdf_folder = PDF_FOLDER
        
        # Validate PDF folder
        if not self.pdf_folder.exists():
            raise ValueError(f"PDF folder does not exist: {self.pdf_folder}")
    
    def get_books_with_glossary_ranges(self) -> List[Dict[str, Any]]:
        """Get all books that have non-null glossary page ranges."""
        try:
            query = """
                SELECT book_id, original_book_title, english_book_title, pdf_name, glossary_pages
                FROM book 
                WHERE glossary_pages IS NOT NULL
                ORDER BY book_id
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                
                books = []
                for row in results:
                    # Parse the glossary range
                    glossary_range = self._parse_page_range(row['glossary_pages'])
                    if glossary_range:
                        books.append({
                            'book_id': row['book_id'],
                            'original_title': row['original_book_title'],
                            'english_title': row['english_book_title'],
                            'pdf_name': row['pdf_name'],
                            'glossary_pages_raw': row['glossary_pages'],
                            'glossary_range': glossary_range
                        })
                
                print(f"Found {len(books)} books with glossary page ranges")
                return books
                
        except DatabaseError as e:
            print(f"Database error getting books with glossary ranges: {e}")
            return []
    
    def _parse_page_range(self, range_obj) -> Optional[range]:
        """Parse PostgreSQL int4range object to Python range."""
        if not range_obj:
            return None
        
        try:
            # Handle PostgreSQL NumericRange object
            if hasattr(range_obj, 'lower') and hasattr(range_obj, 'upper'):
                start = range_obj.lower if range_obj.lower is not None else 0
                end = range_obj.upper if range_obj.upper is not None else 0
                
                if start > 0 and end > start:
                    return range(start, end)  # NumericRange upper is exclusive
                return None
            
            # Handle string representation like '[1,10)'
            range_str = str(range_obj)
            if not range_str or range_str.lower() == 'none':
                return None
            
            # Remove brackets and split
            clean_range = range_str.strip('[]()').split(',')
            if len(clean_range) != 2:
                return None
            
            start = int(clean_range[0].strip())
            end = int(clean_range[1].strip())
            
            # Adjust for inclusive/exclusive bounds
            if range_str.endswith(')'):
                return range(start, end)  # Exclusive end
            else:
                return range(start, end + 1)  # Inclusive end
                
        except (ValueError, AttributeError, TypeError):
            return None
    
    def extract_glossary_content_from_book(self, book_info: Dict[str, Any]) -> List[str]:
        """Extract glossary content from a specific book using its glossary page range."""
        pdf_name = book_info['pdf_name']
        glossary_range = book_info['glossary_range']
        book_id = book_info['book_id']
        
        print(f"Processing book ID {book_id}: {book_info['original_title']}")
        print(f"  PDF: {pdf_name}")
        print(f"  Glossary pages: {list(glossary_range)}")
        
        # Check if PDF exists
        pdf_path = self.pdf_folder / pdf_name
        if not pdf_path.exists():
            print(f"  Warning: PDF not found at {pdf_path}")
            return []
        
        # Extract content from glossary pages only
        all_content = []
        
        try:
            for page_num in glossary_range:
                try:
                    content = self.page_extractor.extract_page_content(pdf_name, page_num, ExtractionType.BODY)
                    if content and content.strip():
                        all_content.append(content.strip())
                        print(f"    Page {page_num}: {len(content)} chars extracted")
                    else:
                        print(f"    Page {page_num}: No content extracted")
                except Exception as e:
                    print(f"    Page {page_num}: Failed to extract - {e}")
                    continue
            
            print(f"  Total pages with content: {len(all_content)}")
            return all_content
            
        except Exception as e:
            print(f"  Error extracting from {pdf_name}: {e}")
            return []
    
    def process_all_glossary_books(self) -> Dict[str, Any]:
        """Process all books with glossary ranges and extract their content."""
        # Get books with glossary ranges
        books = self.get_books_with_glossary_ranges()
        
        if not books:
            print("No books with glossary ranges found")
            return {}
        
        results = {}
        
        for book in books:
            book_id = book['book_id']
            pdf_name = book['pdf_name']
            
            try:
                # Extract content
                page_contents = self.extract_glossary_content_from_book(book)
                
                if page_contents:
                    # Join all page contents
                    full_text = "\n\n".join(page_contents)
                    
                    # Use enhanced parsing to extract structured glossary entries
                    parsed_entries = parse_glossary_block(book_id, full_text)
                    
                    results[pdf_name] = {
                        'book_info': book,
                        'page_contents': page_contents,
                        'parsed_entries': parsed_entries,
                        'total_entries': len(parsed_entries)
                    }
                    
                    print(f"  Successfully extracted {len(parsed_entries)} structured glossary entries")
                else:
                    print(f"  No content extracted from {pdf_name}")
            
            except Exception as e:
                print(f"Error processing book {book_id} ({pdf_name}): {e}")
                continue
        
        return results


# NOTE: extract_glossary_blocks_from_text function removed as it was unused
# The main processing now uses parse_glossary_block with PageContentExtractor
# which already applies Sanskrit glyph fixes with book_id support


def is_new_glossary_entry(paragraph: str) -> bool:
    """
    Simple heuristic to determine if a paragraph starts a new glossary entry.
    
    This is a placeholder for more sophisticated logic we'll develop.
    """
    # Check for inline separators (term — definition)
    if has_inline_separator(paragraph):
        # Exclude obvious headers
        if paragraph.lower().strip() in {"glossary", "glossary of terms"}:
            return False
        return True
    
    # Check for short title-case terms (basic pattern)
    words = paragraph.split()
    if len(words) <= MAX_TERM_WORDS and len(words) > 0:
        first_line = paragraph.split('\n')[0].strip()
        
        # Title case pattern or Sanskrit terms
        if re.match(r'^[A-ZĀĪŪṚṜḶḸṄÑṆṬḌŚṢṂḤ][a-zA-Zāīūṛṝḷḹṅñṇṭḍśṣṃḥ\s\-\']{1,80}$', first_line):
            # Don't treat sentences ending with periods as terms
            if not first_line.endswith('.'):
                return True
    
    return False


def has_inline_separator(text: str) -> bool:
    """
    Check if text contains a plausible term/definition separator.
    """
    # Common patterns: term — definition, term: definition, etc.
    sep_patterns = [r"\s—\s", r"\s–\s", r"\s-\s", r":\s", r"\s—$", r"\s–$", r"\s-$", r":$"]
    return any(re.search(pattern, text) for pattern in sep_patterns)


# ============================================================
# ENHANCED GLOSSARY PARSING FUNCTIONS
# ============================================================

def normalize_spaces(s: str) -> str:
    """Normalize whitespace in text."""
    return re.sub(r'\s+', ' ', s).strip()


def is_noise_line(line: str) -> bool:
    """Check if line is noise (headers, decorations, etc.) that should be filtered out."""
    l = line.strip()
    if not l:
        return True
    if RE_GLOSSARY_HEADER.fullmatch(l): return True
    if RE_SINGLE_LETTER.fullmatch(l): return True
    if RE_ALPHA_BANNER.fullmatch(l): return True
    if RE_AZ_GUIDE.fullmatch(l): return True
    if RE_PAGE_MARK.fullmatch(l): return True
    if RE_ORNAMENT.fullmatch(l): return True
    return False


def splitlines_clean(block: str) -> List[str]:
    """Split block into clean lines, removing empty lines."""
    out = []
    for ln in (block or "").splitlines():
        ln = normalize_spaces(ln)
        if ln:
            out.append(ln)
    return out


def strip_term(term: str) -> str:
    """Clean up term by removing trailing punctuation."""
    term = term.strip()
    # remove trailing punctuation/brackets commonly bleeding into term
    term = term.rstrip(':;.,-–—()[]{}')
    return normalize_spaces(term)


def contains_common_english_words(term: str) -> bool:
    """
    Check if term contains common English words that indicate it's likely
    part of a description rather than a proper glossary term.
    """
    # Common English words that shouldn't appear as standalone words in glossary terms
    common_words = {
        'the', 'are', 'them', 'is', 'which', 'if', 'and', 'or', 'of', 'in', 'to', 
        'for', 'with', 'by', 'from', 'as', 'at', 'on', 'be', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
        'can', 'must', 'shall', 'this', 'that', 'these', 'those', 'a', 'an',
        'but', 'not', 'so', 'then', 'now', 'here', 'there', 'when', 'where',
        'how', 'what', 'who', 'why', 'all', 'any', 'some', 'each', 'every',
        'both', 'either', 'neither', 'one', 'two', 'first', 'second', 'third',
        'other', 'another', 'such', 'only', 'also', 'even', 'just', 'very',
        'more', 'most', 'much', 'many', 'few', 'little', 'less', 'than',
        'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down',
        'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once',
        'literally', 'means', 'refers', 'called', 'known', 'used', 'made',
        'given', 'taken', 'derived', 'comes', 'goes', 'being', 'been',
        'literally', 'meaning', 'called', 'refers', 'used', 'known', 'our'
    }
    
    # Split term into words and check each
    words = term.lower().split()
    
    # Check if any complete word matches common English words
    for word in words:
        # Remove common punctuation and check if it's a common word
        clean_word = word.strip('.,;:!?"-()[]{}').lower()
        if clean_word in common_words:
            return True
    
    return False


def is_likely_header(term: str, position: int) -> bool:
    """
    Check if a term is likely a section header rather than a glossary term.
    """
    term_lower = term.lower().strip()
    
    # Common header patterns
    header_patterns = {
        'glossary', 'glossary terms', 'glossary of terms', 'terms', 'definitions',
        'vocabulary', 'sanskrit terms', 'sanskrit glossary', 'arcana terms',
        'bhakti terms', 'vedic terms', 'spiritual terms'
    }
    
    # Check if it matches header patterns
    if term_lower in header_patterns:
        return True
    
    # If it's the very first entry and contains "terms" or "glossary"
    if position == 0 and ('terms' in term_lower or 'glossary' in term_lower):
        return True
    
    # Check for section divider patterns (single letters, roman numerals)
    if len(term.strip()) == 1 and term.strip().isupper():
        return True
    
    return False


def is_title_like(s: str) -> bool:
    """Check if text looks like a title (starts uppercase or is ALL CAPS)."""
    s = s.strip()
    if not s: return False
    # title-ish if starts uppercase or is ALL CAPS (but not too long)
    return s[0].isupper() or (s.isupper() and len(s) <= 40)


def normalize_key(s: str) -> str:
    """Normalize text for alphabetical comparison."""
    # fold accents, keep letters/digits/spaces only, lowercase
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
    return normalize_spaces(s).lower()


def detect_book_separator_pattern(raw_content: str) -> str:
    """
    Analyze raw content to detect the dominant separator pattern for this book.
    Returns the separator pattern identifier.
    """
    lines = [ln.strip() for ln in raw_content.splitlines() if ln.strip()][:100]  # Sample first 100 lines
    
    pattern_counts = {
        'space_long_dash_space': 0,    # " – " or " – "
        'space_short_dash_space': 0,   # " - "
        'colon_space': 0,              # ": "
        'all_caps_space': 0,           # "ALL CAPS rest"
        'line_break': 0                # "Term\nDescription"
    }
    
    # Look for separators - prioritize explicit separators over line breaks
    separator_found = False
    
    for line in lines:
        # Check for various dash types (em dash, en dash, hyphen)
        if (' – ' in line or ' — ' in line or 
            ((' - ' in line) and (len([w for w in line.split(' - ')[0].split() if len(w) > 2]) <= 3))):
            # Long/en dash or short dash with short term before it
            if ' – ' in line or ' — ' in line:
                pattern_counts['space_long_dash_space'] += 1
            else:
                pattern_counts['space_long_dash_space'] += 1  # Treat as long dash pattern
            separator_found = True
        elif ' - ' in line:
            pattern_counts['space_short_dash_space'] += 1
            separator_found = True
        elif ': ' in line and len(line.split(': ')[0].split()) <= 4:
            pattern_counts['colon_space'] += 1
            separator_found = True
        else:
            # Check for ALL CAPS pattern
            words = line.split()
            if len(words) >= 2:
                # Count consecutive uppercase words at start
                caps_count = 0
                for word in words:
                    if word.isupper() and len(word) > 1:
                        caps_count += 1
                    else:
                        break
                if caps_count >= 1:  # At least one ALL CAPS word
                    pattern_counts['all_caps_space'] += 1
                    separator_found = True
                else:
                    pattern_counts['line_break'] += 1
    
    # If we found explicit separators, prefer them over line breaks
    if separator_found:
        # Remove line_break from consideration if we found separators
        separator_patterns = {k: v for k, v in pattern_counts.items() if k != 'line_break'}
        if any(v > 0 for v in separator_patterns.values()):
            dominant = max(separator_patterns.items(), key=lambda x: x[1])
            if dominant[1] > 0:
                return dominant[0]
    
    # Fallback to overall dominant pattern
    dominant = max(pattern_counts.items(), key=lambda x: x[1])
    return dominant[0] if dominant[1] > 0 else 'space_long_dash_space'  # default


def first_non_bracket_separator_with_pattern(line: str, pattern: str) -> Optional[int]:
    """
    Find separator based on the detected pattern for this book.
    """
    if pattern == 'space_long_dash_space':
        return line.find(' – ') + 1 if ' – ' in line else None  # Return position of dash
    elif pattern == 'space_short_dash_space':
        return line.find(' - ') + 1 if ' - ' in line else None
    elif pattern == 'colon_space':
        return line.find(': ') if ': ' in line else None
    elif pattern == 'all_caps_space':
        # Find where ALL CAPS ends and description begins
        words = line.split()
        caps_end_idx = 0
        for i, word in enumerate(words):
            if word.isupper() and len(word) > 1:
                caps_end_idx = i + 1
            else:
                break
        if caps_end_idx > 0 and caps_end_idx < len(words):
            # Find position after the last caps word
            caps_text = ' '.join(words[:caps_end_idx])
            return len(caps_text)
        return None
    else:  # line_break pattern
        return None


def first_non_bracket_separator(line: str) -> Optional[int]:
    """
    Find the index of the first separator that is NOT inside brackets or quotes.
    """
    depth_paren = depth_sq = depth_curly = 0
    in_quotes = False
    prev = ''
    for i, ch in enumerate(line):
        if ch == '"' and prev != '\\':
            in_quotes = not in_quotes
        elif not in_quotes:
            if ch == '(':
                depth_paren += 1
            elif ch == ')':
                depth_paren = max(0, depth_paren - 1)
            elif ch == '[':
                depth_sq += 1
            elif ch == ']':
                depth_sq = max(0, depth_sq - 1)
            elif ch == '{':
                depth_curly += 1
            elif ch == '}':
                depth_curly = max(0, depth_curly - 1)
            elif ch in SEP_CHARS:
                if depth_paren == depth_sq == depth_curly == 0:
                    # ignore verse refs like "1:2" (digit before colon)
                    if ch == ':' and i > 0 and line[i-1].isdigit():
                        pass
                    else:
                        return i
        prev = ch
    return None


def looks_like_starter_with_pattern(line: str, pattern: str):
    """Return (term, desc) if line contains term SEP desc pattern, else (None, None)."""
    idx = first_non_bracket_separator_with_pattern(line, pattern)
    if idx is None:
        return None, None
    
    if pattern == 'space_long_dash_space':
        parts = line.split(' – ', 1)
        if len(parts) == 2:
            return strip_term(parts[0]), parts[1].strip()
    elif pattern == 'space_short_dash_space':
        parts = line.split(' - ', 1)
        if len(parts) == 2:
            return strip_term(parts[0]), parts[1].strip()
    elif pattern == 'colon_space':
        parts = line.split(': ', 1)
        if len(parts) == 2:
            return strip_term(parts[0]), parts[1].strip()
    elif pattern == 'all_caps_space':
        words = line.split()
        caps_end_idx = 0
        for i, word in enumerate(words):
            if word.isupper() and len(word) > 1:
                caps_end_idx = i + 1
            else:
                break
        if caps_end_idx > 0 and caps_end_idx < len(words):
            term = ' '.join(words[:caps_end_idx])
            desc = ' '.join(words[caps_end_idx:])
            return strip_term(term), desc.strip()
    
    return None, None


def looks_like_starter(line: str):
    """Return (term, desc) if line contains term SEP desc pattern, else (None, None)."""
    idx = first_non_bracket_separator(line)
    if idx is None:
        return None, None
    
    # expand to include optional spaces around the separator
    left = idx
    while left > 0 and line[left-1].isspace(): 
        left -= 1
    
    right = idx + 1
    while right < len(line) and line[right].isspace(): 
        right += 1

    term = strip_term(line[:left])
    desc = line[right:].strip()
    if not term:
        return None, None
    return term, desc


def looks_like_fallback_starter(curr: str, nxt: str) -> bool:
    """
    Check if current line is a term on its own line, with description starting on next line.
    """
    if not curr or not nxt:
        return False
    if first_non_bracket_separator(curr) is not None:
        return False  # already a regular starter
    
    words = curr.strip().split()
    if len(words) > MAX_TERM_WORDS_ENHANCED:
        return False
    if curr.strip()[-1:] in SOFT_ENDERS:
        return False
    if len(curr) > MAX_TERM_LEN:
        return False
    
    # Title-like term and next line looks like prose (starts lowercase)
    return is_title_like(curr) and (nxt[:1].islower())


def has_proper_description_ending(description: str) -> bool:
    """
    Check if a description has a proper ending that indicates completion.
    
    Based on analysis results:
    - Group 1 (period): Legitimate ending ✓
    - Group 2 (]): Legitimate ending ✓  
    - Group 3 ()): Legitimate ending ✓
    - Group 6 (alphabetic/IAST): Mid-sentence break ✗
    - Group 7 (OTHER like dashes): Mid-sentence break ✗
    - Groups 4,5: Need further analysis, but treat as potentially incomplete
    """
    if not description:
        return False
        
    last_char = description.strip()[-1] if description.strip() else ''
    
    # IAST characters commonly found in Sanskrit texts
    iast_chars = set('āīūṛṝḷḹṅñṇṭḍśṣṃḥĀĪŪṚṜḶḸṄÑṆṬḌŚṢṂḤ')
    
    # Legitimate endings (Groups 1, 2, 3)
    if last_char in '.])':
        return True
    
    # Mid-sentence breaks that should continue (Groups 6, 7)
    if last_char.isalpha() or last_char in iast_chars:
        return False  # Alphabetic/IAST - definitely incomplete
    
    if ord(last_char) in [45, 8211, 8212]:  # Regular dash, en-dash, em-dash
        return False  # Dashes - definitely incomplete
    
    # For now, treat other cases (digits, punctuation) as potentially incomplete
    # We can refine this based on further analysis
    return False


def should_accept_starter(term: str, desc: str, last_key: str, current_letter: Optional[str], entry_position: int = 0) -> bool:
    """
    Use alphabet guardrails and content validation to determine if this should be accepted as a term.
    """
    # Check for headers (especially first entry)
    if is_likely_header(term, entry_position):
        return False
    
    # Check for common English words that indicate misplaced description text
    if contains_common_english_words(term):
        return False
    
    # quick quality checks
    if len(term) > MAX_TERM_LEN:
        return False

    # Strength score to override alpha breaks
    term_words_ok = len(term.split()) <= 8
    title_like = is_title_like(term)
    desc_ok = bool(desc) and not desc[:1].isupper()  # many desc start lowercase
    strong = sum([term_words_ok, title_like, desc_ok]) >= 2

    key = normalize_key(term)
    alpha_ok = (key >= last_key)
    letter_ok = (not current_letter) or (term[:1].upper() == current_letter)

    if alpha_ok and letter_ok:
        return True
    return strong  # allow strong candidates to override


def detect_verse_index_start(lines: List[str]) -> int:
    """
    Detect where "Verse Index" section starts and return the line index.
    Returns -1 if not found.
    """
    verse_index_pattern = re.compile(r'verse\s*index', re.IGNORECASE)
    
    for i, line in enumerate(lines):
        if verse_index_pattern.search(line):
            return i
    return -1


def parse_glossary_block(
    book_id: int,
    raw_glossary_block: str,
    *,
    enable_fallback: bool = True
) -> List[Dict]:
    """
    Parse a raw glossary page/block into structured entries.

    Returns: List[{'book_id': int, 'term': str, 'description': str, 'entry_order': int}]
    """
    # Detect separator pattern for this book
    separator_pattern = detect_book_separator_pattern(raw_glossary_block)
    print(f"  🔍 Detected separator pattern: {separator_pattern.replace('_', ' ').title()}")
    
    lines = [ln for ln in splitlines_clean(raw_glossary_block) if not is_noise_line(ln)]
    
    # Check for verse index and truncate lines if found
    verse_index_start = detect_verse_index_start(lines)
    if verse_index_start >= 0:
        print(f"  📚 Found 'Verse Index' at line {verse_index_start + 1}, stopping glossary processing there")
        lines = lines[:verse_index_start]
    results: List[Dict] = []

    buf_term: Optional[str] = None
    buf_desc: List[str] = []
    entry_order = 0

    # Alpha guard context
    last_key = ""
    current_letter: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        # Try pattern-specific starter first
        term, desc = looks_like_starter_with_pattern(line, separator_pattern)
        
        # Fallback to original starter detection if pattern-specific fails
        if term is None:
            term, desc = looks_like_starter(line)

        # Optionally try fallback starter if no separator found
        if term is None and enable_fallback:
            nxt = lines[i+1] if (i + 1) < len(lines) else ""
            if looks_like_fallback_starter(line, nxt):
                term, desc = line.strip(), ""  # desc will accumulate from next lines

        # Decide starter vs continuation
        if term is not None:
            term_clean = strip_term(term)
            if term_clean and should_accept_starter(term_clean, desc, last_key, current_letter, entry_order):
                # Before starting new entry, check if previous description needs continuation
                if buf_term is not None:
                    current_desc = " ".join(buf_desc)
                    
                    # If previous description doesn't have proper ending, continue it with current line
                    if not has_proper_description_ending(current_desc):
                        # Add current line to previous description instead of starting new entry
                        buf_desc.append(line.strip())
                        i += 1
                        continue
                    else:
                        # Previous description is complete, flush it
                        results.append({
                            "book_id": book_id,
                            "term": buf_term,
                            "description": normalize_spaces(current_desc),
                            "entry_order": entry_order
                        })
                
                # start new entry
                entry_order += 1
                buf_term = term_clean
                buf_desc = [desc.strip()] if desc else []
                # update alpha context
                last_key = normalize_key(buf_term)
                current_letter = buf_term[:1].upper()
                i += 1
                continue

        # Continuation logic
        if buf_term is not None:
            buf_desc.append(line.strip())
        # stray text without an active term: ignore
        i += 1

    # flush tail
    if buf_term is not None:
        results.append({
            "book_id": book_id,
            "term": buf_term,
            "description": normalize_spaces(" ".join(buf_desc)),
            "entry_order": entry_order
        })

    # final tidy: drop empties and obvious garbage
    cleaned = []
    for r in results:
        term = r["term"].strip()
        desc = r["description"].strip()
        if term and desc:  # require both term and description
            cleaned.append({
                "book_id": book_id, 
                "term": term, 
                "description": desc, 
                "entry_order": r["entry_order"]
            })
    
    return cleaned


def analyze_description_endings(all_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the ending characters of glossary descriptions to identify parsing patterns.
    
    Returns detailed statistics about how descriptions end to help improve parsing logic.
    """
    # Categories for analysis
    stats = {
        'ending_with_period': 0,
        'ending_with_square_bracket': 0,
        'ending_with_parenthesis': 0,
        'ending_with_digit': 0,
        'ending_with_punctuation': 0,  # ! ? ; : , etc.
        'ending_with_alpha': 0,  # a-z, A-Z, IAST characters
        'ending_with_other': 0,
        'other_examples': [],  # Store examples of "other" category
        'total_entries': 0
    }
    
    # IAST characters commonly found in Sanskrit texts
    iast_chars = set('āīūṛṝḷḹṅñṇṭḍśṣṃḥĀĪŪṚṜḶḸṄÑṆṬḌŚṢṂḤ')
    
    # Collect all descriptions from all books
    all_descriptions = []
    for result in all_results.values():
        book_id = result['book_info']['book_id']
        book_title = result['book_info']['original_title']
        parsed_entries = result['parsed_entries']
        
        for entry in parsed_entries:
            description = entry['description'].strip()
            all_descriptions.append({
                'book_id': book_id,
                'book_title': book_title,
                'term': entry['term'],
                'description': description
            })
    
    stats['total_entries'] = len(all_descriptions)
    
    # Analyze each description
    for entry in all_descriptions:
        description = entry['description']
        if not description:
            continue
            
        last_char = description[-1]
        
        if last_char == '.':
            stats['ending_with_period'] += 1
        elif last_char == ']':
            stats['ending_with_square_bracket'] += 1
        elif last_char == ')':
            stats['ending_with_parenthesis'] += 1
        elif last_char.isdigit():
            stats['ending_with_digit'] += 1
        elif last_char in '!?;:,':
            stats['ending_with_punctuation'] += 1
        elif last_char.isalpha() or last_char in iast_chars:
            stats['ending_with_alpha'] += 1
        else:
            stats['ending_with_other'] += 1
            # Store example if we have room
            if len(stats['other_examples']) < 20:
                stats['other_examples'].append({
                    'book_id': entry['book_id'],
                    'book_title': entry['book_title'],
                    'term': entry['term'],
                    'description': description,
                    'last_char': last_char,
                    'last_char_code': ord(last_char)
                })
    
    return stats


def print_description_analysis_report(stats: Dict[str, Any]) -> None:
    """Print detailed analysis report of description endings."""
    total = stats['total_entries']
    
    print(f"\n📊 DESCRIPTION ENDING ANALYSIS REPORT")
    print("=" * 70)
    print(f"📈 Total glossary entries analyzed: {total:,}")
    print()
    
    # Print each category with percentages
    categories = [
        ('ending_with_period', '1️⃣  Ending with period (.)', '.'),
        ('ending_with_square_bracket', '2️⃣  Ending with square bracket (])', ']'),
        ('ending_with_parenthesis', '3️⃣  Ending with parenthesis ())', ')'),
        ('ending_with_digit', '4️⃣  Ending with numeric digit', '0-9'),
        ('ending_with_punctuation', '5️⃣  Ending with other punctuation (!?;:,)', '!?;:,'),
        ('ending_with_alpha', '6️⃣  Ending with alphabetic/IAST chars', 'a-z/IAST'),
        ('ending_with_other', '7️⃣  Ending with OTHER characters', 'various')
    ]
    
    for key, label, example in categories:
        count = stats[key]
        percentage = (count / total * 100) if total > 0 else 0
        print(f"{label:<50} {count:>6,} ({percentage:>5.1f}%)")
    
    # Show examples of "other" category
    if stats['other_examples']:
        print(f"\n🔍 EXAMPLES OF 'OTHER' CATEGORY:")
        print("-" * 70)
        for i, example in enumerate(stats['other_examples'], 1):
            last_char = example['last_char']
            char_code = example['last_char_code']
            term = example['term'][:30] + "..." if len(example['term']) > 30 else example['term']
            desc_end = example['description'][-50:] if len(example['description']) > 50 else example['description']
            
            print(f"{i:2d}. Book {example['book_id']} | Term: {term}")
            print(f"    Last char: '{last_char}' (Unicode: {char_code})")
            print(f"    Ending: ...{desc_end}")
            print()
    
    # Summary insights
    print("💡 INSIGHTS FOR PARSING IMPROVEMENT:")
    print("-" * 70)
    
    period_pct = (stats['ending_with_period'] / total * 100) if total > 0 else 0
    alpha_pct = (stats['ending_with_alpha'] / total * 100) if total > 0 else 0
    other_pct = (stats['ending_with_other'] / total * 100) if total > 0 else 0
    
    if period_pct < 70:
        print(f"⚠️  Only {period_pct:.1f}% of descriptions end with periods - many may be incomplete")
    
    if alpha_pct > 20:
        print(f"⚠️  {alpha_pct:.1f}% end with letters - likely incomplete descriptions")
    
    if other_pct > 5:
        print(f"⚠️  {other_pct:.1f}% end with unusual characters - check examples above")
    
    # Recommendations
    print(f"\n📋 RECOMMENDATIONS:")
    if alpha_pct > 15:
        print("   • Consider extending parsing to continue until proper sentence endings")
    if stats['ending_with_digit'] > total * 0.1:
        print("   • Many entries end with digits - may be verse references or incomplete")
    if stats['ending_with_other'] > 0:
        print("   • Review 'OTHER' examples to identify missing character patterns")
    
    print("=" * 70)


def analyze_separator_patterns(all_results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze separator patterns for each book to understand formatting consistency."""
    
    patterns_report = {}
    
    for result in all_results.values():
        book_info = result['book_info']
        book_id = book_info['book_id']
        book_title = book_info['original_title']
        parsed_entries = result['parsed_entries']
        
        if not parsed_entries:
            continue
            
        # Analyze patterns for this book
        pattern_stats = {
            'book_id': book_id,
            'book_title': book_title,
            'total_entries': len(parsed_entries),
            'separator_patterns': {},
            'term_case_patterns': {},
            'sample_entries': []
        }
        
        # Sample first 10 entries for analysis
        for i, entry in enumerate(parsed_entries[:10]):
            pattern_stats['sample_entries'].append({
                'term': entry['term'],
                'description': entry['description'][:100] + '...' if len(entry['description']) > 100 else entry['description']
            })
        
        # Analyze separator patterns in raw content if available
        if 'page_contents' in result:
            raw_content = "\n\n".join(result['page_contents'])
            lines = [ln.strip() for ln in raw_content.splitlines() if ln.strip()]
            
            separator_counts = {
                'space_long_dash_space': 0,  # term — description
                'space_short_dash_space': 0,  # term - description  
                'colon_space': 0,  # term: description
                'colon_only': 0,  # term:description
                'line_break': 0,  # term on one line, desc on next
                'all_caps_space': 0,  # ALL CAPS TERM description
                'other': 0
            }
            
            case_patterns = {
                'all_caps_terms': 0,
                'title_case_terms': 0,
                'mixed_case_terms': 0,
                'lowercase_terms': 0
            }
            
            # Analyze first 50 lines for patterns
            for line in lines[:50]:
                if not line:
                    continue
                    
                # Check separator patterns
                if ' — ' in line:
                    separator_counts['space_long_dash_space'] += 1
                elif ' - ' in line:
                    separator_counts['space_short_dash_space'] += 1
                elif ': ' in line:
                    separator_counts['colon_space'] += 1
                elif ':' in line and ': ' not in line:
                    separator_counts['colon_only'] += 1
                else:
                    # Check if it could be all caps pattern
                    words = line.split()
                    if len(words) >= 2:
                        first_word = words[0]
                        if first_word.isupper() and len(first_word) > 1:
                            # Check if multiple words are caps before lowercase
                            caps_count = 0
                            for word in words:
                                if word.isupper() and len(word) > 1:
                                    caps_count += 1
                                else:
                                    break
                            if caps_count >= 1:
                                separator_counts['all_caps_space'] += 1
                            else:
                                separator_counts['other'] += 1
                        else:
                            separator_counts['line_break'] += 1
                    else:
                        separator_counts['line_break'] += 1
                
                # Analyze case patterns of potential terms
                potential_term = line.split(' — ')[0] if ' — ' in line else \
                                line.split(' - ')[0] if ' - ' in line else \
                                line.split(': ')[0] if ': ' in line else \
                                line.split(':')[0] if ':' in line else \
                                line.split()[0] if line.split() else line
                
                if potential_term:
                    if potential_term.isupper():
                        case_patterns['all_caps_terms'] += 1
                    elif potential_term.istitle() or potential_term[0].isupper():
                        case_patterns['title_case_terms'] += 1
                    elif potential_term.islower():
                        case_patterns['lowercase_terms'] += 1
                    else:
                        case_patterns['mixed_case_terms'] += 1
            
            pattern_stats['separator_patterns'] = separator_counts
            pattern_stats['term_case_patterns'] = case_patterns
        
        patterns_report[book_id] = pattern_stats
    
    return patterns_report


def print_separator_analysis_report(patterns_report: Dict[str, Any]) -> None:
    """Print detailed separator pattern analysis report."""
    
    print(f"\n📊 SEPARATOR PATTERN ANALYSIS REPORT")
    print("=" * 80)
    
    # Summary statistics
    total_books = len(patterns_report)
    print(f"📈 Total books analyzed: {total_books}")
    print()
    
    # Analyze each book
    for book_id, stats in patterns_report.items():
        print(f"📚 BOOK {book_id}: {stats['book_title']}")
        print("-" * 60)
        print(f"Total entries: {stats['total_entries']}")
        
        # Separator patterns
        print(f"\n🔍 Separator Patterns:")
        separators = stats['separator_patterns']
        total_lines = sum(separators.values()) if separators else 0
        
        if total_lines > 0:
            for pattern, count in separators.items():
                if count > 0:
                    percentage = (count / total_lines) * 100
                    print(f"  • {pattern.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        # Case patterns  
        print(f"\n📝 Term Case Patterns:")
        cases = stats['term_case_patterns']
        total_terms = sum(cases.values()) if cases else 0
        
        if total_terms > 0:
            for pattern, count in cases.items():
                if count > 0:
                    percentage = (count / total_terms) * 100
                    print(f"  • {pattern.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        # Dominant pattern detection
        print(f"\n🎯 Detected Primary Pattern:")
        if separators:
            dominant_sep = max(separators.items(), key=lambda x: x[1])
            if dominant_sep[1] > 0:
                print(f"  • Separator: {dominant_sep[0].replace('_', ' ').title()}")
        
        if cases:
            dominant_case = max(cases.items(), key=lambda x: x[1])
            if dominant_case[1] > 0:
                print(f"  • Case Style: {dominant_case[0].replace('_', ' ').title()}")
        
        # Sample entries
        print(f"\n📋 Sample Entries (first 5):")
        for i, sample in enumerate(stats['sample_entries'][:5], 1):
            term_preview = sample['term'][:30] + "..." if len(sample['term']) > 30 else sample['term']
            desc_preview = sample['description'][:50] + "..." if len(sample['description']) > 50 else sample['description']
            print(f"  {i}. Term: '{term_preview}'")
            print(f"     Desc: '{desc_preview}'")
        
        print("\n" + "=" * 80)
    
    # Overall pattern summary
    print(f"\n📈 OVERALL PATTERN SUMMARY:")
    print("-" * 40)
    
    # Aggregate separator patterns
    all_separators = {}
    all_cases = {}
    
    for stats in patterns_report.values():
        for sep, count in stats['separator_patterns'].items():
            all_separators[sep] = all_separators.get(sep, 0) + count
        for case, count in stats['term_case_patterns'].items():
            all_cases[case] = all_cases.get(case, 0) + count
    
    print("Most common separator patterns across all books:")
    sorted_seps = sorted(all_separators.items(), key=lambda x: x[1], reverse=True)
    for sep, count in sorted_seps[:5]:
        if count > 0:
            print(f"  • {sep.replace('_', ' ').title()}: {count} occurrences")
    
    print("\nMost common case patterns across all books:")
    sorted_cases = sorted(all_cases.items(), key=lambda x: x[1], reverse=True) 
    for case, count in sorted_cases[:5]:
        if count > 0:
            print(f"  • {case.replace('_', ' ').title()}: {count} occurrences")


class GoogleSheetsWriter:
    """Write glossary entries to Google Sheets with duplicate checking."""

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]

    def __init__(self, credentials_file: str, sheet_id: str, tab_name: str = 'glossary'):
        """
        Initialize Google Sheets writer.

        Args:
            credentials_file: Path to service account JSON credentials
            sheet_id: Google Sheets ID
            tab_name: Name of the tab to write to
        """
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.tab_name = tab_name
        self.client = None
        self.worksheet = None

    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        try:
            print(f"🔐 Authenticating with Google Sheets API...")

            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=self.SCOPES
            )

            self.client = gspread.authorize(creds)
            print(f"✅ Authentication successful!")
            return True

        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False

    def open_worksheet(self) -> bool:
        """Open the target worksheet."""
        try:
            print(f"📊 Opening Google Sheet (ID: {self.sheet_id})...")
            spreadsheet = self.client.open_by_key(self.sheet_id)

            # Try to get the glossary tab
            try:
                self.worksheet = spreadsheet.worksheet(self.tab_name)
                print(f"✅ Found '{self.tab_name}' tab")
            except gspread.exceptions.WorksheetNotFound:
                print(f"⚠️  Tab '{self.tab_name}' not found, creating it...")
                self.worksheet = spreadsheet.add_worksheet(
                    title=self.tab_name,
                    rows=1000,
                    cols=4
                )
                # Add headers to match existing format
                self.worksheet.update('A1:D1', [['book_id', 'pdf_name', 'term', 'description']])
                print(f"✅ Created '{self.tab_name}' tab with headers")

            return True

        except Exception as e:
            print(f"❌ Failed to open worksheet: {e}")
            return False

    def append_entries(self, entries: List[Dict[str, Any]], pdf_name: str) -> int:
        """
        Append all entries to the sheet (no duplicate checking).

        Args:
            entries: List of glossary entries to append
            pdf_name: PDF filename for this book

        Returns:
            Number of entries appended
        """
        try:
            new_rows = []

            for entry in entries:
                book_id = entry['book_id']
                term = entry['term']
                description = entry['description']

                # Format: book_id, pdf_name, term, description
                new_rows.append([book_id, pdf_name, term, description])

            if new_rows:
                print(f"   📝 Appending {len(new_rows)} entries...")
                self.worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')

            return len(new_rows)

        except Exception as e:
            print(f"❌ Failed to append entries: {e}")
            raise


def write_glossary_to_google_sheets(all_results: Dict[str, Any], sheet_writer: GoogleSheetsWriter) -> Dict[str, int]:
    """Write all parsed glossary entries to Google Sheets (no duplicate checking)."""

    stats = {
        'total_processed': 0,
        'total_added': 0,
        'errors': 0
    }

    # Authenticate and open worksheet
    if not sheet_writer.authenticate():
        return stats

    if not sheet_writer.open_worksheet():
        return stats

    # Write all parsed entries from all books
    for result in all_results.values():
        book_info = result['book_info']
        book_id = book_info['book_id']
        pdf_name = book_info['pdf_name']
        parsed_entries = result['parsed_entries']

        print(f"  📤 Processing {len(parsed_entries)} entries for book {book_id} ({book_info['original_title']})")

        try:
            added = sheet_writer.append_entries(parsed_entries, pdf_name)

            stats['total_processed'] += len(parsed_entries)
            stats['total_added'] += added

            print(f"     ✅ Appended: {added} entries")

        except Exception as e:
            print(f"     ❌ Error processing book {book_id}: {e}")
            stats['errors'] += 1
            continue

    print(f"\n  📊 Google Sheets write summary:")
    print(f"     • Total entries processed: {stats['total_processed']}")
    print(f"     • Total entries appended: {stats['total_added']}")
    print(f"     • Books with errors: {stats['errors']}")

    return stats

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Enhanced Glossary Extractor - Extract glossary terms from PDFs and write to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python glossary_extractor.py                    # Extract and append glossary entries to Google Sheets
  python glossary_extractor.py --verbose          # Extract with detailed analysis reports
  python glossary_extractor.py --help             # Show this help message

The script will:
1. Connect to PostgreSQL database to find books with glossary page ranges
2. Extract glossary content from those page ranges using PageContentExtractor
3. Parse the content into structured term/description pairs
4. Append ALL entries to the 'glossary' tab (no duplicate checking)
5. User manually reviews and cleans up data in Google Sheets
        """
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output with detailed analysis reports"
    )

    return parser.parse_args()


def main():
    """Main function - extract glossary and write to Google Sheets."""
    # Parse command line arguments
    args = parse_arguments()

    print("🚀 Starting Enhanced Glossary Extraction")
    print("=" * 60)
    print("📤 Output: Google Sheets (all entries appended for manual review)")

    if args.verbose:
        print("📊 Verbose mode: Detailed analysis reports enabled")

    try:
        # Get Google Sheets configuration from environment
        credentials_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
        sheet_id = os.getenv('GOOGLE_BOOK_LOADER_SHEET_ID')

        if not credentials_file:
            print("❌ ERROR: GOOGLE_SERVICE_ACCOUNT_FILE not set in .env file")
            return

        if not sheet_id:
            print("❌ ERROR: GOOGLE_BOOK_LOADER_SHEET_ID not set in .env file")
            return

        if not Path(credentials_file).exists():
            print(f"❌ ERROR: Credentials file not found at: {credentials_file}")
            return

        print(f"✅ Google Sheets configuration loaded")
        print(f"   Sheet ID: {sheet_id}")
        print(f"   Tab: 'glossary'")

        # Initialize the enhanced glossary extractor
        extractor = GlossaryExtractor()

        # Test database connection (for reading book metadata)
        if not extractor.db.test_connection():
            print("❌ Failed to connect to database. Check your connection parameters.")
            return

        print("✅ Database connection successful (for reading book metadata)")

        # Process all books with glossary ranges
        print("\n📖 Processing books with glossary page ranges...")
        results = extractor.process_all_glossary_books()

        if not results:
            print("\n⚠️  No books with glossary ranges found or processed")
            return

        # Analyze patterns if verbose mode is enabled
        if args.verbose:
            # Analyze separator patterns for each book
            print(f"\n🔍 Analyzing separator patterns for each book...")
            separator_analysis = analyze_separator_patterns(results)
            print_separator_analysis_report(separator_analysis)

            # Analyze description endings for parsing insights
            print(f"\n🔍 Analyzing description patterns...")
            analysis_stats = analyze_description_endings(results)
            print_description_analysis_report(analysis_stats)
        else:
            print(f"\n💡 Tip: Use --verbose flag to see detailed pattern analysis reports")

        # Export results to Google Sheets
        print(f"\n📤 Writing all results to Google Sheets...")

        try:
            sheet_writer = GoogleSheetsWriter(
                credentials_file=credentials_file,
                sheet_id=sheet_id,
                tab_name='glossary'
            )

            stats = write_glossary_to_google_sheets(results, sheet_writer)

            if stats['total_added'] > 0 or stats['total_skipped'] > 0:
                print(f"  ✅ Successfully processed glossary entries")
            else:
                print(f"  ⚠️  No new entries to add")

        except Exception as e:
            print(f"  ❌ Failed to write to Google Sheets: {e}")
            import traceback
            traceback.print_exc()
            return

        # Summary
        print(f"\n🎉 Processing Complete!")
        print("=" * 60)
        print(f"📊 Summary:")
        print(f"  • Books processed: {len(results)}")
        print(f"  • Total entries extracted: {stats['total_processed']}")
        print(f"  • Total entries appended to Google Sheets: {stats['total_added']}")
        print(f"  • Output: Google Sheets 'glossary' tab")
        print(f"  • Columns: book_id, pdf_name, term, description")
        print(f"  • Note: All entries appended for manual review (no duplicate filtering)")
        print(f"\n🔗 View your Google Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}")

        # Show breakdown by book
        print(f"\n📋 Breakdown by book:")
        for result in results.values():
            book_info = result['book_info']
            count = result['total_entries']
            print(f"  • Book {book_info['book_id']} ({book_info['original_title']}): {count} entries")

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()


# Legacy functions removed - all processing now uses database integration and PageContentExtractor


if __name__ == "__main__":
    main()
