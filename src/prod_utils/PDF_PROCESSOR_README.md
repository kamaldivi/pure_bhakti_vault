# PDF Content Transliteration Processor

Automated utility to extract content from PDF files, apply Sanskrit IAST transliteration fixes, and store corrected content in the database.

## Overview

This utility processes books of type `'english-gurudev'` from the database, extracts raw content from PDF pages using PyMuPDF, applies Sanskrit transliteration fixes, and stores the corrected content in the `content.ai_page_content` column.

## Features

- **Automatic book discovery**: Reads books from database (book_type = 'english-gurudev')
- **Resume capability**: Picks up from last unprocessed page automatically
- **Header/footer exclusion**: Configurable header/footer removal using book metadata
- **Transliteration fixes**: Applies Sanskrit IAST corrections using `sanskrit_utils`
- **Database integration**: Upserts corrected content to `content.ai_page_content`
- **Error handling**: Stops on page failure and logs failed pages
- **Comprehensive logging**: Console logging with detailed progress information

## Requirements

### Python Packages

```bash
pip install PyMuPDF psycopg2-binary python-dotenv
```

### Environment Variables

The following must be configured in `.env`:

```bash
# Database connection
DATABASE_URL=postgresql://user:password@localhost:5432/pure_bhakti_vault
# OR individual parameters
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pure_bhakti_vault
DB_USER=pbbdbuser
DB_PASSWORD=your_password
```

### PDF Files

PDF files must be located in `/opt/pbb_static_content/pbb_pdf_files/` (configurable via command line)

## Database Schema

### Book Table

The processor queries books with:
```sql
SELECT book_id, pdf_name
FROM book
WHERE book_type = 'english-gurudev'
ORDER BY book_id
```

### Content Table

Structure:
- `content_id` (PK, auto-increment)
- `book_id` (FK to book, part of unique constraint)
- `page_number` (part of unique constraint)
- `page_content` (existing raw content)
- `ai_page_content` (corrected content - populated by this processor)
- `created_at`, `updated_at` (timestamps)

Unique constraint: `(book_id, page_number)`

## Usage

### 1. Test the Setup

Before running the full processor, verify everything is configured correctly:

```bash
python src/prod_utils/test_pdf_processor.py
```

This will test:
- Database connectivity
- Book retrieval from database
- PDF file access
- Single page content extraction
- Transliteration fix application
- Database operations

### 2. Run the Processor

To process all books:

```bash
python src/prod_utils/pdf_content_transliteration_processor.py
```

To use a different PDF folder:

```bash
python src/prod_utils/pdf_content_transliteration_processor.py /path/to/pdf/folder/
```

## How It Works

### Processing Flow

1. **Initialize**: Connect to database, verify PDF folder exists
2. **Get Books**: Query books with `book_type = 'english-gurudev'`, ordered by book_id
3. **For Each Book**:
   - Get last processed page (max page_number where ai_page_content IS NOT NULL)
   - Get pages needing processing (where ai_page_content IS NULL)
   - Skip book if all pages already processed
4. **For Each Page**:
   - Extract raw content using PyMuPDF (1-based page numbering)
   - Exclude header/footer regions if configured (using book.header_height, book.footer_height)
   - Apply transliteration fixes using `sanskrit_utils.process_page()`
   - Upsert corrected content to `content.ai_page_content`
   - Log statistics (words corrected, processing time, confidence)
   - **STOP on failure** (as per requirements)
5. **Complete**: Log final summary

### Resume Capability

The processor automatically resumes from the last processed page:

- Checks for last page with `ai_page_content IS NOT NULL` for each book
- Starts processing from next page
- If interrupted, simply rerun the script - it will continue where it left off

### Error Handling

Following the requirements:
- **Page extraction failure**: Logs error and STOPS processing
- **Database upsert failure**: Logs error and STOPS processing
- **Any exception**: Logs error and STOPS processing

Failed pages are logged with details for manual review.

## Logging

Console logging format:
```
2025-12-25 12:00:00 - processor_name - LEVEL - message
```

### Log Levels

- **INFO**: Normal operations (book start, page progress, completion)
- **ERROR**: Failures (missing files, extraction errors, database errors)
- **DEBUG**: Detailed operations (disabled by default)

### Sample Output

```
================================================================================
Processing Book ID 1: Acarya_Kesari_2nd_ed_2013.pdf
================================================================================
Book 1: Found 367 pages to process (from page 17 to 405)
  Processing page 17/405...
  ✓ Page 17 processed: 3 words corrected, 2.04ms
  Processing page 18/405...
  ✓ Page 18 processed: 5 words corrected, 1.87ms
  ...
--------------------------------------------------------------------------------
Book 1 (Acarya_Kesari_2nd_ed_2013.pdf): Processed 367 pages, Successful: 367, Failed: 0
✓ Book 1 completed successfully!
================================================================================
```

## Transliteration Fixes Applied

The utility uses the `sanskrit_utils` package which applies:

- **Global character map**: Simple OCR error corrections (ä→ā, ß→ṣ, etc.)
- **ñ corrections**: ñ → ṣ (or preserved for legitimate jñ, ñc, ñj cases)
- **å corrections**: å → ṛ or ā based on context
- **Combined patterns**: åñṇ → ṛṣṇ (e.g., kåñṇa → kṛṣṇa)
- **Case preservation**: Maintains original case (lowercase, UPPERCASE, Title Case, mixed)

