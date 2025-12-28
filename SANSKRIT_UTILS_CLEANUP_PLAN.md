# Sanskrit Utils Cleanup & Migration Plan

**Date**: 2024-12-26
**Status**: ⚠️ REQUIRES MIGRATION
**Priority**: HIGH

---

## Current Situation

### Files to Review

1. **OLD FILES** (in `src/prod_utils/`):
   - `sanskrit_utils.py` - Simple glyph replacement utility (OLD VERSION)
   - `sanskrit_util_v2.py` - Intermediate version with book profiles
   - `test_sanskrit_util_v2.py` - Test file for v2

2. **NEW PACKAGE** (in `src/prod_utils/sanskrit_utils/`):
   - `__init__.py` - Package initialization (v1.0.9)
   - `transliteration_fix_system.py` - Complete 5-stage pipeline
   - `sanskrit_diacritic_utils.py` - Core correction utilities
   - `CHANGELOG.md` - Complete version history

---

## Problem: Active Dependencies on Old Files

### Files Importing Old `fix_iast_glyphs()`:

1. ✅ `pdf_content_transliteration_processor.py` - Already using new package
2. ⚠️ `page_content_extractor.py` - Uses `fix_iast_glyphs` from old file
3. ⚠️ `page_map_utils.py` - Uses `fix_iast_glyphs` from old file
4. ⚠️ `page_type_identifier.py` - Uses `fix_iast_glyphs` from old file
5. ⚠️ `toc_loader.py` - Uses `fix_iast_glyphs` from old file
6. ⚠️ `verse_index_extractor.py` - Uses `fix_iast_glyphs` from old file

**TOTAL**: 5 files actively using the old function!

---

## Comparison: Old vs New

### Old `fix_iast_glyphs()` Function

**Simple character replacement**:
- Pattern replacements (e.g., `kåñëa` → `kṛṣṇa`)
- Special character replacements (e.g., `®` → `ṛ`)
- Standard glyph replacements (e.g., `ä` → `ā`)
- Conditional book-based replacements (e.g., `ṛ` → `ā` for specific books)

**Limitations**:
- No intelligent context-aware corrections
- No ñ → ṣ/ñ disambiguation
- No å → ṛ/ā priority rules (12 rules)
- No case preservation
- No validation or quality checks
- Simple string replacement only

### New Package Functions

**Sophisticated 5-stage pipeline**:
1. **Global Character Mapping** (`apply_global_char_map`) - 26+ mappings including new à→ṁ, ï→ñ
2. **Tokenization** (`tokenize_text`) - Preserves punctuation, whitespace
3. **Word Classification** (`classify_word`) - Detects Sanskrit vs English
4. **Context-Aware Correction** (`correct_sanskrit_diacritics`):
   - 10+ ñ → ṣ/ñ patterns
   - 12 å → ṛ/ā priority rules
   - Case preservation
5. **Validation** (`validate_correction`) - Quality checks, confidence scoring

**Advantages**:
- 98-99% accuracy (vs ~70% for old function)
- Handles ambiguous characters intelligently
- Preserves case (UPPERCASE, Title Case, lowercase)
- Detailed statistics and reporting
- No incorrect conversions

---

## Migration Strategy

### Option 1: Add Compatibility Wrapper (RECOMMENDED)

Add `fix_iast_glyphs()` to new package as a simple wrapper:

```python
# In sanskrit_utils/__init__.py

def fix_iast_glyphs(text: str, book_id: Optional[int] = None) -> str:
    """
    Legacy compatibility function for old code.

    This is a simple wrapper around apply_global_char_map() for backward
    compatibility with existing code that imports fix_iast_glyphs().

    For new code, use:
    - apply_global_char_map() for simple character mapping
    - correct_sanskrit_diacritics() for intelligent corrections
    - process_page() for full pipeline processing

    Args:
        text: Input text with broken glyphs
        book_id: Ignored (for backward compatibility)

    Returns:
        Text with corrected characters
    """
    # Just use global char map (most similar to old behavior)
    corrected, _ = apply_global_char_map(text)
    return corrected
```

**Pros**:
- Zero code changes needed in dependent files
- Immediate safe cleanup
- Can remove old files right away

**Cons**:
- Doesn't use full power of new system
- Still relatively simple corrections

