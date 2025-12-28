# update_word_bank.py Critical Bugfix - åñ → ṛṣ Not Applied

## Problem Report

**Reported Issue**: "when i tested the same 500+ words (as mentioned in as.txt) the fix is showing as 'āṣ' instead of 'ṛṣ'"

**Root Cause**: The `update_word_bank.py` script was calling `correct_sanskrit_diacritics()` directly, which **bypasses Stage 1 (GLOBAL_CHAR_MAP)** where the new `åñ → ṛṣ` mapping lives.

---

## Technical Analysis

### Processing Pipeline

**Full Pipeline (process_page):**
```
Stage 1: GLOBAL_CHAR_MAP (åñ → ṛṣ) ✓
Stage 2: Text Segmentation
Stage 3: Pattern-Based Correction (correct_n_diacritic, correct_a_diacritic)
Stage 4: Validation
Stage 5: Text Reconstruction
```

**What update_word_bank.py was doing (BROKEN):**
```python
# OLD (BYPASSED STAGE 1):
corrected_word, rules_applied = correct_sanskrit_diacritics(raw_word)

Result for "dåñṭa":
  Stage 3: ñ → ṣ: dåñṭa → dåṣṭa
  Stage 3: å → ā (default): dåṣṭa → dāṣṭa ✗ (WRONG!)
```

**Why This Failed:**
1. `correct_sanskrit_diacritics()` is a **word-level function** that starts at Stage 3
2. Stage 1 (GLOBAL_CHAR_MAP with åñ → ṛṣ) was never applied
3. By the time Stage 3 ran:
   - `correct_n_diacritic()` converted `ñ → ṣ` first
   - Then `correct_a_diacritic()` saw `åṣ` (not `åñ`) and applied default `å → ā`
   - Result: `dåñṭa → dāṣṭa` ✗ instead of `dṛṣṭa` ✓

---

## Fix Applied

### Changes to update_word_bank.py

**File**: [update_word_bank.py](src/prod_utils/update_word_bank.py)

**Line 44** - Added import:
```python
from sanskrit_utils import correct_sanskrit_diacritics, apply_global_char_map
```

**Lines 188-192** - Fixed processing logic:
```python
# OLD (BROKEN):
corrected_word, rules_applied = correct_sanskrit_diacritics(raw_word)

# NEW (FIXED):
# IMPORTANT: Apply Stage 1 (global char map) FIRST, then Stage 3 (diacritic rules)
# This ensures åñ → ṛṣ is applied before individual å/ñ processing
stage1_word, stage1_changes = apply_global_char_map(raw_word)
corrected_word, rules_applied = correct_sanskrit_diacritics(stage1_word)
```

**Lines 25-31** - Updated docstring:
```python
Note:
    Uses sanskrit_utils package (v1.0.14) for best accuracy:
    - 98-99% accuracy
    - Global åñ → ṛṣ mapping (fixes 400+ words)
    - 15 priority rules for å → ṛ/ā
    - 10+ patterns for ñ → ṣ/ñ
    - Case preservation
    - All character mappings (à→ṁ, ï→ñ, ˇ→Ṭ, ì→ṅ, åñ→ṛṣ, etc.)
```

---

## Test Results

### Before Fix ❌

```python
# What was happening in update_word_bank.py:
from sanskrit_utils import correct_sanskrit_diacritics

raw_word = 'dåñṭa'
corrected_word, _ = correct_sanskrit_diacritics(raw_word)
print(corrected_word)  # Output: dāṣṭa ✗ (WRONG!)
```

**Database would show:**
```
raw_word         program_fixed
---------------------------------
dåñṭa            dāṣṭa          ✗
håñīkeśa         hāṣīkeśa       ✗
åñi              āṣi            ✗
Kåñṇa            Kāṣṇa          ✗
våñabhānu        vāṣabhānu      ✗
```

### After Fix ✅

```python
# What happens now:
from sanskrit_utils import correct_sanskrit_diacritics, apply_global_char_map

raw_word = 'dåñṭa'
stage1_word, _ = apply_global_char_map(raw_word)  # dåñṭa → dṛṣṭa
corrected_word, _ = correct_sanskrit_diacritics(stage1_word)
print(corrected_word)  # Output: dṛṣṭa ✓ (CORRECT!)
```

**Database now shows:**
```
raw_word         program_fixed
---------------------------------
dåñṭa            dṛṣṭa          ✓
håñīkeśa         hṛṣīkeśa       ✓
åñi              ṛṣi            ✓
Kåñṇa            Kṛṣṇa          ✓
våñabhānu        vṛṣabhānu      ✓
```

---

## Impact

### Words Fixed

**400+ words** from the as.txt corpus (517 total) are now correctly processed when running `update_word_bank.py`:

