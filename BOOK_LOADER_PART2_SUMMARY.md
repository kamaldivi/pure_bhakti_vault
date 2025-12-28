# Book Loader Part 2 - Quick Reference

## Overview

**Book Loader Part 2** syncs reviewed/enriched data from Google Sheets back to the PostgreSQL database.

After content managers have manually reviewed and updated data in Google Sheets (filled in missing metadata, corrected page labels, etc.), this script reads that data and updates the database accordingly.

---

## Quick Start

### 1. Dry-Run (Test Mode)

```bash
python src/prod_utils/book_loader_part2.py --dry-run
```

Shows what would be updated without writing to database.

### 2. Production Mode

```bash
# Sync all books
python src/prod_utils/book_loader_part2.py

# Sync specific books only
python src/prod_utils/book_loader_part2.py --book-ids 121,122,123

# Verbose logging
python src/prod_utils/book_loader_part2.py --verbose
```

---

## What Part 2 Does

### ✅ Step 1: Update Book Metadata

Reads `book` tab from Google Sheets and updates database `book` table with:
- `book_type` (english, tamil, rays)
- `original_book_title` (must be updated from placeholder)
- `edition` (e.g., "4th Edition")
- `original_author`
- `commentary_author`
- `header_height` (pixels)
- `footer_height` (pixels)
- `book_summary`

**Skips:**
- Books with placeholder titles still containing "[TO BE ADDED]"
- Empty fields (only updates fields with values)

### ✅ Step 2: Update Page Maps

Reads `page_map` tab and:
- Compares with existing database page_map entries
- Identifies changed `page_label` values
- Updates only the changed page labels

**Smart diffing:** Only updates what changed, not the entire table.

### ✅ Step 3: Insert Table of Contents

Reads `table_of_contents` tab and:
- Sorts entries by book_id and page_number for proper sequencing
- Deletes existing TOC entries per book for clean rebuild
- Inserts new TOC entries with hierarchical parent-child relationships
- Tracks parent_toc_id using parent stack algorithm (same as toc_loader.py)
- Ensures entries appear in page order within each book

**Delete & rebuild strategy:** Deletes all TOC for each book, then rebuilds with correct hierarchy.

### ✅ Step 4: Insert Glossary

Reads `glossary` tab and:
- Inserts new glossary terms
- Updates definitions if term already exists (book_id + term unique key)
- Filters out empty rows

**Note:** Google Sheet uses "definition" column, database uses "description" field.

### ✅ Step 5: Insert Verse Index

Reads `verse_index` tab and:
- Inserts new verse references
- Checks for duplicates (book_id + verse_name + page_number)
- Skips entries that already exist

---

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Validation mode: reads data but doesn't write to database |
| `--book-ids ID,ID,ID` | Process only specific book IDs (comma-separated) |
| `--verbose` or `-v` | Enable debug logging |
| `--help` | Show help message |

---

## Safety Features

### 1. Duplicate Prevention
- Uses `ON CONFLICT` clauses to handle duplicates safely
- Checks existing data before inserting
- Never creates duplicate entries

### 2. Placeholder Detection
- Automatically skips books with "[TO BE ADDED]" in title
- Warns content managers to update titles first

### 3. Validation
- Filters out empty rows
- Validates required fields
- Logs errors without stopping execution

### 4. Incremental Updates
- Only updates changed data (smart diffing for page_map)
- Doesn't overwrite unchanged records
- Tracks statistics for each operation

### 5. Dry-Run Mode
- Test everything before committing to database
- Shows exactly what would be updated/inserted
- Zero risk

---

## Expected Results

### Successful Run

```
📊 EXECUTION SUMMARY
Books updated: 9
Page maps updated: 15
TOC entries inserted: 350
Glossary entries inserted: 125
Verse entries inserted: 0
Skipped: 1
Errors: 0
Elapsed time: 0:01:23

🎉 Part 2 completed successfully!
```

### Nothing to Update

```
📊 EXECUTION SUMMARY
Books updated: 0
Page maps updated: 0
TOC entries inserted: 0
Glossary entries inserted: 0
Verse entries inserted: 0
Skipped: 0
Errors: 0

✅ No changes needed - all data is up to date
```

### Partial Update (Some Skipped)

```
📊 EXECUTION SUMMARY
Books updated: 8
Page maps updated: 15
TOC entries inserted: 300
Glossary entries inserted: 100
Verse entries inserted: 0
Skipped: 2
Errors: 0

⚠️  Skipping book_id=123: Title not updated (still placeholder)
⚠️  Skipping book_id=124: Title not updated (still placeholder)
```

---

## Common Workflows

### Workflow 1: Complete Book Loading

```bash
# Part 1: Extract and prepare
python src/prod_utils/book_loader_part1.py

# Content managers review/update Google Sheets
# (Fill in book_type, titles, authors, etc.)

# Part 2: Sync back to database
python src/prod_utils/book_loader_part2.py --dry-run  # Test first
python src/prod_utils/book_loader_part2.py            # Actual sync
```

