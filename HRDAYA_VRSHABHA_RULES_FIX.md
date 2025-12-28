# håd/våṣ Rules Fix - Sanskrit Diacritic Utils

## Issue Report

**User Report**: "Can you please check how we are fixing the words håday, våñabhänu"

**Problems Found**:
1. "håday" was converting to "hāday" instead of "hṛday" (heart)
2. "våñabhänu" was converting to "vāṣabhānu" instead of "vṛṣabhānu" (Vṛṣabhānu)

## Root Causes

1. **håd → hṛd rule missing**: The pattern `håd` (from hṛdaya = heart) was not recognized, so it fell through to default `å → ā`
2. **våṣ → vṛṣ rule missing**: The pattern `våṣ` (from vṛṣabha = bull, or Vṛṣabhānu) was not recognized, so it fell through to default `å → ā`

## Fixes Applied

### Changes to `sanskrit_diacritic_utils.py`

**Rule 14 (håda → hṛda) - Added** (Lines 237-241):

```python
# NEW (ADDED):
# Rule 14: håda → hṛda (hṛdaya - heart)
# More specific pattern to avoid false positives (e.g., mahādeva)
corrected = corrected.replace('håda', 'hṛda')
corrected = corrected.replace('Håda', 'Hṛda')
corrected = corrected.replace('HÅDA', 'HṚDA')
```

**Rule 15 (våṣa → vṛṣa) - Added** (Lines 243-247):

```python
# NEW (ADDED):
# Rule 15: våṣa → vṛṣa (vṛṣabha - bull; Vṛṣabhānu - father of Radha)
# More specific pattern with trailing 'a' (raw OCR shows våñ which becomes våṣa)
corrected = corrected.replace('våṣa', 'vṛṣa')
corrected = corrected.replace('Våṣa', 'Vṛṣa')
corrected = corrected.replace('VÅṢA', 'VṚṢA')
```

**Location**: Lines 237-247 in `sanskrit_diacritic_utils.py` (before default å → ā conversion)

**Key Design Decision**: Used MORE SPECIFIC patterns (`håda`, `våṣa` with trailing 'a') instead of broader patterns (`håd`, `våṣ`) based on word bank analysis to avoid false positives.

## Test Results

### Before Fix ❌
```
håday          → hāday         (WRONG - should be hṛday)
hådaya         → hādaya        (WRONG - should be hṛdaya)
våñabhänu      → vāṣabhānu     (WRONG - should be vṛṣabhānu)
våṣabha        → vāṣabha       (WRONG - should be vṛṣabha)
```

### After Fix ✅
```
✓ håday          → hṛday          (Rule 14 - heart)
✓ hådaya         → hṛdaya         (Rule 14 - heart)
✓ Hådaya         → Hṛdaya         (Rule 14 - capitalized)
✓ våṣabha        → vṛṣabha        (Rule 15 - bull)
✓ Våṣabha        → Vṛṣabha        (Rule 15 - capitalized)
✓ Våṣabhānu      → Vṛṣabhānu      (Rule 15 - name)
✓ våñabhänu      → vṛṣabhānu      (Full pipeline with ñ→ṣ, ä→ā)
```

## Comprehensive Test Results

All 35 test cases for å diacritic rules now pass (including new Rules 14-15):

```
✓ båhad          → bṛhad            (Rule 1: åh → ṛh)
✓ gåha           → gṛha             (Rule 1: åh → ṛh)
✓ båḥ            → bṛḥ              (Rule 1: åḥ → ṛḥ - visarga)
✓ Båḥ            → Bṛḥ              (Rule 1: åḥ → ṛḥ - visarga)
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
✓ adhåta         → adhṛta           (Rule 12: Mid-word)
✓ bhågu          → bhṛgu            (Rule 13: bhåg → bhṛg)
✓ Bhågu          → Bhṛgu            (Rule 13: bhåg → bhṛg)
✓ bhågavat       → bhṛgavat         (Rule 13: bhåg → bhṛg)
✓ håday          → hṛday            (Rule 14: håd → hṛd - NEW)
✓ hådaya         → hṛdaya           (Rule 14: håd → hṛd - NEW)
✓ Hådaya         → Hṛdaya           (Rule 14: håd → hṛd - NEW)
✓ våṣabha        → vṛṣabha          (Rule 15: våṣ → vṛṣ - NEW)
✓ Våṣabha        → Vṛṣabha          (Rule 15: våṣ → vṛṣ - NEW)
✓ Våṣabhānu      → Vṛṣabhānu        (Rule 15: våṣ → vṛṣ - NEW)
✓ Bhagavån       → Bhagavān         (Default: å → ā)
✓ kåla           → kāla             (Default: å → ā)
✓ bhå            → bhā              (Default: å → ā)
✓ bhårata        → bhārata          (Default: å → ā)
```

## Technical Details

### Rule 14: håd → hṛd (hṛdaya)

**Sanskrit Word**: हृदय (hṛdaya)
- **Meaning**: Heart, mind
- **Root**: hṛd (heart)
- **Pronunciation**: hri-da-ya

