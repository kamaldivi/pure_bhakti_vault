#!/usr/bin/env python3
"""
Sanskrit IAST Transliteration Fix System
=========================================

Complete 5-stage pipeline for fixing OCR/encoding errors in Sanskrit IAST text.

Stages:
1. Global Character Map (simple substitutions)
2. Text Segmentation & Word Classification
3. Pattern-Based Correction (context-aware)
4. Validation & Quality Checks
5. Text Reconstruction

Author: Sanskrit Text Processing
License: MIT
Version: 1.0.0
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter
from datetime import datetime

# Import the actual correction functions from sanskrit_diacritic_utils
from . import sanskrit_diacritic_utils


# ============================================================================
# CONFIGURATION
# ============================================================================

GLOBAL_CHAR_MAP = {
    # CRITICAL: Combined patterns MUST come first (before individual character mappings)
    # This ensures 'åñ' is replaced as a unit before 'å' or 'ñ' are processed individually
    "åñ": "ṛṣ", "Åñ": "Ṛṣ", "ÅÑ": "ṚṢ",  # Combined pattern åñ → ṛṣ (500+ words)
                                          # MUST be before any standalone å or ñ mappings
                                          # Covers: kåñṇa→kṛṣṇa, dåñṭa→dṛṣṭa, håñīkeśa→hṛṣīkeśa, våñabhānu→vṛṣabhānu, åñi→ṛṣi
                                          # This fixes 400+ currently broken words (dṛṣṭa, hṛṣīkeśa, ṛṣi, etc.)

    # Individual character mappings follow
    "ä": "ā", "Ä": "Ā",
    "é": "ī", "É": "Ī",
    "ü": "ū", "Ü": "Ū",
    "î": "ī", "Î": "Ī",
    "ë": "ṇ", "Ë": "Ṇ",
    "√": "ṇ",
    "ö": "ṭ", "Ö": "Ṭ",
    "ò": "ḍ", "Ò": "Ḍ",
    "∂": "ḍ",
    "∫": "ṅ",
    "ì": "ṅ", "Ì": "Ṅ",  # Latin Small/Capital Letter I with Grave - OCR error for ṅ
                         # Found in patterns where ṅ (n with dot above) is misread as ì
                         # Note: Would corrupt Italian words if present, but corpus is Sanskrit-only
    "ç": "ś", "Ç": "Ś",
    "ß": "ṣ",
    "®": "ṛ",
    "µ": "ṁ",
    "ù": "ḥ", "Ù": "Ḥ",
    "†": "ṭ",
    "ˇ": "Ṭ",  # Caron (U+02C7) - OCR error for Ṭ (e.g., ˇhākura → Ṭhākura)
                # Note: This assumes Sanskrit-only text; would corrupt Czech/Slovak if present
    "à": "ṁ", "À": "Ṁ",  # Latin Small/Capital Letter A with Grave - OCR error for ṁ
                         # Found in patterns like: oà → oṁ, ekaà → ekaṁ, satatà → satataṁ
                         # Note: Would corrupt French words (voilà, café) if present, but corpus is Sanskrit-only
    "ï": "ñ", "Ï": "Ñ",  # Latin Small/Capital Letter I with Diaeresis - OCR error for ñ
                         # Found in patterns like: Jïäna → Jñāna, Saïjaya → Sañjaya, Prajïäna → Prajñāna
                         # Note: Would corrupt English/French words (naïve) if present, but corpus is Sanskrit-only
}

# Valid IAST characters for validation (IAST standard)
# Vowels: a ā i ī u ū ṛ ṝ ḷ ḹ e ai o au
# Anusvāra: ṁ ṃ
# Visarga: ḥ
# Consonants: k kh g gh ṅ c ch j jh ñ ṭ ṭh ḍ ḍh ṇ t th d dh n p ph b bh m y r l v ś ṣ s h
VALID_IAST_CHARS = set(
    'aāiīuūṛṝḷḹeaioauṁṃḥ'  # Vowels, anusvāra, visarga
    'kgṅcjñṭḍṇtdnpbmyrlvśṣsh'  # Consonants
    'AĀIĪUŪṚṜḶḸEAIOAUṀṂḤ'  # Uppercase vowels
    'KGṄCJÑṬḌṆTDNPBMYRLVŚṢSH'  # Uppercase consonants
)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class WordClass(Enum):
    """Word classification by diacritic complexity."""
    CLEAN = 0              # No ñ or å
    SINGLE_N = 1           # Single ñ only
    SINGLE_A = 2           # Single å only
    COMBINED_PATTERN = 3   # Both ñ and å (åñ pattern - handled in Stage 1 now)
    BOTH_DIACRITICS = 4    # Both but not combined pattern
    MULTIPLE_N = 5         # Multiple ñ
    MULTIPLE_A = 6         # Multiple å
    COMPLEX = 7            # Complex combinations


class TokenType(Enum):
    """Token type for text segmentation."""
    WORD = 'word'
    WHITESPACE = 'whitespace'
    PUNCTUATION = 'punctuation'
    OTHER = 'other'


@dataclass
class Token:
    """Represents a token in the text."""
    text: str
    start: int
    end: int
    token_type: TokenType
    has_n: bool = False
    has_a: bool = False
    word_class: Optional[WordClass] = None
    case_pattern: Optional[str] = None  # 'upper', 'lower', 'title', 'mixed'


@dataclass
class CorrectionResult:
    """Result of word correction."""
    original: str
    corrected: str
    word_class: WordClass
    confidence: float
    rules_applied: List[str] = field(default_factory=list)
    changed: bool = False


@dataclass
class ValidationIssue:
    """Validation issue for a correction."""
    level: str  # 'ERROR', 'WARNING', 'INFO'
    message: str
    suggestion: str = ""


@dataclass
class ValidationReport:
    """Validation report for a correction."""
    passed: bool
    confidence: float
    issues: List[ValidationIssue] = field(default_factory=list)
    needs_review: bool = False


@dataclass
class PageStatistics:
    """Statistics for processed page."""
    total_tokens: int = 0
    total_words: int = 0
    words_corrected: int = 0
    
    # Stage 1 stats
    global_map_replacements: Counter = field(default_factory=Counter)
    
    # Classification stats
    class_distribution: Counter = field(default_factory=Counter)
    
    # Correction stats
    n_corrections: int = 0
    a_corrections: int = 0
    combined_corrections: int = 0
    
    # Confidence distribution
    high_confidence: int = 0    # ≥0.95
    medium_confidence: int = 0  # 0.90-0.95
    low_confidence: int = 0     # <0.90
    
    # Validation stats
    validation_errors: int = 0
    needs_manual_review: int = 0
    
    # Patterns
    patterns_applied: Counter = field(default_factory=Counter)
    
    # Performance
    processing_time: float = 0.0
    stage_times: Dict[str, float] = field(default_factory=dict)


@dataclass
class ProcessedPage:
    """Complete result of page processing."""
    page_number: int
    original_text: str
    corrected_text: str
    statistics: PageStatistics
    corrections: List[CorrectionResult]
    validation_reports: List[ValidationReport]
    timestamp: datetime
    processing_time: float


# ============================================================================
# STAGE 1: GLOBAL CHARACTER MAP
# ============================================================================

def apply_global_char_map(text: str, char_map: Dict[str, str] = None) -> Tuple[str, Counter]:
    """
    Apply global character substitutions.
    
    Args:
        text: Input text with OCR errors
        char_map: Character mapping (default: GLOBAL_CHAR_MAP)
        
    Returns:
        Tuple of (corrected_text, replacement_counts)
    """
    if char_map is None:
        char_map = GLOBAL_CHAR_MAP
    
    replacements = Counter()
    result = text
    
    for wrong, correct in char_map.items():
        count = result.count(wrong)
        if count > 0:
            result = result.replace(wrong, correct)
            replacements[f"{wrong}→{correct}"] = count
    
    return result, replacements


# ============================================================================
# STAGE 2: TEXT SEGMENTATION & CLASSIFICATION
# ============================================================================

def tokenize_text(text: str) -> List[Token]:
    """
    Tokenize text into words, whitespace, and punctuation.
    
    Args:
        text: Input text after global map
        
    Returns:
        List of Token objects
    """
    tokens = []
    
    # Pattern to match: words (with IAST) | whitespace | punctuation | other (digits, etc.)
    # Include both lowercase and uppercase IAST diacritics
    # Group 1: IAST chars + a-z, A-Z, hyphens
    # Group 2: Whitespace
    # Group 3: Punctuation (excluding word chars and whitespace)
    # Group 4: Digits and other characters to preserve as-is
    pattern = r'([āīūṛṝḷḹṅñṭḍṇśṣṁṃḥåĀĪŪṚṜḶḸṄÑṬḌṆŚṢṀṂḤÅa-zA-Z\-]+)|(\s+)|([^\s\w]+)|(\d+|.)'

    for match in re.finditer(pattern, text, re.UNICODE):
        word, space, punct, other = match.groups()

        if word:
            token_type = TokenType.WORD
            token_text = word
        elif space:
            token_type = TokenType.WHITESPACE
            token_text = space
        elif punct:
            token_type = TokenType.PUNCTUATION
            token_text = punct
        elif other:
            # Digits, special chars, etc. - preserve as-is
            token_type = TokenType.OTHER
            token_text = other
        else:
            token_type = TokenType.OTHER
            token_text = match.group(0)
        
        # Check for problematic diacritics
        has_n = 'ñ' in token_text or 'Ñ' in token_text
        has_a = 'å' in token_text or 'Å' in token_text
        
        token = Token(
            text=token_text,
            start=match.start(),
            end=match.end(),
            token_type=token_type,
            has_n=has_n,
            has_a=has_a
        )
        
        tokens.append(token)
    
    return tokens


def classify_word(word: str) -> WordClass:
    """
    Classify word by diacritic complexity.
    
    Args:
        word: Word to classify
        
    Returns:
        WordClass enum value
    """
    word_lower = word.lower()
    n_count = word_lower.count('ñ')
    a_count = word_lower.count('å')

    if n_count == 0 and a_count == 0:
        return WordClass.CLEAN

    # NOTE: Combined pattern åñ → ṛṣ is now handled in Stage 1 (GLOBAL_CHAR_MAP)
    # By the time we reach this stage, åñ has already been converted to ṛṣ
    # So we no longer need to check for it here

    if n_count == 1 and a_count == 0:
        return WordClass.SINGLE_N
    
    if n_count == 0 and a_count == 1:
        return WordClass.SINGLE_A
    
    if n_count > 0 and a_count > 0:
        return WordClass.BOTH_DIACRITICS
    
    if n_count > 1 and a_count == 0:
        return WordClass.MULTIPLE_N
    
    if n_count == 0 and a_count > 1:
        return WordClass.MULTIPLE_A
    
    return WordClass.COMPLEX


def detect_case_pattern(word: str) -> str:
    """
    Detect case pattern of word.
    
    Args:
        word: Word to analyze
        
    Returns:
        'upper', 'lower', 'title', or 'mixed'
    """
    if not word or not any(c.isalpha() for c in word):
        return 'lower'
    
    alpha_chars = [c for c in word if c.isalpha()]
    
    if all(c.isupper() for c in alpha_chars):
        return 'upper'
    
    if all(c.islower() for c in alpha_chars):
        return 'lower'
    
    if alpha_chars[0].isupper() and all(c.islower() for c in alpha_chars[1:]):
        return 'title'
    
    return 'mixed'


def analyze_tokens(tokens: List[Token]) -> List[Token]:
    """
    Analyze tokens and add classification info.
    
    Args:
        tokens: List of tokens from tokenization
        
    Returns:
        Updated tokens with classification info
    """
    for token in tokens:
        if token.token_type == TokenType.WORD:
            token.word_class = classify_word(token.text)
            token.case_pattern = detect_case_pattern(token.text)
    
    return tokens


# ============================================================================
# STAGE 3: PATTERN-BASED CORRECTION (WITH CASE PRESERVATION)
# ============================================================================

def correct_n_diacritic_lowercase(word: str) -> Tuple[str, List[str]]:
    """
    Correct ñ diacritic (lowercase version for internal use).
    Returns tuple of (corrected_word, rules_applied).

    This is a wrapper around sanskrit_diacritic_utils.correct_n_diacritic
    that infers which rules were applied by analyzing the changes.
    """
    # Use the canonical implementation from sanskrit_diacritic_utils
    corrected = sanskrit_diacritic_utils.correct_n_diacritic(word)

    # Infer which rules were applied by checking patterns
    rules = []

    if word != corrected:
        # Check for specific pattern changes to determine which rules were applied
        if 'ñṇ' in word and 'ṣṇ' in corrected:
            rules.append('ñṇ→ṣṇ')
        if 'viñ' in word and 'viṣ' in corrected:
            rules.append('viñ→viṣ')
        if 'kñ' in word and 'kṣ' in corrected:
            rules.append('kñ→kṣ')
        if 'rña' in word and 'rṣa' in corrected:
            rules.append('rña→rṣa')
        if 'ñṭ' in word and 'ṣṭ' in corrected:
            rules.append('ñṭ→ṣṭ')
        if 'ñeka' in word and 'ṣeka' in corrected:
            rules.append('ñeka→ṣeka')
        if 'śiñya' in word and 'śiṣya' in corrected:
            rules.append('śiñya→śiṣya')
        if 'ñya' in word and 'ṣya' in corrected:
            rules.append('ñya→ṣya')
        if 'ñma' in word and 'ṣma' in corrected:
            rules.append('ñma→ṣma')

        # Note: We could add more detailed rule tracking here if needed

    return corrected, rules


def correct_a_diacritic_lowercase(word: str) -> Tuple[str, List[str]]:
    """
    Correct å diacritic (lowercase version for internal use).
    Returns tuple of (corrected_word, rules_applied).

    This is a wrapper around sanskrit_diacritic_utils.correct_a_diacritic
    that infers which rules were applied by analyzing the changes.
    """
    # Use the canonical implementation from sanskrit_diacritic_utils
    corrected = sanskrit_diacritic_utils.correct_a_diacritic(word)

    # Infer which rules were applied by checking patterns
    rules = []

    if word != corrected:
        # Check for specific patterns to determine which rules were applied
        if 'åh' in word and 'ṛh' in corrected:
            rules.append('åh→ṛh')
        if 'amåt' in word and 'amṛt' in corrected:
            rules.append('amåt→amṛt')
        if 'småt' in word and 'smṛt' in corrected:
            rules.append('småt→smṛt')
        if 'gåhī' in word and 'gṛhī' in corrected:
            rules.append('gåhī→gṛhī')
        if 'tåpt' in word and 'tṛpt' in corrected:
            rules.append('tåpt→tṛpt')
        if 'tåṇ' in word and 'tṛṇ' in corrected:
            rules.append('tåṇ→tṛṇ')
        if 'dåḍh' in word and 'dṛḍh' in corrected:
            rules.append('dåḍh→dṛḍh')
        if 'dåśy' in word and 'dṛśy' in corrected:
            rules.append('dåśy→dṛśy')
        if 'prakåt' in word.lower() and 'prakṛt' in corrected.lower():
            rules.append('prakåt→prakṛt')
        if 'kåt' in word and 'kṛt' in corrected:
            rules.append('kåt→kṛt')
        if 'vånd' in word and 'vṛnd' in corrected:
            rules.append('vånd→vṛnd')
        if 'dhåt' in word and 'dhṛt' in corrected:
            rules.append('dhåt→dhṛt')

        # If å was present and ā appears in output, it's the default rule
        if 'å' in word and 'ā' in corrected:
            # Check if not all å were converted to ṛ
            if not all(c != 'å' for c in corrected):
                rules.append('å→ā(default)')
            elif 'å' in word and 'å' not in corrected:
                # All å converted, check if any became ā
                word_a_count = word.count('ā')
                corrected_a_count = corrected.count('ā')
                if corrected_a_count > word_a_count:
                    rules.append('å→ā(default)')

    return corrected, rules


def restore_case_pattern(original: str, corrected: str) -> str:
    """
    Restore the case pattern from original to corrected text.
    
    Handles:
    - All uppercase
    - All lowercase
    - Title case
    - Mixed case (character-wise mapping)
    
    Args:
        original: Original word with case
        corrected: Corrected word in lowercase
        
    Returns:
        Corrected word with original case pattern
    """
    if not original or not corrected:
        return corrected
    
    # Get only alphabetic characters for analysis
    orig_alpha = [c for c in original if c.isalpha()]
    
    if not orig_alpha:
        return corrected
    
    # Quick check for common patterns
    if all(c.isupper() for c in orig_alpha):
        # All uppercase
        return corrected.upper()
    
    if all(c.islower() for c in orig_alpha):
        # All lowercase
        return corrected.lower()
    
    # Check for title case (first upper, rest lower)
    if orig_alpha[0].isupper() and all(c.islower() for c in orig_alpha[1:]):
        return corrected.capitalize()
    
    # Mixed case - map character by character
    result = []
    orig_idx = 0
    
    for char in corrected:
        if not char.isalpha():
            result.append(char)
            continue
        
        # Find next alphabetic character in original
        while orig_idx < len(original) and not original[orig_idx].isalpha():
            orig_idx += 1
        
        # Apply case from original
        if orig_idx < len(original):
            if original[orig_idx].isupper():
                result.append(char.upper())
            else:
                result.append(char.lower())
            orig_idx += 1
        else:
            # Past end of original, keep as lowercase
            result.append(char)
    
    return ''.join(result)


def correct_sanskrit_diacritics(word: str, correct_n: bool = True,
                                correct_a: bool = True) -> Tuple[str, List[str]]:
    """
    Correct both ñ and å diacritics with case preservation.
    
    Args:
        word: Word to correct
        correct_n: Whether to correct ñ
        correct_a: Whether to correct å
        
    Returns:
        Tuple of (corrected_word, rules_applied)
    """
    if not word:
        return word, []
    
    # Save original for case restoration
    original = word
    all_rules = []
    
    # Normalize to lowercase for processing
    word_lower = word.lower()

    # NOTE: Combined pattern åñ → ṛṣ is now handled in Stage 1 (GLOBAL_CHAR_MAP)
    # No need for special åñṇ → ṛṣṇ handling here anymore

    # Apply individual corrections
    if correct_n:
        word_lower, n_rules = correct_n_diacritic_lowercase(word_lower)
        all_rules.extend(n_rules)
    
    if correct_a:
        word_lower, a_rules = correct_a_diacritic_lowercase(word_lower)
        all_rules.extend(a_rules)
    
    # Restore original case pattern
    result = restore_case_pattern(original, word_lower)
    
    return result, all_rules


def correct_word(token: Token) -> CorrectionResult:
    """
    Correct a single word token.
    
    Args:
        token: Token to correct
        
    Returns:
        CorrectionResult with correction details
    """
    if token.word_class == WordClass.CLEAN:
        return CorrectionResult(
            original=token.text,
            corrected=token.text,
            word_class=WordClass.CLEAN,
            confidence=1.0,
            rules_applied=[],
            changed=False
        )
    
    # Apply corrections
    corrected, rules = correct_sanskrit_diacritics(token.text)
    
    # Determine confidence based on word class
    confidence_map = {
        WordClass.SINGLE_N: 0.99,
        WordClass.SINGLE_A: 0.99,
        WordClass.COMBINED_PATTERN: 0.98,
        WordClass.BOTH_DIACRITICS: 0.95,
        WordClass.MULTIPLE_N: 0.95,
        WordClass.MULTIPLE_A: 0.95,
        WordClass.COMPLEX: 0.90,
    }
    
    confidence = confidence_map.get(token.word_class, 0.90)
    
    return CorrectionResult(
        original=token.text,
        corrected=corrected,
        word_class=token.word_class,
        confidence=confidence,
        rules_applied=rules,
        changed=(token.text != corrected)
    )


# ============================================================================
# STAGE 4: VALIDATION & QUALITY CHECKS
# ============================================================================

def validate_correction(result: CorrectionResult) -> ValidationReport:
    """
    Validate a correction result.
    
    Args:
        result: CorrectionResult to validate
        
    Returns:
        ValidationReport with issues and confidence
    """
    issues = []
    
    # Level 1: Structural validation
    
    # Check for remaining ñ
    if 'ñ' in result.corrected.lower():
        # Check if it's legitimate (jñ, ñc, ñj)
        if not (('jñ' in result.corrected.lower()) or 
                ('ñc' in result.corrected.lower()) or
                ('ñj' in result.corrected.lower())):
            issues.append(ValidationIssue(
                level='ERROR',
                message=f'Remaining ñ in: {result.corrected}',
                suggestion='Manual review required'
            ))
    
    # Check for remaining å
    if 'å' in result.corrected.lower():
        issues.append(ValidationIssue(
            level='ERROR',
            message=f'Remaining å in: {result.corrected}',
            suggestion='Correction failed - check rules'
        ))
    
    # Check length change is reasonable
    len_diff = abs(len(result.corrected) - len(result.original))
    if len_diff > 2:
        issues.append(ValidationIssue(
            level='WARNING',
            message=f'Large length change: {len(result.original)} → {len(result.corrected)}',
            suggestion='Verify correction'
        ))
    
    # Check for valid IAST characters
    for char in result.corrected.lower():
        if char.isalpha() and char not in VALID_IAST_CHARS:
            issues.append(ValidationIssue(
                level='WARNING',
                message=f'Unusual character: {char}',
                suggestion='Verify if valid'
            ))
    
    # Compute final confidence
    final_confidence = result.confidence
    
    # Reduce confidence for issues
    error_count = len([i for i in issues if i.level == 'ERROR'])
    warning_count = len([i for i in issues if i.level == 'WARNING'])
    
    if error_count > 0:
        final_confidence *= 0.7
    if warning_count > 0:
        final_confidence *= 0.9
    
    passed = error_count == 0
    needs_review = final_confidence < 0.90
    
    return ValidationReport(
        passed=passed,
        confidence=final_confidence,
        issues=issues,
        needs_review=needs_review
    )


# ============================================================================
# STAGE 5: TEXT RECONSTRUCTION
# ============================================================================

def reconstruct_text(tokens: List[Token], 
                     corrections: List[CorrectionResult]) -> str:
    """
    Reconstruct text with corrections applied.
    
    Args:
        tokens: Original tokens
        corrections: Correction results
        
    Returns:
        Reconstructed text with corrections
    """
    # Build correction lookup
    correction_map = {}
    for correction in corrections:
        if correction.changed:
            correction_map[correction.original] = correction.corrected
    
    # Reconstruct text
    result_parts = []
    for token in tokens:
        if token.token_type == TokenType.WORD and token.text in correction_map:
            result_parts.append(correction_map[token.text])
        else:
            result_parts.append(token.text)
    
    return ''.join(result_parts)


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def process_page(text: str, page_number: int = 1) -> ProcessedPage:
    """
    Process a page of Sanskrit text through all 5 stages.
    
    Args:
        text: Raw extracted text with OCR errors
        page_number: Page number for tracking
        
    Returns:
        ProcessedPage with complete results
    """
    import time
    start_time = time.time()
    
    stats = PageStatistics()
    
    # STAGE 1: Global Character Map
    stage1_start = time.time()
    text_after_global, replacements = apply_global_char_map(text)
    stats.global_map_replacements = replacements
    stats.stage_times['stage1_global_map'] = time.time() - stage1_start
    
    # STAGE 2: Text Segmentation & Classification
    stage2_start = time.time()
    tokens = tokenize_text(text_after_global)
    tokens = analyze_tokens(tokens)
    
    stats.total_tokens = len(tokens)
    stats.total_words = sum(1 for t in tokens if t.token_type == TokenType.WORD)
    
    # Count word classes
    for token in tokens:
        if token.word_class:
            stats.class_distribution[token.word_class] += 1
    
    stats.stage_times['stage2_tokenization'] = time.time() - stage2_start
    
    # STAGE 3: Pattern-Based Correction
    stage3_start = time.time()
    corrections = []
    
    for token in tokens:
        if token.token_type == TokenType.WORD and token.word_class != WordClass.CLEAN:
            result = correct_word(token)
            corrections.append(result)
            
            if result.changed:
                stats.words_corrected += 1
                
                # Track correction types
                if any('ñ' in r or 'ṣ' in r for r in result.rules_applied):
                    stats.n_corrections += 1
                if any('å' in r or 'ṛ' in r or 'ā' in r for r in result.rules_applied):
                    stats.a_corrections += 1
                if 'combined' in str(result.rules_applied):
                    stats.combined_corrections += 1
                
                # Track rules
                for rule in result.rules_applied:
                    stats.patterns_applied[rule] += 1
    
    stats.stage_times['stage3_correction'] = time.time() - stage3_start
    
    # STAGE 4: Validation
    stage4_start = time.time()
    validation_reports = []
    
    for correction in corrections:
        report = validate_correction(correction)
        validation_reports.append(report)
        
        # Update statistics
        if report.confidence >= 0.95:
            stats.high_confidence += 1
        elif report.confidence >= 0.90:
            stats.medium_confidence += 1
        else:
            stats.low_confidence += 1
        
        if not report.passed:
            stats.validation_errors += 1
        
        if report.needs_review:
            stats.needs_manual_review += 1
    
    stats.stage_times['stage4_validation'] = time.time() - stage4_start
    
    # STAGE 5: Text Reconstruction
    stage5_start = time.time()
    corrected_text = reconstruct_text(tokens, corrections)
    stats.stage_times['stage5_reconstruction'] = time.time() - stage5_start
    
    # Final statistics
    total_time = time.time() - start_time
    stats.processing_time = total_time
    
    return ProcessedPage(
        page_number=page_number,
        original_text=text,
        corrected_text=corrected_text,
        statistics=stats,
        corrections=corrections,
        validation_reports=validation_reports,
        timestamp=datetime.now(),
        processing_time=total_time
    )


def print_page_report(page: ProcessedPage, detailed: bool = False):
    """
    Print a report for processed page.
    
    Args:
        page: ProcessedPage result
        detailed: Whether to print detailed corrections
    """
    print(f"\n{'='*80}")
    print(f"PAGE {page.page_number} - TRANSLITERATION FIX REPORT")
    print(f"{'='*80}")
    print(f"Timestamp: {page.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Processing Time: {page.processing_time*1000:.2f}ms")
    
    print(f"\n{'Stage Times:':<30}")
    for stage, time_val in page.statistics.stage_times.items():
        print(f"  {stage:<28} {time_val*1000:>6.2f}ms")
    
    print(f"\n{'STATISTICS':<30}")
    print(f"{'─'*80}")
    print(f"  {'Total Tokens:':<28} {page.statistics.total_tokens:>6}")
    print(f"  {'Total Words:':<28} {page.statistics.total_words:>6}")
    print(f"  {'Words Corrected:':<28} {page.statistics.words_corrected:>6}")
    
    if page.statistics.global_map_replacements:
        print(f"\n{'Global Map Replacements:':<30}")
        for replacement, count in page.statistics.global_map_replacements.most_common(10):
            print(f"  {replacement:<28} {count:>6}x")
    
    print(f"\n{'Word Classification:':<30}")
    for word_class, count in page.statistics.class_distribution.most_common():
        print(f"  {word_class.name:<28} {count:>6}")
    
    print(f"\n{'Correction Types:':<30}")
    print(f"  {'ñ corrections:':<28} {page.statistics.n_corrections:>6}")
    print(f"  {'å corrections:':<28} {page.statistics.a_corrections:>6}")
    print(f"  {'Combined (åñṇ→ṛṣṇ):':<28} {page.statistics.combined_corrections:>6}")
    
    print(f"\n{'Confidence Distribution:':<30}")
    print(f"  {'High (≥0.95):':<28} {page.statistics.high_confidence:>6}")
    print(f"  {'Medium (0.90-0.95):':<28} {page.statistics.medium_confidence:>6}")
    print(f"  {'Low (<0.90):':<28} {page.statistics.low_confidence:>6}")
    
    if page.statistics.validation_errors > 0 or page.statistics.needs_manual_review > 0:
        print(f"\n{'ATTENTION NEEDED:':<30}")
        if page.statistics.validation_errors > 0:
            print(f"  {'Validation Errors:':<28} {page.statistics.validation_errors:>6}")
        if page.statistics.needs_manual_review > 0:
            print(f"  {'Needs Manual Review:':<28} {page.statistics.needs_manual_review:>6}")
    
    if page.statistics.patterns_applied:
        print(f"\n{'Top Correction Patterns:':<30}")
        for pattern, count in page.statistics.patterns_applied.most_common(10):
            print(f"  {pattern:<28} {count:>6}x")
    
    if detailed and page.corrections:
        print(f"\n{'DETAILED CORRECTIONS':<30}")
        print(f"{'─'*80}")
        print(f"{'Original':<25} {'Corrected':<25} {'Class':<15} {'Conf':<6}")
        print(f"{'─'*80}")
        
        for corr in page.corrections[:50]:  # Limit to first 50
            if corr.changed:
                print(f"{corr.original:<25} {corr.corrected:<25} "
                      f"{corr.word_class.name:<15} {corr.confidence:.2f}")
        
        if len(page.corrections) > 50:
            print(f"... and {len(page.corrections) - 50} more corrections")
    
    # Show flagged items
    flagged = [
        (corr, report) 
        for corr, report in zip(page.corrections, page.validation_reports)
        if report.needs_review
    ]
    
    if flagged:
        print(f"\n{'ITEMS FLAGGED FOR REVIEW':<30}")
        print(f"{'─'*80}")
        for corr, report in flagged[:20]:  # Limit to first 20
            print(f"  {corr.original} → {corr.corrected} (conf: {report.confidence:.2f})")
            for issue in report.issues:
                print(f"    [{issue.level}] {issue.message}")
        
        if len(flagged) > 20:
            print(f"... and {len(flagged) - 20} more flagged items")
    
    print(f"\n{'='*80}\n")


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

def main():
    """Example usage of the transliteration fix system."""
    
    # Example text with various issues
    sample_text = """
    The Bhagavatāmåta describes the life of Kåñṇa. The småti texts mention 
    that Balaråma was the brother of Kåñṇa. According to Ajñāna philosophy,
    ignorance is the cause of suffering. The Påñcabadrī temples are sacred.
    In the gåhastha åśrama, one follows the path of dharma.
    
    Småtis like Manusmåti provide guidance. The Båhadāraṇyaka Upaniñad 
    discusses the nature of reality. Pañca means five in Sanskrit.
    The śiñya learns from the guru through añjali.
    """
    
    print("\n" + "="*80)
    print("SANSKRIT IAST TRANSLITERATION FIX SYSTEM - DEMONSTRATION")
    print("="*80)
    
    print("\nORIGINAL TEXT:")
    print("─"*80)
    print(sample_text)
    
    # Process the page
    result = process_page(sample_text, page_number=1)
    
    print("\n\nCORRECTED TEXT:")
    print("─"*80)
    print(result.corrected_text)
    
    # Print report
    print_page_report(result, detailed=True)
    
    # Test case preservation
    print("\n" + "="*80)
    print("CASE PRESERVATION TEST")
    print("="*80)
    
    test_words = [
        "kåñṇa", "Kåñṇa", "KÅÑṆA",
        "småti", "Småti", "SMÅTI",
        "bhagavån", "Bhagavån", "BHAGAVÅN"
    ]
    
    print(f"\n{'Input':<20} {'Output':<20} {'Rules Applied'}")
    print("─"*80)
    for word in test_words:
        corrected, rules = correct_sanskrit_diacritics(word)
        print(f"{word:<20} {corrected:<20} {', '.join(rules[:2])}")


if __name__ == "__main__":
    main()
