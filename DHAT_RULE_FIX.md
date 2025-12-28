# dhåt Rule Fix - Sanskrit Diacritic Utils

## Issue Report
**Problem**: Words like "dhåtrāṣṭra" were being incorrectly converted to "dhātrāṣṭra" instead of "dhṛtarāṣṭra"

**Root Cause**: The dhåt → dhṛt rule had two bugs:
1. Regex pattern `([^i])dhåt` didn't match word-initial "dhåt" (no character before it)
2. Missing special case for "dhåtr" → "dhṛtar" pattern (sandhi with lost vowel)

## Fix Applied

### Changes to `sanskrit_diacritic_utils.py`

**Rule 12 (dhåt → dhṛt) - Fixed**:

```python
# OLD (BROKEN):
corrected = re.sub(r'([^i])dhåt', r'\1dhṛt', corrected)
corrected = re.sub(r'([^i])Dhåt', r'\1Dhṛt', corrected)
corrected = re.sub(r'DHÅT', 'DHṚT', corrected)

# NEW (FIXED):
# Special case: dhåtr → dhṛtar (Dhṛtarāṣṭra - compound with lost vowel)
corrected = re.sub(r'dhåtr', 'dhṛtar', corrected)
corrected = re.sub(r'Dhåtr', 'Dhṛtar', corrected)
corrected = re.sub(r'DHÅTR', 'DHṚTAR', corrected)
# Convert word-initial dhåt
corrected = re.sub(r'^dhåt', 'dhṛt', corrected)
corrected = re.sub(r'^Dhåt', 'Dhṛt', corrected)
# Convert mid-word dhåt if NOT preceded by 'i'
corrected = re.sub(r'([^i])dhåt', r'\1dhṛt', corrected)
corrected = re.sub(r'([^i])Dhåt', r'\1Dhṛt', corrected)
# Convert uppercase
corrected = re.sub(r'^DHÅT', 'DHṚT', corrected)
corrected = re.sub(r'([^I])DHÅT', r'\1DHṚT', corrected)
```

**Rule 10 (kåt → kṛt) - Also Fixed**:
While testing, discovered case preservation bug in kåt rule:

```python
# OLD (BROKEN):
corrected = re.sub(r'^[Kk]åt([aeiumoāīū])', r'Kṛt\1', corrected)

# NEW (FIXED):
corrected = re.sub(r'^kåt([aeiumoāīū])', r'kṛt\1', corrected)
corrected = re.sub(r'^Kåt([aeiumoāīū])', r'Kṛt\1', corrected)
```

## Test Results

### Before Fix ❌
```
dhåtrāṣṭra → dhātrāṣṭra  (WRONG - should be dhṛtarāṣṭra)
dhåta      → dhāta       (WRONG - should be dhṛta)
kåta       → Kṛta        (WRONG - incorrect capitalization)
```

### After Fix ✅
```
✓ dhåtrāṣṭra  → dhṛtarāṣṭra  (Dhṛtarāṣṭra - character name)
✓ Dhåtrāṣṭra  → Dhṛtarāṣṭra  (Capitalized)
✓ dhåta       → dhṛta        (dhṛta - held/worn)
✓ vidhåtā     → vidhātā      (Exception preserved)
✓ adhåta      → adhṛta       (Mid-word conversion)
✓ kåta        → kṛta         (Case preserved)
✓ Kåta        → Kṛta         (Case preserved)
```

## Comprehensive Test Results

All 22 test cases for å diacritic rules now pass:

```
✓ båhad        → bṛhad          (Rule 1: åh → ṛh)
✓ gåha         → gṛha           (Rule 1: åh → ṛh)
✓ amåta        → amṛta          (Rule 2: måt → mṛt)
✓ Amåta        → Amṛta          (Rule 2: måt → mṛt)
✓ småti        → smṛti          (Rule 3: småt → smṛt)
✓ gåhīta       → gṛhīta         (Rule 4: gåhī → gṛhī)
✓ tåpta        → tṛpta          (Rule 5: tåpt → tṛpt)
✓ tåṇa         → tṛṇa           (Rule 6: tåṇ → tṛṇ)
✓ dåḍha        → dṛḍha          (Rule 7: dåḍh → dṛḍh)
✓ dåśya        → dṛśya          (Rule 8: dåśy → dṛśy)
✓ prakåti      → prakṛti        (Rule 9: prakåt → prakṛt)
✓ kåta         → kṛta           (Rule 10: kåt → kṛt - FIXED)
✓ Kåta         → Kṛta           (Rule 10: kåt → kṛt - FIXED)
✓ vånda        → vṛnda          (Rule 11: vånd → vṛnd)
✓ Våndāvana    → Vṛndāvana      (Rule 11: vånd → vṛnd)
✓ dhåta        → dhṛta          (Rule 12: dhåt → dhṛt - FIXED)
✓ dhåtrāṣṭra   → dhṛtarāṣṭra    (Rule 12: dhåtr → dhṛtar - FIXED)
✓ Dhåtrāṣṭra   → Dhṛtarāṣṭra    (Rule 12: dhåtr → dhṛtar - FIXED)
✓ vidhåtā      → vidhātā        (Rule 12: Exception preserved)
✓ adhåta       → adhṛta         (Rule 12: Mid-word conversion)
✓ Bhagavån     → Bhagavān       (Default: å → ā)
✓ kåla         → kāla           (Default: å → ā)
```

## Technical Details

### Bug 1: Word-Initial Pattern Not Matching

**Problem**:
The regex `([^i])dhåt` requires a character BEFORE "dhåt" that is not 'i'.
At word start, there's no character before "dhåt", so pattern doesn't match.

**Example**:
- Input: "dhåtrāṣṭra" (starts with "dhåt")
- Pattern: `([^i])dhåt` → NO MATCH (no char before dhåt)
- Result: Falls through to default å → ā

**Solution**:
Add separate pattern for word-initial: `^dhåt`

### Bug 2: Missing Sandhi Pattern

**Problem**:
"Dhṛtarāṣṭra" is a compound: dhṛta + rāṣṭra
In sandhi, the final 'a' of "dhṛta" is often dropped: dhṛt + rāṣṭra
OCR sees: "dhåtrāṣṭra" (with å instead of ṛ)

**Example**:
- Input: "dhåtrāṣṭra"
- Pattern needed: "dhåtr" → "dhṛtar" (restore the lost 'a')
- Old behavior: "dhåtr" → "dhṛtr" (missing 'a')
- Correct: "dhåtrāṣṭra" → "dhṛtarāṣṭra"

**Solution**:
Add special case BEFORE general dhåt rule: `dhåtr → dhṛtar`

### Bug 3: Case Preservation Issue

**Problem**:
Pattern `r'^[Kk]åt([aeiumoāīū])'` with replacement `r'Kṛt\1'` always capitalizes K

**Example**:
- Input: "kåta" (lowercase)
- Pattern: `[Kk]åt` → MATCHES
- Replacement: `Kṛt` → ALWAYS UPPERCASE
- Result: "Kṛta" (incorrect capitalization)

**Solution**:
Separate patterns for lowercase and uppercase:
- `^kåt` → `kṛt` (lowercase)
- `^Kåt` → `Kṛt` (uppercase)

## Impact

This fix affects:
- **Dhṛtarāṣṭra** - Major character in Mahābhārata
- **dhṛta** - Common Sanskrit root (held, worn, sustained)
- All compounds with dhṛt/dhṛta
- Any word starting with "kåt" pattern

## Version

Fixed in: **sanskrit_utils v1.0.11** (unreleased)
Previous version: v1.0.10

## Files Modified

- `src/prod_utils/sanskrit_utils/sanskrit_diacritic_utils.py`
  - Lines 207-221: Rule 12 (dhåt) completely rewritten
  - Lines 194-200: Rule 10 (kåt) case preservation fixed

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
print(correct_a_diacritic('dhåtrāṣṭra'))  # Should output: dhṛtarāṣṭra
print(correct_a_diacritic('dhåta'))        # Should output: dhṛta
print(correct_a_diacritic('vidhåtā'))      # Should output: vidhātā
"
```

Expected output:
```
dhṛtarāṣṭra
dhṛta
vidhātā
```