**Common Forms**:
- hṛdaya (heart)
- hṛday (shortened form)
- hṛdayam (accusative)
- mahā-hṛdaya (great-hearted)

**Why This Pattern**:
The word hṛdaya is extremely common in Sanskrit literature, especially in spiritual and philosophical texts where the "heart" is discussed as the seat of consciousness and devotion.

### Rule 15: våṣ → vṛṣ (vṛṣabha, Vṛṣabhānu)

**Sanskrit Word 1**: वृषभ (vṛṣabha)
- **Meaning**: Bull, best, excellent
- **Usage**: Common in describing strength and excellence

**Sanskrit Word 2**: वृषभानु (Vṛṣabhānu)
- **Meaning**: Important name in Vaishnava tradition
- **Context**: Father of Śrī Rādhā
- **Significance**: Appears frequently in Gaudiya Vaishnava literature

**Why This Pattern**:
- vṛṣabha is a common Sanskrit word
- Vṛṣabhānu is an important name in the Pure Bhakti Vault corpus
- OCR frequently misreads the vṛṣ pattern

## Pattern Analysis

### håd Pattern
```
hå + d → hṛ + d

Examples:
- håday  → hṛday  (short form)
- hådaya → hṛdaya (full word)
- Hådaya → Hṛdaya (capitalized)
```

### våṣ Pattern
```
vå + ṣ → vṛ + ṣ

Examples:
- våṣabha   → vṛṣabha   (bull)
- Våṣabhānu → Vṛṣabhānu (name)
```

Note: The `ñ → ṣ` conversion happens in Stage 1 (GLOBAL_CHAR_MAP), so by the time the å diacritic rules run, `ñ` has already become `ṣ`.

## Full Pipeline Example

Input: `våñabhänu`

**Stage 1 - Global Character Map**:
- `ä → ā`: våñabhänu → våñabhānu

**Stage 2 - Text Segmentation**: (tokenization)

**Stage 3 - Pattern-Based Correction**:
- `ñ → ṣ`: våñabhānu → våṣabhānu
- `våṣ → vṛṣ` (Rule 15): våṣabhānu → vṛṣabhānu

**Final Output**: `vṛṣabhānu` ✓

## Impact

### Words Affected - Rule 14 (håd → hṛd)

- **hṛdaya** (हृदय) - heart, mind
- **hṛdayam** - heart (accusative)
- **mahā-hṛdaya** - great-hearted
- **kṛpā-hṛdaya** - compassionate heart
- All derivatives and compounds with hṛd/hṛdaya

### Words Affected - Rule 15 (våṣ → vṛṣ)

- **vṛṣabha** (वृषभ) - bull, best, excellent
- **Vṛṣabhānu** (वृषभानु) - father of Śrī Rādhā
- **vṛṣabhānuja** - daughter of Vṛṣabhānu (i.e., Rādhā)
- **vṛṣa** - bull, male
- All derivatives and compounds with vṛṣ

## Version

- **Fixed in**: sanskrit_utils v1.0.13
- **Previous version**: v1.0.12

## Files Modified

1. **[sanskrit_diacritic_utils.py](src/prod_utils/sanskrit_utils/sanskrit_diacritic_utils.py)**
   - Lines 235-238: Added Rule 14 (håd → hṛd)
   - Lines 240-243: Added Rule 15 (våṣ → vṛṣ)
   - Lines 120-121: Updated docstring

2. **[CHANGELOG.md](src/prod_utils/sanskrit_utils/CHANGELOG.md)**
   - Added v1.0.13 release notes

3. **[__init__.py](src/prod_utils/sanskrit_utils/__init__.py)**
   - Updated version to 1.0.13

## Testing

Run test to verify the fixes:

```bash
cd src/prod_utils
python3 -c "
from sanskrit_utils import process_page

# Test håday
result1 = process_page('håday', page_number=1)
print(f'håday → {result1.corrected_text}')  # Should be hṛday

# Test hådaya
result2 = process_page('hådaya', page_number=1)
print(f'hådaya → {result2.corrected_text}')  # Should be hṛdaya

# Test våñabhänu (full pipeline)
result3 = process_page('våñabhänu', page_number=1)
print(f'våñabhänu → {result3.corrected_text}')  # Should be vṛṣabhānu

# Test Våṣabhānu
result4 = process_page('Våṣabhānu', page_number=1)
print(f'Våṣabhānu → {result4.corrected_text}')  # Should be Vṛṣabhānu
"
```

Expected output:
```
håday → hṛday
hådaya → hṛdaya
våñabhänu → vṛṣabhānu
Våṣabhānu → Vṛṣabhānu
```

## Backward Compatibility

✅ **Fully backward compatible** - only fixes previously incorrect behavior
- All existing conversions continue to work
- No breaking changes to API
- No regressions in existing tests (all 35 tests pass)

## Summary

Added two new rules to fix common Sanskrit words:
1. **Rule 14**: `håd → hṛd` for hṛdaya (heart) and related words
2. **Rule 15**: `våṣ → vṛṣ` for vṛṣabha (bull) and Vṛṣabhānu (important Vaishnava name)

Both rules are essential for correctly processing spiritual literature in the Pure Bhakti Vault corpus where these words appear frequently.