Statistics tracked per page:
- Total words processed
- Words corrected
- Processing time (milliseconds)
- Confidence scores

## Database Operations

### Upsert Logic

The processor uses PostgreSQL's `ON CONFLICT` for efficient upserts:

```sql
INSERT INTO content (book_id, page_number, ai_page_content, created_at, updated_at)
VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (book_id, page_number)
DO UPDATE SET
    ai_page_content = EXCLUDED.ai_page_content,
    updated_at = CURRENT_TIMESTAMP
```

This ensures:
- New rows are inserted if they don't exist
- Existing rows are updated with new content
- No duplicate key errors
- Atomic operations

### Query Performance

The processor uses indexed queries:
- `(book_id, page_number)` - unique constraint provides index
- `WHERE ai_page_content IS NULL` - finds unprocessed pages efficiently

## Monitoring Progress

### Check Book Progress

```sql
-- See which books have been processed
SELECT
    b.book_id,
    b.pdf_name,
    COUNT(c.page_number) as total_pages,
    COUNT(c.ai_page_content) as processed_pages,
    COUNT(c.page_number) - COUNT(c.ai_page_content) as remaining_pages
FROM book b
LEFT JOIN content c ON b.book_id = c.book_id
WHERE b.book_type = 'english-gurudev'
GROUP BY b.book_id, b.pdf_name
ORDER BY b.book_id;
```

### Check Last Processed Page

```sql
-- See last processed page for a specific book
SELECT MAX(page_number) as last_page
FROM content
WHERE book_id = 1
AND ai_page_content IS NOT NULL;
```

### Check Processing Quality

```sql
-- Sample corrected content
SELECT book_id, page_number,
       LEFT(ai_page_content, 200) as sample_content
FROM content
WHERE book_id = 1
AND ai_page_content IS NOT NULL
LIMIT 5;
```

## Troubleshooting

### Issue: "PDF file not found"

**Solution**:
- Verify PDF files are in `/opt/pbb_static_content/pbb_pdf_files/`
- Check pdf_name in database matches actual filename (case-sensitive)
- Use command line argument to specify different folder

### Issue: "No books found to process"

**Solution**:
- Verify books exist with `book_type = 'english-gurudev'`
- Check database connection is working
- Run test script to diagnose

### Issue: "Failed to connect to database"

**Solution**:
- Check `.env` file has correct DATABASE_URL or DB_* parameters
- Verify PostgreSQL is running
- Test connection: `psql postgresql://user:password@localhost:5432/dbname`

### Issue: Page extraction returns empty content

**Solution**:
- PDF might be image-based (no extractable text)
- Page might be blank
- Check PDF manually to verify content exists

### Issue: Processing stops unexpectedly

**Solution**:
- Check logs for the failed page
- Manually inspect the PDF at that page
- Fix any database or filesystem issues
- Rerun - processor will resume from last successful page

## Performance

Typical performance:
- **Page extraction**: ~100ms per page (varies with PDF complexity)
- **Transliteration fix**: ~2-5ms per page
- **Database upsert**: ~10-20ms per page
- **Total**: ~110-125ms per page

For a 400-page book:
- Estimated time: 45-50 seconds

For 98 books (avg 300 pages each):
- Estimated time: ~1.5-2 hours

## Files

- `pdf_content_transliteration_processor.py` - Main processor
- `test_pdf_processor.py` - Test suite
- `pure_bhakti_vault_db.py` - Database utility
- `sanskrit_utils/` - Transliteration fix modules
- `PDF_PROCESSOR_README.md` - This file

## Version History

### v1.0.4 (2025-12-25)
- **REVERTED** `sort=True` parameter from PyMuPDF `get_text()` calls
- **Reason**: Caused column mixing in multi-column layouts where adjacent columns were being interleaved
- Text now extracted in PDF's native block order, preserving column integrity
- Future enhancement may implement column-aware sorting if needed

### v1.0.3 (2025-12-25) [REVERTED]
- ~~Added `sort=True` to all PyMuPDF `get_text()` calls for natural reading order~~
- ~~Ensures text extracted top-to-bottom, left-to-right for better readability~~
- **Issue found**: Caused multi-column text mixing, reverted in v1.0.4

### v1.0.2 (2025-12-25)
- Added header/footer exclusion support using book metadata
- Reads `header_height` and `footer_height` from book table
- Uses PyMuPDF clipping rectangles to exclude header/footer regions
- See [HEADER_FOOTER_EXCLUSION_FEATURE.md](../../HEADER_FOOTER_EXCLUSION_FEATURE.md) for details

### v1.0.1 (2025-12-25)
- Fixed missing pages not being inserted into content table
- Changed to process ALL PDF pages (not just existing content table records)
- Added page count validation to prevent out-of-range errors
- Added logging for insert vs update counts
- See [INSERT_MISSING_PAGES_FIX.md](../../INSERT_MISSING_PAGES_FIX.md) and [PAGE_COUNT_VALIDATION_FIX.md](../../PAGE_COUNT_VALIDATION_FIX.md) for details

### v1.0.0 (2025-12-25)
- Initial release
- PyMuPDF-based content extraction
- Sanskrit transliteration fixes (sanskrit_utils v1.0.x)
- Resume capability
- Comprehensive logging
- Error handling with stop-on-failure

## Support

For issues or questions:
1. Check logs for error messages
2. Run test suite to diagnose
3. Review this README
4. Check database content table structure

## License

MIT License - Pure Bhakti Vault Project