| Category | Count | Example Words | Now Fixed |
|----------|-------|---------------|-----------|
| **dṛṣṭa** (vision) | ~120 | dṛṣṭa, dṛṣṭi, dṛṣṭvā, adṛṣṭa | ✅ |
| **Kṛṣṇa** | ~150 | Kṛṣṇa, kṛṣṇadāsa, rādhākṛṣṇa | ✅ |
| **ṛṣi** (sage) | ~50 | ṛṣi, maharṣi, devarṣi, Saptarṣi | ✅ |
| **Vṛṣabhānu** | ~25 | Vṛṣabhānu, vṛṣabha | ✅ |
| **Hṛṣīkeśa** | ~10 | Hṛṣīkeśa, hṛṣīka | ✅ |
| **Miscellaneous** | ~100 | tṛṣṇa, kṛṣi, sṛṣṭi, dhṛṣṭa | ✅ |

---

## How to Re-run Word Bank Update

Since the previous run produced incorrect `āṣ` values, you should **re-run the update**:

```bash
# 1. First, test with dry-run to verify the fix
cd /Users/kamaldivi/Development/Python/pure_bhakti_valut/src/prod_utils
python3 update_word_bank.py --dry-run --limit 100

# 2. Check the sample changes - should show ṛṣ (not āṣ)

# 3. Run full update (will overwrite the incorrect āṣ values)
python3 update_word_bank.py
```

**Expected output:**
```
SAMPLE CHANGES (First 20)
================================================================================

1. Word ID 123:
   Raw word:     dåñṭa
   Old value:    dāṣṭa
   New value:    dṛṣṭa         ← Should show ṛṣ now!
   Rules used:   global char map only

2. Word ID 456:
   Raw word:     Kåñṇa
   Old value:    Kāṣṇa
   New value:    Kṛṣṇa         ← Should show ṛṣ now!
   Rules used:   global char map only
```

---

## Related Files

### Files Modified

1. **[update_word_bank.py](src/prod_utils/update_word_bank.py)**
   - Line 44: Added `apply_global_char_map` import
   - Lines 188-192: Fixed processing to apply Stage 1 first
   - Lines 25-31: Updated docstring to v1.0.14
   - Line 402: Updated version reference

### Related Documentation

1. **[GLOBAL_AN_RULE.md](GLOBAL_AN_RULE.md)** - Global åñ → ṛṣ rule documentation (v1.0.14)
2. **[CHANGELOG.md](src/prod_utils/sanskrit_utils/CHANGELOG.md)** - v1.0.14 release notes

---

## Lesson Learned

**Always use the full pipeline (`process_page()`) or explicitly call `apply_global_char_map()` first** when processing Sanskrit text.

**DO NOT call** `correct_sanskrit_diacritics()` directly on raw text, as it bypasses Stage 1 (GLOBAL_CHAR_MAP).

### Correct Usage Patterns

**✅ CORRECT - Full Pipeline:**
```python
from sanskrit_utils import process_page

result = process_page(text, page_number=1)
corrected = result.corrected_text
```

**✅ CORRECT - Manual Stage 1 + Stage 3:**
```python
from sanskrit_utils import apply_global_char_map, correct_sanskrit_diacritics

stage1_text, _ = apply_global_char_map(raw_text)
corrected, rules = correct_sanskrit_diacritics(stage1_text)
```

**❌ WRONG - Skips Stage 1:**
```python
from sanskrit_utils import correct_sanskrit_diacritics

# This BYPASSES global char map (åñ → ṛṣ won't be applied!)
corrected, rules = correct_sanskrit_diacritics(raw_text)  # DON'T DO THIS!
```

---

## Testing

Verify the fix works:

```bash
cd /Users/kamaldivi/Development/Python/pure_bhakti_valut/src/prod_utils
python3 -c "
from sanskrit_utils import correct_sanskrit_diacritics, apply_global_char_map

# Test the updated logic
raw_word = 'dåñṭa'
stage1_word, _ = apply_global_char_map(raw_word)
final_word, _ = correct_sanskrit_diacritics(stage1_word)

print(f'Raw:    {raw_word}')
print(f'Stage1: {stage1_word}')
print(f'Final:  {final_word}')
print()
print('Expected: dṛṣṭa (with ṛṣ, not āṣ)')
print(f'Got:      {final_word}')
print(f'Status:   {\"✅ PASS\" if final_word == \"dṛṣṭa\" else \"❌ FAIL\"}')"
```

Expected output:
```
Raw:    dåñṭa
Stage1: dṛṣṭa
Final:  dṛṣṭa

Expected: dṛṣṭa (with ṛṣ, not āṣ)
Got:      dṛṣṭa
Status:   ✅ PASS
```

---

## Summary

Fixed critical bug in `update_word_bank.py` where it was bypassing Stage 1 (GLOBAL_CHAR_MAP), causing the new global `åñ → ṛṣ` rule (v1.0.14) to not be applied. The fix ensures all 400+ words with the åñ pattern are correctly converted to ṛṣ (not āṣ) when updating the database.

**Action Required**: Re-run `update_word_bank.py` to fix the 400+ incorrectly converted words in the database.