### Workflow 2: Update Specific Books

```bash
# Content managers updated books 121, 122, 123 in Google Sheets

# Sync only those books
python src/prod_utils/book_loader_part2.py --book-ids 121,122,123
```

### Workflow 3: Fix Page Labels

```bash
# Content managers corrected page labels in Google Sheets

# Part 2 will detect and update only changed labels
python src/prod_utils/book_loader_part2.py
```

### Workflow 4: Add Glossary/TOC Later

```bash
# Initial run (no glossary yet)
python src/prod_utils/book_loader_part2.py

# Content managers add glossary entries to Google Sheets

# Run again - only inserts new glossary entries
python src/prod_utils/book_loader_part2.py
```

---

## Troubleshooting

### "Failed to authenticate with Google Sheets"

**Cause:** Service account credentials or permissions issue

**Fix:**
1. Check `GOOGLE_SERVICE_ACCOUNT_FILE` path in `.env`
2. Verify service account has Editor permissions on sheet
3. Ensure `GOOGLE_BOOK_LOADER_SHEET_ID` is correct

### "Title not updated (still placeholder)"

**Cause:** Content managers haven't updated book titles yet

**Fix:**
1. Open Google Sheets `book` tab
2. Find rows with `[TO BE ADDED]` in `original_book_title`
3. Replace with actual book titles
4. Re-run Part 2

### "No TOC entries inserted" (but expected entries)

**Cause:** Either duplicates or missing data

**Fix:**
1. Check if TOC entries already exist in database:
   ```sql
   SELECT * FROM table_of_contents WHERE book_id = 121;
   ```
2. Verify `table_of_contents` tab in Google Sheets has data
3. Check `book_id` values match between tabs

### Database connection errors

**Cause:** PostgreSQL not accessible

**Fix:**
1. Test connection:
   ```python
   from pure_bhakti_vault_db import PureBhaktiVaultDB
   db = PureBhaktiVaultDB()
   print(db.test_connection())
   ```
2. Check database is running: `psql -h localhost -U pbbdbuser -d pure_bhakti_vault`
3. Verify credentials in `.env`

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Google Sheets                         │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐  │
│  │   book   │  │page_map │  │table_of_contents   │  │
│  └──────────┘  └──────────┘  └─────────────────────┘  │
│  ┌──────────┐  ┌──────────┐                           │
│  │ glossary │  │verse_index│                          │
│  └──────────┘  └──────────┘                           │
└─────────────────────────────────────────────────────────┘
                        │
                        │ book_loader_part2.py
                        │ (reads & syncs)
                        ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL Database                        │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐  │
│  │   book   │  │page_map │  │table_of_contents   │  │
│  │(updated) │  │(updated) │  │    (inserted)       │  │
│  └──────────┘  └──────────┘  └─────────────────────┘  │
│  ┌──────────┐  ┌──────────┐                           │
│  │ glossary │  │verse_index│                          │
│  │(inserted)│  │(inserted) │                          │
│  └──────────┘  └──────────┘                           │
└─────────────────────────────────────────────────────────┘
```

---

## Performance Notes

**Typical execution time:**
- Small batches (1-5 books): 10-30 seconds
- Medium batches (10-20 books): 1-2 minutes
- Large batches (50+ books): 3-5 minutes

**What affects performance:**
- Number of page_map entries to compare
- Number of TOC entries to insert
- Database query speed
- Network latency (Google Sheets API)

**Optimization tips:**
- Use `--book-ids` to process specific books
- Run during off-peak hours for large batches
- Ensure database has proper indexes (already configured)

---

## Integration with Web App

After Part 2 completes:

1. ✅ Books appear in book listing with correct metadata
2. ✅ Page labels display correctly in reader
3. ✅ TOC navigation works in web app
4. ✅ Glossary search returns results
5. ✅ Verse index search returns results

**No web app restart needed** - changes are immediate in database.

---

## Best Practices

### For Content Managers

1. **Complete one book at a time** - easier to verify
2. **Use consistent naming** - especially for authors, editions
3. **Double-check book_type** - must be: english, tamil, or rays
4. **Test with dry-run first** - catch errors before committing
5. **Document uncertain values** - use Google Sheets comments

### For Administrators

1. **Always run dry-run first** - especially for large batches
2. **Use book-ids filter** - test with 1-2 books initially
3. **Backup database** - before large data syncs
4. **Monitor logs** - check for warnings and errors
5. **Verify in web app** - test actual book display after sync

---

## Related Documentation

- **Complete workflow**: [BOOK_LOADER_WORKFLOW.md](BOOK_LOADER_WORKFLOW.md)
- **Google Sheets setup**: [GOOGLE_SHEETS_TEMPLATE.md](GOOGLE_SHEETS_TEMPLATE.md)
- **Part 1 script**: [src/prod_utils/book_loader_part1.py](src/prod_utils/book_loader_part1.py)
- **Part 2 script**: [src/prod_utils/book_loader_part2.py](src/prod_utils/book_loader_part2.py)

---

**Last Updated**: 2025-01-12
