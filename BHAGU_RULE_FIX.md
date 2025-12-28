# bhågu Rule Fix + Visarga Enhancement - Sanskrit Diacritic Utils

## Issue Reports

### Issue 1: bhågu Pattern
**Problem**: Words like "bhågu" were being incorrectly converted to "bhāgu" instead of "bhṛgu"

**Root Cause**: Missing rule for bhåg → bhṛg pattern in `correct_a_diacritic()` function

### Issue 2: Visarga Form Not Handled
**Problem**: Words like "båḥ" were being incorrectly converted to "bāḥ" instead of "bṛḥ"

**Root Cause**: Rule 1 only matched `åh` (plain h) but not `åḥ` (visarga ḥ = U+1E25)

## Fixes Applied

### Changes to `sanskrit_diacritic_utils.py`

**Rule 1 Enhancement (åh/åḥ → ṛh/ṛḥ) - Fixed**:

```python
# OLD (INCOMPLETE):
corrected = corrected.replace('åh', 'ṛh')
corrected = corrected.replace('Åh', 'Ṛh')
corrected = corrected.replace('ÅH', 'ṚH')

# NEW (COMPLETE):
corrected = corrected.replace('åh', 'ṛh')
corrected = corrected.replace('Åh', 'Ṛh')
corrected = corrected.replace('ÅH', 'ṚH')
corrected = corrected.replace('åḥ', 'ṛḥ')  # NEW - visarga
corrected = corrected.replace('Åḥ', 'Ṛḥ')  # NEW - visarga
corrected = corrected.replace('ÅḤ', 'ṚḤ')  # NEW - visarga
```

**Location**: Lines 146-151

**Rule 13 (bhåg → bhṛg) - Added**:

```python
# NEW (ADDED):
# Rule 13: bhåg → bhṛg (Bhṛgu - Vedic sage name)
corrected = corrected.replace('bhåg', 'bhṛg')
corrected = corrected.replace('Bhåg', 'Bhṛg')
corrected = corrected.replace('BHÅG', 'BHṚG')
```

**Location**: Lines 225-228 (before default å → ā conversion)

## Test Results

### Before Fix ❌
```
bhågu      → bhāgu      (WRONG - should be bhṛgu)
Bhågu      → Bhāgu      (WRONG - should be Bhṛgu)
bhågavat   → bhāgavat   (WRONG - should be bhṛgavat)
båḥ        → bāḥ        (WRONG - should be bṛḥ)
Båḥ        → Bāḥ        (WRONG - should be Bṛḥ)
```

### After Fix ✅
```
✓ bhågu      → bhṛgu       (Bhṛgu - Vedic sage name)
✓ Bhågu      → Bhṛgu       (Capitalized)
✓ BHÅGU      → BHṚGU       (Uppercase)
✓ bhågavat   → bhṛgavat    (Compound words)
✓ Bhågavat   → Bhṛgavat    (Compound capitalized)
✓ bhå        → bhā         (Default case preserved)
✓ bhårata    → bhārata     (Default case preserved)
✓ båḥ        → bṛḥ         (Visarga form - FIXED)
✓ Båḥ        → Bṛḥ         (Visarga capitalized - FIXED)
✓ BÅḤ        → BṚḤ         (Visarga uppercase - FIXED)
```

## Comprehensive Test Results

All 29 test cases for å diacritic rules now pass (including visarga forms):

```
✓ båhad          → bṛhad            (Rule 1: åh → ṛh)
✓ gåha           → gṛha             (Rule 1: åh → ṛh)
✓ båḥ            → bṛḥ              (Rule 1: åḥ → ṛḥ - visarga - FIXED)
✓ Båḥ            → Bṛḥ              (Rule 1: åḥ → ṛḥ - visarga - FIXED)
✓ amåta          → amṛta            (Rule 2: måt → mṛt)
✓ Amåta          → Amṛta            (Rule 2: måt → mṛt)
✓ småti          → smṛti            (Rule 3: småt → smṛt)
✓ gåhīta         → gṛhīta           (Rule 4: gåhī → gṛhī)
✓ tåpta          → tṛpta            (Rule 5: tåpt → tṛpt)
✓ tåṇa           → tṛṇa             (Rule 6: tåṇ → tṛṇ)
✓ dåḍha          → dṛḍha            (Rule 7: dåḍh → dṛḍh)
✓ dåśya          → dṛśya            (Rule 8: dåśy → dṛśy)
✓ prakåti        → prakṛti          (Rule 9: prakåt → prakṛt)
✓ kåta           → kṛta             (Rule 10: kåt → kṛt)
✓ Kåta           → Kṛta             (Rule 10: kåt → kṛt)
✓ vånda          → vṛnda            (Rule 11: vånd → vṛnd)
✓ Våndāvana      → Vṛndāvana        (Rule 11: vånd → vṛnd)
✓ dhåta          → dhṛta            (Rule 12: dhåt → dhṛt)
✓ dhåtrāṣṭra     → dhṛtarāṣṭra      (Rule 12: dhåtr → dhṛtar)
✓ Dhåtrāṣṭra     → Dhṛtarāṣṭra      (Rule 12: dhåtr → dhṛtar)
✓ vidhåtā        → vidhātā          (Rule 12: Exception preserved)
✓ adhåta         → adhṛta           (Rule 12: Mid-word conversion)
✓ bhågu          → bhṛgu            (Rule 13: bhåg → bhṛg - NEW)
✓ Bhågu          → Bhṛgu            (Rule 13: bhåg → bhṛg - NEW)
✓ bhågavat       → bhṛgavat         (Rule 13: bhåg → bhṛg - NEW)
✓ Bhagavån       → Bhagavān         (Default: å → ā)
✓ kåla           → kāla             (Default: å → ā)
✓ bhå            → bhā              (Default: å → ā)
✓ bhårata        → bhārata          (Default: å → ā)
```

