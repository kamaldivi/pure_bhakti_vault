# Header/Footer Exclusion Feature - Summary

## Feature Added

The PDF processor now **excludes header and footer regions** from content extraction before applying transliteration fixes.

## Implementation

### Database Fields Used

The processor reads header/footer settings from the `book` table:
- **`header_height`**: Height of header region in PDF points (from top of page)
- **`footer_height`**: Y-coordinate where footer starts (from top of page)

These fields are already populated in your database (e.g., Book ID 1 has `header_height=50.40pt`, `footer_height=610.17pt`).

### Extraction Logic

**File**: `pdf_content_transliteration_processor.py`

#### 1. Get Book Metadata (lines 370-389)
```python
book_info = self.db.get_book_by_id(book_id)
header_height = book_info.get('header_height', 0.0)
footer_height = book_info.get('footer_height', None)
```

#### 2. Extract Content with Clipping (lines 207-280)
```python
def extract_page_content(pdf_path, page_number, header_height, footer_height):
    # Calculate content region
    content_y0 = page_rect.y0 + header_height  # Skip header
    content_y1 = footer_height                  # Stop before footer
    
    # Create clipping rectangle
    content_rect = fitz.Rect(x0, content_y0, x1, content_y1)
    
    # Extract only from content area
    text = page.get_text("text", clip=content_rect)
```

## Example Results

**Book**: Acarya Kesari (Book ID 1)  
**Page**: 18  
**Settings**: header_height=50.40pt, footer_height=610.17pt

### Before (Full Page)
```
x v i                              ← Header (page number)
Thirteen years ago, in 1985...     ← Content starts
```
3,421 characters extracted

### After (Filtered)
```
Thirteen years ago, in 1985...     ← Content only
```
3,415 characters extracted  
**6 characters removed** (0.2%) - header excluded

## Benefits

1. **Cleaner Content**: Removes page numbers, running headers/footers
2. **Better Quality**: Transliteration fixes apply only to actual content
3. **No False Corrections**: Page numbers won't be incorrectly "fixed"
4. **Automatic**: Uses existing book metadata - no manual configuration

## Configuration

### Books with Header/Footer Settings
Books that have `header_height` and/or `footer_height` configured in the database will automatically have headers/footers excluded.

### Books Without Settings
Books without header/footer settings will process the entire page (backwards compatible).

## Logging

The processor logs header/footer usage:

```
Book 1: Using header_height=50.4pt, footer_height=610.17pt for content extraction
```

Or if not configured:
```
Book 1: No header/footer settings - extracting full pages
```

## Technical Details

### Coordinate System

PyMuPDF uses PDF coordinate system:
- **Origin**: Bottom-left corner
- **Y-axis**: Goes upward (bottom=0, top=page_height)
- **header_height**: Distance from top (e.g., 50pt = exclude first 50pt from top)
- **footer_height**: Y-coordinate from bottom where footer starts

### Clipping Rectangle

```python
# Page dimensions
page_rect = fitz.Rect(0, 0, width, height)

# Content area (excluding header/footer)
content_rect = fitz.Rect(
    0,                    # Left edge
    header_height,        # Start below header
    width,                # Right edge
    footer_height         # End before footer
)
```

## Fallback Behavior

If invalid header/footer values create an impossible content area:
- Logs a warning
- Falls back to extracting the full page
- Processing continues without error

Example warning:
```
Invalid content area for page 20: header=50.4, footer=40.0, page_height=792.0
```

## Testing

Tested with Book ID 1:
- ✅ Header/footer metadata retrieved correctly
- ✅ Content extraction excludes header region
- ✅ Page numbers removed from extracted text
- ✅ Main content preserved
- ✅ Transliteration fixes applied to content only
- ✅ Fallback works for invalid settings

## Integration with Existing Features

Works seamlessly with:
- ✅ Uppercase diacritic fix (v1.0.2)
- ✅ Missing page INSERT fix
- ✅ Resume capability
- ✅ All page processing

## Version

**Added in**: PDF Content Transliteration Processor v1.2  
**Date**: 2024-12-25

## SQL Query to Check Settings

```sql
-- See which books have header/footer configured
SELECT 
    book_id,
    pdf_name,
    header_height,
    footer_height,
    CASE 
        WHEN header_height IS NOT NULL OR footer_height IS NOT NULL 
        THEN 'Configured' 
        ELSE 'Full Page' 
    END as extraction_mode
FROM book
WHERE book_type = 'english-gurudev'
ORDER BY book_id;
```

## Impact

**Before**: Header/footer content included in ai_page_content  
**After**: Only main content included in ai_page_content

This results in:
- Cleaner database content
- No page numbers in searchable text
- No running headers polluting content
- Better search/retrieval results
- More accurate transliteration (fixes only apply to actual content)

---

**Note**: This feature uses the same header/footer exclusion logic as the existing `page_content_extractor.py` utility, ensuring consistency across the system.