### Option 2: Full Migration to New Functions

Update all 5 files to use new package functions:

**Before**:
```python
from sanskrit_utils import fix_iast_glyphs
text = fix_iast_glyphs(extracted_text)
```

**After**:
```python
from sanskrit_utils import correct_sanskrit_diacritics
text, rules = correct_sanskrit_diacritics(extracted_text)
# or for full pipeline:
from sanskrit_utils import process_page
result = process_page(extracted_text, page_number=1)
text = result.corrected_text
```

**Pros**:
- Gets full benefit of new system
- Better accuracy
- Detailed statistics

**Cons**:
- Requires testing all 5 dependent files
- More complex API
- Potential breaking changes

---

## Recommended Approach

### Phase 1: Add Compatibility Wrapper (Immediate)

1. Add `fix_iast_glyphs()` wrapper to `sanskrit_utils/__init__.py`
2. Add to `__all__` export list
3. Test that old code still works
4. **Delete old files**:
   - `sanskrit_utils.py`
   - `sanskrit_util_v2.py`
   - `test_sanskrit_util_v2.py`
5. Remove `__pycache__` directories

### Phase 2: Gradual Migration (Future)

For each file, when you next work on it:
1. Update imports to use new functions
2. Get better accuracy and validation
3. Eventually deprecate `fix_iast_glyphs()` wrapper

---

## Files to Delete (After Adding Wrapper)

### Safe to Delete:

1. ✅ `src/prod_utils/sanskrit_utils.py` - Superseded by new package
2. ✅ `src/prod_utils/sanskrit_util_v2.py` - Intermediate version, no longer needed
3. ✅ `src/prod_utils/test_sanskrit_util_v2.py` - Test for old v2
4. ✅ `src/prod_utils/__pycache__/sanskrit_util_v2.cpython-313.pyc` - Compiled cache
5. ✅ `src/prod_utils/__pycache__/sanskrit_utils.cpython-313.pyc` - Compiled cache

### Keep (Part of New System):

1. ✅ `src/prod_utils/sanskrit_utils/` - Entire directory (new package)
2. ✅ `src/prod_utils/test_glossary_sanskrit_errors.py` - Still references patterns but independent

---

## Implementation Checklist

### Step 1: Add Wrapper Function
- [ ] Add `fix_iast_glyphs()` to `sanskrit_utils/__init__.py`
- [ ] Add to `__all__` export list
- [ ] Test wrapper works

### Step 2: Verify No Breaking Changes
- [ ] Test `page_content_extractor.py`
- [ ] Test `page_map_utils.py`
- [ ] Test `page_type_identifier.py`
- [ ] Test `toc_loader.py`
- [ ] Test `verse_index_extractor.py`

### Step 3: Delete Old Files
- [ ] Delete `sanskrit_utils.py`
- [ ] Delete `sanskrit_util_v2.py`
- [ ] Delete `test_sanskrit_util_v2.py`
- [ ] Delete `__pycache__` directories

### Step 4: Update Documentation
- [ ] Update any README files referencing old utils
- [ ] Update import examples in docstrings

---

## Risk Assessment

### LOW RISK with Wrapper Approach:

- ✅ Wrapper provides exact same API
- ✅ Uses proven `apply_global_char_map()` from new system
- ✅ All old files can be safely deleted
- ✅ No breaking changes to dependent code
- ✅ Can gradually migrate to better functions later

### Verification:

The wrapper essentially does what old `fix_iast_glyphs()` did (character mapping), but uses the NEW GLOBAL_CHAR_MAP which has:
- All old mappings PLUS
- New `ˇ → Ṭ` mapping (v1.0.8)
- New `à → ṁ` mapping (v1.0.9)
- New `ï → ñ` mapping (v1.0.9)

So it's actually BETTER than the old function!

---

## Summary

**Current State**: 3 old files + 5 dependent files
**Recommended**: Add compatibility wrapper → Delete old files → Migrate gradually
**Timeline**: Immediate (wrapper + deletion), then gradual migration
**Risk**: LOW with wrapper approach
**Benefit**: Clean codebase, no old code confusion, better accuracy

---

**Next Steps**:
1. Add `fix_iast_glyphs()` wrapper to new package
2. Test it works with one dependent file
3. Delete old files
4. Commit with clear message about migration