## Technical Details

### Visarga Issue

**Unicode Character Distinction**:
- Plain 'h': U+0068 (Latin Small Letter H)
- Visarga 'ḥ': U+1E25 (Latin Small Letter H with Dot Below)

These are **different Unicode characters**, so pattern matching for `åh` does NOT match `åḥ`.

**Why This Matters**:
Visarga (ḥ) is extremely common in Sanskrit, especially at word endings. Without handling both forms, a large number of words would be incorrectly converted.

**Example Words**:
- बृहत् (bṛhat) → vaak appears as "båḥ" in OCR → should be "bṛḥ" not "bāḥ"
- गृह: (gṛhaḥ) → appears as "gåhaḥ" in OCR → should be "gṛhaḥ"

### bhågu Pattern Analysis

**Problem**:
The pattern "bhå" (without 'g') should convert to "bhā" (default case) for most words like:
- bhårata → bhārata (India)
- bhå → bhā (light, splendor)

However, "bhåg" specifically should convert to "bhṛg" for:
- bhågu → bhṛgu (Bhṛgu - famous Vedic sage)
- bhågavat → bhṛgavat (compounds with Bhṛgu)

**Solution**:
Add specific pattern matching for "bhåg" BEFORE the default å → ā conversion. This ensures:
1. "bhågu" matches "bhåg" → "bhṛg" pattern first → "bhṛgu" ✓
2. "bhårata" doesn't match "bhåg" → falls through to default → "bhārata" ✓

### Why This Pattern?

**Bhṛgu** is a prominent figure in Vedic literature:
- One of the Saptarishi (Seven Great Sages)
- Author of Bhṛgu Saṃhitā (astrological text)
- Father of Śukrācārya
- Referenced extensively in Purāṇas and Mahābhārata

OCR often misreads the "ṛ" (vocalic r) as "å" in this name, requiring special handling.

## Impact

This fix affects:
- **Bhṛgu** - Vedic sage name
- **Bhṛgavaḥ** - Descendants of Bhṛgu
- All compounds with bhṛg/bhṛgu
- Preserves correct behavior for "bhå" in other contexts (bhārata, bhā)

## Version

Fixed in: **sanskrit_utils v1.0.11** (unreleased)
Previous version: v1.0.10

## Files Modified

- `src/prod_utils/sanskrit_utils/sanskrit_diacritic_utils.py`
  - Lines 225-228: Rule 13 (bhåg → bhṛg) added
  - Lines 119: Docstring updated to include Rule 13

## Backward Compatibility

✅ Fully backward compatible - only fixes incorrect behavior
- All previous correct conversions still work
- New conversions now work correctly
- No breaking changes to API

## Testing

Run comprehensive tests:
```bash
cd src/prod_utils
python3 -c "
from sanskrit_utils import correct_a_diacritic
print(correct_a_diacritic('bhågu'))      # Should output: bhṛgu
print(correct_a_diacritic('Bhågu'))      # Should output: Bhṛgu
print(correct_a_diacritic('bhårata'))    # Should output: bhārata
print(correct_a_diacritic('bhå'))        # Should output: bhā
"
```

Expected output:
```
bhṛgu
Bhṛgu
bhārata
bhā
```

## Related Issues

This is the third fix in the å diacritic series:
1. **DHAT_RULE_FIX.md** - Fixed dhåt → dhṛt and dhåtr → dhṛtar patterns
2. **SESSION_SUMMARY_2025-12-26.md** - Simplified ñ diacritic logic
3. **BHAGU_RULE_FIX.md** (THIS FILE) - Added bhåg → bhṛg pattern + fixed visarga handling in Rule 1

## Summary of Changes

Two important fixes in v1.0.11:

1. **Rule 13 (NEW)**: Added `bhåg → bhṛg` pattern for Bhṛgu and related words
2. **Rule 1 (ENHANCED)**: Added visarga support `åḥ → ṛḥ` alongside existing `åh → ṛh`

Both fixes are backward compatible and add new functionality without breaking existing conversions.
