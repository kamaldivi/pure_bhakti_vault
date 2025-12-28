# Full Page Default Behavior Change - Transliteration Processor

## Change Summary

Changed the default behavior of `transliteration_processor.py` from **excluding** headers/footers to **including** them (full page capture).

## Rationale

Many books were experiencing header and footer truncation issues when using the automatic header/footer exclusion based on `book.header_height` and `book.footer_height` values in the database. To avoid data loss, the default is now to capture the full page content.

## Changes Made

### File: `transliteration_processor.py` (v2.1.0)

**1. Changed default `full_page` parameter** (Line 79):
```python
# OLD:
full_page: bool = False

# NEW:
full_page: bool = True
```

**2. Updated command-line argument default** (Line 881):
```python
# OLD:
default='no',

# NEW:
default='yes',
```

**3. Updated documentation**:
- Module docstring (lines 20-36)
- Argument parser help text (lines 848-869)
- `__init__` docstring (lines 87-88)

## Behavior Changes

### Before (v2.0.0)
```bash
# Default behavior: Exclude header/footer
python transliteration_processor.py

# To include header/footer, explicit flag needed
python transliteration_processor.py --full-page yes
```

### After (v2.1.0)
```bash
# Default behavior: Include header/footer (FULL PAGE)
python transliteration_processor.py

# To exclude header/footer, explicit flag needed
python transliteration_processor.py --full-page no
```

## Impact

### Positive
- ✅ No data loss from header/footer truncation
- ✅ More conservative approach - captures all content
- ✅ Users can still exclude headers/footers for specific books using `--full-page no`

### To Consider
- Headers and footers will now be included in `page_content` by default
- Users will need to use `--full-page no` for books where header/footer margins are correctly configured
- May increase storage slightly due to extra content

## Migration Guide

### For Existing Scripts

If you have scripts that rely on the old default behavior (excluding headers/footers), you need to add `--full-page no`:

```bash
# OLD (worked in v2.0.0):
python transliteration_processor.py --book-id 3

# NEW (to get same behavior in v2.1.0):
python transliteration_processor.py --book-id 3 --full-page no
```

### For New Processing

The new default is recommended for most cases. Only use `--full-page no` if you're certain the header/footer margins in the database are correctly configured for that book.

## Testing

Test the new default behavior:

```bash
# Full page (new default)
python transliteration_processor.py --book-id 3

# Body only (old default, now requires explicit flag)
python transliteration_processor.py --book-id 3 --full-page no
```

## Version History

- **v2.0.0**: Default `--full-page no` (excludes header/footer)
- **v2.1.0**: Default `--full-page yes` (includes header/footer) ← **CURRENT**

## Related Files

- [transliteration_processor.py](src/prod_utils/transliteration_processor.py)
- [HEADER_FOOTER_EXCLUSION_FEATURE.md](HEADER_FOOTER_EXCLUSION_FEATURE.md) (original feature documentation)

## Command Reference

```bash
# Process all books with full page (default)
python transliteration_processor.py

# Process specific book with full page (default)
python transliteration_processor.py --book-id 3

# Process specific book, exclude header/footer
python transliteration_processor.py --book-id 3 --full-page no

# Process with auto-column detection (default)
python transliteration_processor.py --book-id 5 --sort auto

# Process with natural reading order
python transliteration_processor.py --book-id 5 --sort true
```

## Database Considerations

The `book` table's `header_height` and `footer_height` columns are now **only used when `--full-page no` is specified**. In the default mode (`--full-page yes`), these values are ignored and the entire page is captured.

This allows you to:
1. Process all books with full page capture (safe, no data loss)
2. Selectively reprocess specific books with `--full-page no` after verifying header/footer margins
3. Update header/footer margins in the database for problematic books
4. Reprocess those books with `--full-page no` to get clean body content

## Recommendation

**Best Practice Workflow**:
1. First pass: Process all books with default settings (full page)
2. Review content to identify books with header/footer issues
3. Update `header_height` and `footer_height` in database for those books
4. Reprocess affected books with `--full-page no --book-id <id>`

This ensures no content is lost initially, while still allowing fine-tuned control for books that need it.
