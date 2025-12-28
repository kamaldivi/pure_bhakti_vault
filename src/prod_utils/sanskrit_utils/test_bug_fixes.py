#!/usr/bin/env python3
"""
Comprehensive Test Suite for Sanskrit Transliteration Bug Fixes
================================================================

This file documents and tests all critical bug fixes made to the
transliteration system.

Version History:
- v1.0.1: Added __init__.py and expanded VALID_IAST_CHARS
- v1.0.2: Fixed uppercase diacritics being dropped
- v1.0.3: Fixed numeric digits and special chars being removed

Run this test to verify all fixes are working correctly.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from prod_utils.sanskrit_utils import process_page


def test_v1_0_3_numeric_digits_preservation():
    """
    Bug Fix v1.0.3: Numeric digits were being removed

    Root cause: Regex pattern [^\s\w]+ excluded digits since \w matches [a-zA-Z0-9_]
    Fix: Added fourth capture group (\d+|.) to explicitly preserve digits
    """
    print("\n" + "="*80)
    print("TEST v1.0.3: Numeric Digits Preservation")
    print("="*80)

    test_cases = [
        ("Page 123", "Page 123"),
        ("The year 2024 has 365 days", "The year 2024 has 365 days"),
        ("Chapter 4, verse 10", "Chapter 4, verse 10"),
        ("Born in 3227 BCE", "Born in 3227 BCE"),
        ("Verses 1-18", "Verses 1-18"),
    ]

    all_passed = True
    for input_text, expected in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}' → '{result.corrected_text}'")
        if not passed:
            print(f"        Expected: '{expected}'")

    return all_passed


def test_v1_0_3_special_chars_preservation():
    """
    Bug Fix v1.0.3: Special characters (@#$%^&*() etc.) were being removed

    All non-IAST characters should be preserved exactly as-is.
    """
    print("\n" + "="*80)
    print("TEST v1.0.3: Special Characters Preservation")
    print("="*80)

    test_cases = [
        ("Email: user@example.com", "Email: user@example.com"),
        ("Price: $99.99", "Price: $99.99"),
        ("Test @#$%^&*()", "Test @#$%^&*()"),
        ("[brackets] {braces} <angles>", "[brackets] {braces} <angles>"),
        ("Symbols: !? ~`", "Symbols: !? ~`"),
    ]

    all_passed = True
    for input_text, expected in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}'")
        if not passed:
            print(f"        Got: '{result.corrected_text}'")
            print(f"        Expected: '{expected}'")

    return all_passed


def test_v1_0_3_n_diacritic_preservation():
    """
    Verification v1.0.3: ñ should be preserved when appropriate

    User reported "jñāna becoming jāna" but testing shows ñ is preserved correctly.
    This test verifies that ñ is preserved in legitimate contexts.
    """
    print("\n" + "="*80)
    print("TEST v1.0.3: ñ Diacritic Preservation")
    print("="*80)

    test_cases = [
        # ñ should be preserved in these contexts
        ("jñāna", "jñāna", "Knowledge (legitimate jñ combination)"),
        ("Ajñāna", "Ajñāna", "Ignorance (legitimate jñ combination)"),
        ("vijñāna", "vijñāna", "Science (legitimate jñ combination)"),
        ("jñeya", "jñeya", "To be known (legitimate jñ combination)"),

        # But ñ should be corrected to ṣ in these contexts
        ("kåñṇa", "kṛṣṇa", "Krishna (OCR error correction)"),
        ("viñṇu", "viṣṇu", "Vishnu (OCR error correction)"),
    ]

    all_passed = True
    for input_text, expected, description in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}' → '{result.corrected_text}' ({description})")
        if not passed:
            print(f"        Expected: '{expected}'")

    return all_passed


def test_v1_0_2_uppercase_diacritics():
    """
    Bug Fix v1.0.2: Uppercase diacritics (Ā, Ī, Ś, Ṣ) were being dropped

    Root cause: Tokenization regex only included lowercase diacritics
    Fix: Added uppercase IAST diacritics to pattern
    """
    print("\n" + "="*80)
    print("TEST v1.0.2: Uppercase Diacritic Preservation")
    print("="*80)

    test_cases = [
        ("ĀŚRAMA", "ĀŚRAMA"),
        ("GĪTĀ", "GĪTĀ"),
        ("ŚRĪ", "ŚRĪ"),
        ("ĪŚVARA", "ĪŚVARA"),
        ("BHAGAVAD-GĪTĀ", "BHAGAVAD-GĪTĀ"),
        ("KṚṢṆA", "KṚṢṆA"),
    ]

    all_passed = True
    for input_text, expected in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}' → '{result.corrected_text}'")
        if not passed:
            print(f"        Expected: '{expected}'")

    return all_passed


def test_corrections_still_working():
    """
    Regression Test: Verify that legitimate corrections still work

    After fixing bugs, we must ensure the core correction functionality
    (å → ṛ/ā, ñ → ṣ/ñ) still works correctly.
    """
    print("\n" + "="*80)
    print("REGRESSION TEST: Corrections Still Working")
    print("="*80)

    test_cases = [
        # å corrections
        ("kåñṇa", "kṛṣṇa", "Krishna"),
        ("Bhagavån", "Bhagavān", "Bhagavan"),
        ("småti", "smṛti", "Smriti"),

        # ñ corrections
        ("viñṇu", "viṣṇu", "Vishnu"),
        ("kåñṇa", "kṛṣṇa", "Krishna (combined)"),

        # Combined patterns
        ("Śrī Kåñṇa", "Śrī Kṛṣṇa", "Sri Krishna"),
    ]

    all_passed = True
    for input_text, expected, description in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}' → '{result.corrected_text}' ({description})")
        if not passed:
            print(f"        Expected: '{expected}'")

    return all_passed


def test_case_preservation():
    """
    Regression Test: Verify case preservation still works

    The system should preserve original case: lowercase, UPPERCASE, Title Case, mixed
    """
    print("\n" + "="*80)
    print("REGRESSION TEST: Case Preservation")
    print("="*80)

    test_cases = [
        # Lowercase
        ("kåñṇa", "kṛṣṇa", "lowercase"),

        # UPPERCASE
        ("KÅÑṆA", "KṚṢṆA", "UPPERCASE"),

        # Title Case
        ("Kåñṇa", "Kṛṣṇa", "Title Case"),

        # Mixed case preservation
        ("śrī", "śrī", "lowercase with diacritics"),
        ("ŚRĪ", "ŚRĪ", "UPPERCASE with diacritics"),
        ("Śrī", "Śrī", "Title Case with diacritics"),
    ]

    all_passed = True
    for input_text, expected, description in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: '{input_text}' → '{result.corrected_text}' ({description})")
        if not passed:
            print(f"        Expected: '{expected}'")

    return all_passed


def test_mixed_content_real_world():
    """
    Integration Test: Real-world mixed content with IAST + digits + special chars

    This simulates actual PDF page content with Sanskrit text, English text,
    page numbers, punctuation, etc.
    """
    print("\n" + "="*80)
    print("INTEGRATION TEST: Real-World Mixed Content")
    print("="*80)

    test_cases = [
        (
            "Page 123\n\nŚrī Kṛṣṇa was born in 3227 BCE.",
            "Page 123\n\nŚrī Kṛṣṇa was born in 3227 BCE.",
            "Page header + Sanskrit + date"
        ),
        (
            "BHAGAVAD-GĪTĀ Chapter 18, verse 66",
            "BHAGAVAD-GĪTĀ Chapter 18, verse 66",
            "Uppercase title + numbers"
        ),
        (
            "The word jñāna (knowledge) appears in verse 4.39.",
            "The word jñāna (knowledge) appears in verse 4.39.",
            "Sanskrit word in English context + decimal number"
        ),
        (
            "Contact: info@example.com | Price: $99.99",
            "Contact: info@example.com | Price: $99.99",
            "Email and currency"
        ),
    ]

    all_passed = True
    for input_text, expected, description in test_cases:
        result = process_page(input_text, page_number=1)
        passed = result.corrected_text == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {description}")
        if not passed:
            print(f"        Input:    '{input_text}'")
            print(f"        Got:      '{result.corrected_text}'")
            print(f"        Expected: '{expected}'")

    return all_passed


def run_all_tests():
    """Run all test suites and report results."""
    print("\n" + "="*80)
    print("SANSKRIT TRANSLITERATION BUG FIX TEST SUITE")
    print("="*80)
    print("Testing all bug fixes and regression tests...")
    print()

    results = {}

    # Run all test suites
    results['v1.0.3 Numeric Digits'] = test_v1_0_3_numeric_digits_preservation()
    results['v1.0.3 Special Chars'] = test_v1_0_3_special_chars_preservation()
    results['v1.0.3 ñ Preservation'] = test_v1_0_3_n_diacritic_preservation()
    results['v1.0.2 Uppercase Diacritics'] = test_v1_0_2_uppercase_diacritics()
    results['Corrections Still Working'] = test_corrections_still_working()
    results['Case Preservation'] = test_case_preservation()
    results['Real-World Mixed Content'] = test_mixed_content_real_world()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    total_tests = len(results)
    passed_tests = sum(1 for passed in results.values() if passed)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "="*80)
    print(f"FINAL RESULT: {passed_tests}/{total_tests} test suites passed")
    print("="*80)

    if passed_tests == total_tests:
        print("\n✓ All tests passed! System is working correctly.")
        return 0
    else:
        print(f"\n✗ {total_tests - passed_tests} test suite(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
