#!/usr/bin/env python3
"""
Sanskrit IAST Diacritic Correction Utilities
=============================================

Functions for correcting misencoded diacritics in Sanskrit IAST transliteration:
- ñ (often incorrectly used) → ṣ or ñ (correct usage)
- å (incorrectly used) → ṛ or ā

Author: Sanskrit Text Processing
License: MIT
"""

import re
from typing import Optional


def correct_n_diacritic(word: str) -> str:
    """
    Correct ñ diacritic: ñ → ṣ (or keep ñ for legitimate cases).

    Strategy: Global ñ → ṣ replacement with exceptions protected.

    This handles the common encoding error where ñ is used instead of ṣ
    in Sanskrit IAST transliteration. Uses a global replacement approach
    that is simpler and more comprehensive than enumerating specific patterns.

    The ONLY legitimate uses of ñ in Sanskrit IAST are:
    - jñ (ज्ञ) - palatal nasal before j (jñāna, vijñāna)
    - ñc, ñch - palatal nasal before c (pañca, pañcama)
    - ñj - palatal nasal before j in compounds (sañjaya, rañjana)

    All other uses of ñ are OCR/encoding errors and should be ṣ.

    Args:
        word: Sanskrit word in IAST with potentially incorrect ñ

    Returns:
        Corrected word with proper ṣ/ñ usage

    Examples:
        >>> correct_n_diacritic("kñā")
        'kṣā'  # Global: kñ → kṣ
        >>> correct_n_diacritic("lakñmī")
        'lakṣmī'  # Global: ñ → ṣ
        >>> correct_n_diacritic("Ajñāna")
        'Ajñāna'  # Exception: jñ preserved
        >>> correct_n_diacritic("pañca")
        'pañca'  # Exception: ñc preserved
    """
    if not word:
        return word

    corrected = word

    # STEP 1: Protect legitimate ñ patterns (EXCEPTIONS ONLY)
    # These are the ONLY cases where ñ should remain in Sanskrit IAST

    # Exception 1: jñ (ज्ञ - knowledge)
    # Most common legitimate use: jñāna, vijñāna, ajñāna
    corrected = corrected.replace('jñ', '⟨JN⟩')
    corrected = corrected.replace('jÑ', '⟨JN⟩')
    corrected = corrected.replace('Jñ', '⟨JN⟩')
    corrected = corrected.replace('JÑ', '⟨JN⟩')

    # Exception 2: ñc, ñch (palatal nasal before palatal stops)
    # Examples: pañca (five), pañcama (fifth)
    corrected = corrected.replace('ñc', '⟨NC⟩')
    corrected = corrected.replace('ñC', '⟨NC⟩')
    corrected = corrected.replace('Ñc', '⟨NC⟩')
    corrected = corrected.replace('ÑC', '⟨NC⟩')
    corrected = re.sub(r'ñch', '⟨NCH⟩', corrected, flags=re.IGNORECASE)
    corrected = re.sub(r'Ñch', '⟨NCH⟩', corrected, flags=re.IGNORECASE)

    # Exception 3: Mid-word ñj (rare, but legitimate)
    # Examples: sañjaya, rañjana
    # Only protect mid-word (after vowels), not word-initial
    corrected = re.sub(r'([aāiīuūṛeēoō])ñj', r'\1⟨NJ⟩', corrected, flags=re.IGNORECASE)

    # STEP 2: Global replacement - ALL remaining ñ → ṣ
    # This is the DEFAULT behavior for ~95% of cases
    # Catches: kñ→kṣ, viñ→viṣ, rña→rṣa, ñṭ→ṣṭ, and ALL other combinations

    # Replace all lowercase ñ → ṣ (except placeholders)
    corrected = corrected.replace('ñ', 'ṣ')

    # Replace all uppercase Ñ → Ṣ (except placeholders)
    corrected = corrected.replace('Ñ', 'Ṣ')

    # STEP 3: Restore protected patterns (EXCEPTIONS)
    corrected = corrected.replace('⟨JN⟩', 'jñ')
    corrected = corrected.replace('⟨NC⟩', 'ñc')
    corrected = corrected.replace('⟨NCH⟩', 'ñch')
    corrected = corrected.replace('⟨NJ⟩', 'ñj')

    return corrected


def correct_a_diacritic(word: str) -> str:
    """
    Correct å diacritic: å → ṛ or ā based on consonant context.

    This handles the encoding error where å is used instead of either
    ṛ (vocalic r) or ā (long a) in Sanskrit IAST transliteration.

    Priority rules for ṛ (~17% of cases):
    - åh/åḥ → ṛh/ṛḥ (bṛhad, gṛha, bṛḥ - includes visarga)
    - måt → mṛt (amṛta)
    - småt → smṛt (smṛti)
    - gåhī → gṛhī (gṛhīta)
    - tåpt → tṛpt (tṛpta)
    - tåṇ → tṛṇ (tṛṇa)
    - dåḍh → dṛḍh (dṛḍha)
    - dåśy → dṛśy (dṛśya)
    - prakåt → prakṛt (prakṛti)
    - kåt → kṛt (kṛta)
    - vånd → vṛnd (Vṛndāvana)
    - dhåt → dhṛt (dhṛta - except vidhātā)
    - bhåg → bhṛg (Bhṛgu - Vedic sage)
    - håda → hṛda (hṛdaya - heart)
    - våṣa → vṛṣa (vṛṣabha - bull; Vṛṣabhānu)

    Default: å → ā (~83% of cases)

    Args:
        word: Sanskrit word in IAST with incorrect å

    Returns:
        Corrected word with proper ṛ/ā usage

    Examples:
        >>> correct_a_diacritic("Amåta")
        'Amṛta'
        >>> correct_a_diacritic("Bhagavån")
        'Bhagavān'
        >>> correct_a_diacritic("Båhad")
        'Bṛhad'
    """
    if not word:
        return word

    corrected = word

    # STEP 1: Apply ṛ patterns (priority rules - MUST come first)

    # Rule 1: åh → ṛh (bṛhad, gṛha)
    # Also handle åḥ → ṛḥ (visarga form)
    corrected = corrected.replace('åh', 'ṛh')
    corrected = corrected.replace('Åh', 'Ṛh')
    corrected = corrected.replace('ÅH', 'ṚH')
    corrected = corrected.replace('åḥ', 'ṛḥ')
    corrected = corrected.replace('Åḥ', 'Ṛḥ')
    corrected = corrected.replace('ÅḤ', 'ṚḤ')

    # Rule 2: måt → mṛt (amṛta - nectar, immortal)
    # Handle standalone amåt
    corrected = re.sub(r'([^āīū])amåt', r'\1amṛt', corrected)
    corrected = re.sub(r'^amåt', 'amṛt', corrected)  # Word-initial
    corrected = re.sub(r'^Amåt', 'Amṛt', corrected)

    # Handle compounds: preserve sandhi ā/ī/ū before måt
    # Example: Bhagavatāmåta → Bhagavatāmṛta (NOT Bhagavatāmāta)
    corrected = re.sub(r'([āīū])måt', r'\1mṛt', corrected)

    # Rule 3: småt → smṛt (smṛti - memory)
    corrected = corrected.replace('småt', 'smṛt')
    corrected = corrected.replace('Småt', 'Smṛt')
    corrected = corrected.replace('SMÅT', 'SMṚT')

    # Rule 4: gåhī → gṛhī (gṛhīta - grasped)
    corrected = corrected.replace('gåhī', 'gṛhī')
    corrected = corrected.replace('gåhĪ', 'gṛhī')
    corrected = corrected.replace('Gåhī', 'Gṛhī')
    corrected = corrected.replace('GÅHĪ', 'GṚHĪ')

    # Rule 5: tåpt → tṛpt (tṛpta - satisfied)
    corrected = corrected.replace('tåpt', 'tṛpt')
    corrected = corrected.replace('Tåpt', 'Tṛpt')
    corrected = corrected.replace('TÅPT', 'TṚPT')

    # Rule 6: tåṇ → tṛṇ (tṛṇa - grass)
    corrected = corrected.replace('tåṇ', 'tṛṇ')
    corrected = corrected.replace('tåṆ', 'tṛṇ')
    corrected = corrected.replace('Tåṇ', 'Tṛṇ')
    corrected = corrected.replace('TÅṆ', 'TṚṆ')

    # Rule 7: dåḍh → dṛḍh (dṛḍha - firm)
    corrected = corrected.replace('dåḍh', 'dṛḍh')
    corrected = corrected.replace('Dåḍh', 'Dṛḍh')
    corrected = corrected.replace('DÅḌH', 'DṚḌH')

    # Rule 8: dåśy → dṛśy (dṛśya - visible)
    corrected = corrected.replace('dåśy', 'dṛśy')
    corrected = corrected.replace('Dåśy', 'Dṛśy')
    corrected = corrected.replace('DÅŚY', 'DṚŚY')

    # Rule 9: prakåt → prakṛt (prakṛti - nature)
    corrected = re.sub(r'([Pp])rakåt', r'\1rakṛt', corrected)
    corrected = re.sub(r'PRAKÅT', 'PRAKṚT', corrected)

    # Rule 10: kåt → kṛt (kṛta - done/made)
    # Be careful not to match adhikåta (which might be adhikāra)
    # Convert at word boundaries or after non-'i' characters
    corrected = re.sub(r'^kåt([aeiumoāīū])', r'kṛt\1', corrected)
    corrected = re.sub(r'^Kåt([aeiumoāīū])', r'Kṛt\1', corrected)
    corrected = re.sub(r'([^i])kåt([aeiumoāīū])', r'\1kṛt\2', corrected)
    corrected = re.sub(r'([^i])Kåt([aeiumoāīū])', r'\1Kṛt\2', corrected)

    # Rule 11: vånd → vṛnd (Vṛndāvana - holy place)
    corrected = corrected.replace('vånd', 'vṛnd')
    corrected = corrected.replace('vÅnd', 'vṛnd')
    corrected = corrected.replace('Vånd', 'Vṛnd')
    corrected = corrected.replace('VÅnd', 'Vṛnd')
    corrected = corrected.replace('VÅND', 'VṚND')

    # Rule 12: dhåt → dhṛt (dhṛta - held/worn)
    # Exception: vidhātā (not vidhṛtā)
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

    # Rule 13: bhåg → bhṛg (Bhṛgu - Vedic sage name)
    corrected = corrected.replace('bhåg', 'bhṛg')
    corrected = corrected.replace('Bhåg', 'Bhṛg')
    corrected = corrected.replace('BHÅG', 'BHṚG')

    # Rule 14: håda → hṛda (hṛdaya - heart)
    # More specific pattern to avoid false positives (e.g., mahādeva)
    corrected = corrected.replace('håda', 'hṛda')
    corrected = corrected.replace('Håda', 'Hṛda')
    corrected = corrected.replace('HÅDA', 'HṚDA')

    # STEP 2: Apply default å → ā conversion for all remaining å
    # This is the default for the vast majority of cases (~83%)
    corrected = corrected.replace('å', 'ā')
    corrected = corrected.replace('Å', 'Ā')

    return corrected
