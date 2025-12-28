# Book Loader Workflow - Complete Guide

## Overview

The book loading process is split into **two parts**:

### **Part 1: Automated Extraction & Preparation** (This script)
- Scans PDFs and extracts basic metadata
- Creates minimal database records
- Generates page maps with auto-detected page labels
- Extracts TOC from PDF bookmarks
- Renders WebP images
- **Writes all data to Google Sheets for manual review/enrichment**

### **Part 2: Manual Review & Database Sync** (Future)
- Content managers review/update data in Google Sheets
- Sync approved changes back to database
- Load table_of_contents, glossary, verse_index to database

---

## Prerequisites

### 1. Environment Setup

Ensure your `.env` file has these variables configured:

```bash
# PDF and Output Folders
PDF_FOLDER=/Users/kamaldivi/Development/pbb_books/Harmonist/unsec/
PAGE_FOLDER=/Users/kamaldivi/Development/pbb_book_pages/

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pure_bhakti_vault
DB_USER=pbbdbuser
DB_PASSWORD=Govinda2025#

# Google Sheets Configuration
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/credentials/google_service_account.json
GOOGLE_BOOK_LOADER_SHEET_ID=your_google_sheet_id_here

# Optional: Rendering Configuration
RENDER_DPI=150
RENDER_FORMAT=webp
RENDER_GRAYSCALE=false
```

### 2. Google Sheets Setup

#### Create the Google Sheet with 5 tabs:

1. **Tab: `book`**
   - Header row (row 1):
     ```
     book_id | pdf_name | book_type | original_book_title | edition | original_author | commentary_author | header_height | footer_height | book_summary
     ```

2. **Tab: `page_map`**
   - Header row (row 1):
     ```
     book_id | page_number | page_label | page_type
     ```

3. **Tab: `table_of_contents`**
   - Header row (row 1):
     ```
     book_id | pdf_name | toc_level | toc_label | page_number | page_label
     ```

4. **Tab: `glossary`**
   - Header row (row 1):
     ```
     book_id | pdf_name | term | definition | page_number | page_label
     ```

5. **Tab: `verse_index`**
   - Header row (row 1):
     ```
     book_id | pdf_name | verse_name | page_number | page_label
     ```

#### Share the Sheet

1. Get your service account email from the credentials JSON file:
   ```bash
   cat credentials/google_service_account.json | grep client_email
   ```

2. Open your Google Sheet
3. Click **Share**
4. Add the service account email with **Editor** permissions
5. Copy the Sheet ID from the URL and add to `.env`:
   ```
   GOOGLE_BOOK_LOADER_SHEET_ID=11-O6tPfw-lNnL_cqrnL7VcF6v2Nvroz0Ecq1jQ_Cv68
   ```

### 3. Database Schema

Required tables (should already exist):
- `book` - Book metadata
- `page_map` - Page mappings
- `table_of_contents` - Table of contents entries
- `glossary` - Glossary terms
- `verse_index` - Verse references

---

## Part 1: Running the Book Loader

### Step 1: Place PDFs in PDF_FOLDER

```bash
# Copy your PDF files to the configured folder
cp /path/to/your/pdfs/*.pdf /Users/kamaldivi/Development/pbb_books/Harmonist/unsec/
```

### Step 2: Run Dry-Run Test (Recommended First)

```bash
cd /Users/kamaldivi/Development/Python/pure_bhakti_valut
python src/prod_utils/book_loader_part1.py --dry-run
```

This will:
- Validate configuration
- Scan PDFs and show what would be processed
- **NOT write anything** to database or Google Sheets

### Step 3: Run Production Mode

```bash
python src/prod_utils/book_loader_part1.py
```

Or with verbose logging:

```bash
python src/prod_utils/book_loader_part1.py --verbose
```

### What Happens During Execution

```
STEP 1: Scanning PDF folder
├─ Scans PDF_FOLDER for *.pdf files
├─ Extracts file_size_bytes, number_of_pages
├─ Skips PDFs already in database
└─ Shows count of new vs existing PDFs

STEP 2: Creating database book records
├─ Inserts minimal book data:
│   ├─ pdf_name
│   ├─ original_book_title = "[TO BE ADDED] {pdf_name}"  (placeholder)
│   ├─ number_of_pages
│   └─ file_size_bytes
└─ Captures auto-generated book_id

STEP 3: Writing to Google Sheets - book tab
├─ Appends rows with:
│   ├─ book_id, pdf_name
│   ├─ Placeholder original_book_title
│   └─ Empty columns for manual entry
└─ Content managers will fill in the rest

STEP 4: Generating page maps
├─ Uses page_map_builder.py to extract page labels
├─ Tries embedded PDF page labels first
├─ Falls back to page_number if no labels
├─ Writes to database page_map table
└─ Collects all page_map entries

STEP 4b: Writing page maps to Google Sheets
├─ Appends all page_map entries to 'page_map' tab
└─ Format: book_id, page_number, page_label, page_type

STEP 5: Extracting TOC from PDF bookmarks
├─ Uses PyMuPDF to extract PDF bookmarks/outlines
├─ Converts to TOC format with hierarchy levels
├─ Maps page_number to page_label using page_map
└─ Only writes to Google Sheets (NOT database)

STEP 5b: Writing TOC to Google Sheets
├─ Appends TOC entries to 'table_of_contents' tab
└─ Format: book_id, pdf_name, toc_level, toc_label, page_number, page_label

STEP 6: Rendering WebP images
├─ Uses render_pdf_pages.py for selected book_ids
├─ Converts all pages to WebP format
├─ Saves to: PAGE_FOLDER/{book_id}/{page_number}.webp
└─ No thumbnails (as per requirement)
```

### Expected Output

```
======================================================================
📚 BOOK LOADER - PART 1
======================================================================
PDF Folder: /Users/kamaldivi/Development/pbb_books/Harmonist/unsec/
Page Folder: /Users/kamaldivi/Development/pbb_book_pages/
Mode: PRODUCTION
======================================================================

======================================================================
STEP 1: Scanning PDF folder for new books
======================================================================
Found 15 PDF files
Extracting PDF metadata: 100%|████████████████| 15/15

📊 Scan complete:
   Total PDFs found: 15
   Already in database: 5
   New PDFs to process: 10

======================================================================
STEP 2: Creating database book records
======================================================================
Creating book records: 100%|████████████████| 10/10
  ✅ Created book_id=121: book1.pdf
  ✅ Created book_id=122: book2.pdf
  ...

📊 Books created: 10

======================================================================
STEP 3: Writing book metadata to Google Sheets
======================================================================
  ✅ Wrote 10 rows to 'book' tab

======================================================================
STEP 4: Generating page maps
======================================================================
Generating page maps: 100%|████████████████| 10/10
  ✅ Generated 250 page maps for book_id=121
  ...

📊 Page maps created: 2500

======================================================================
STEP 4b: Writing page maps to Google Sheets
======================================================================
  ✅ Wrote 2500 rows to 'page_map' tab

======================================================================
STEP 5: Extracting TOC from PDF bookmarks
======================================================================
Extracting bookmarks: 100%|████████████████| 10/10
  ✅ Extracted 45 TOC entries from book1.pdf
  ⚠️  No bookmarks found in book2.pdf
  ...

📊 TOC entries extracted: 350

======================================================================
STEP 5b: Writing TOC entries to Google Sheets
======================================================================
  ✅ Wrote 350 rows to 'table_of_contents' tab

======================================================================
STEP 6: Rendering WebP images
======================================================================
Rendering pages: 100%|████████████████| 2500/2500
...

📊 Image rendering complete:
   Total pages: 2500
   Successful: 2500
   Failed: 0

======================================================================
📊 EXECUTION SUMMARY
======================================================================
PDFs scanned: 15
PDFs skipped (existing): 5
Books created: 10
Page maps created: 2500
TOC entries extracted: 350
Images rendered: 2500
Errors: 0
Elapsed time: 0:15:23
======================================================================

🎉 Part 1 completed successfully!

📝 Next steps:
   1. Open Google Sheets to review/update book metadata
   2. Fill in: book_type, original_book_title, edition, authors, etc.
   3. Review/correct page_label values in page_map tab
   4. Review/edit TOC entries in table_of_contents tab
   5. Run Part 2 to sync changes back to database
======================================================================
```

---

## Part 2: Content Manager Manual Review

After Part 1 completes, content managers review and enrich the data in Google Sheets:

### Tab 1: `book` - Book Metadata Review

**Tasks:**
1. Update `book_type` (dropdown: english, tamil, rays)
2. Update `original_book_title` (replace placeholder with actual title)
3. Add `edition` (e.g., "2nd Edition", "Revised 2019")
4. Add `original_author` (e.g., "Srila Bhaktivinoda Thakura")
5. Add `commentary_author` (if applicable)
6. Add `header_height` (in pixels, for page cropping)
7. Add `footer_height` (in pixels, for page cropping)
8. Add `book_summary` (brief description)

**Example:**
```
Before:
book_id | pdf_name         | book_type | original_book_title           | edition | ...
121     | bhagavad-gita.pdf|           | [TO BE ADDED] bhagavad-gita.pdf|         | ...

After:
book_id | pdf_name         | book_type | original_book_title   | edition      | original_author | ...
121     | bhagavad-gita.pdf| english   | Bhagavad-gita As It Is| 4th Edition  | A.C. Bhaktivedanta Swami | ...
```

### Tab 2: `page_map` - Page Label Review

**Tasks:**
1. Review auto-extracted `page_label` values
2. Correct any mistakes (e.g., Roman numerals misread as Arabic)
3. Ensure page labels match the actual PDF page labels

**Example corrections:**
```
Before:
book_id | page_number | page_label | page_type
121     | 10          | x          | Primary    (Roman numeral X)
121     | 11          | 11         | Primary    (Should be xi)

After:
book_id | page_number | page_label | page_type
121     | 10          | x          | Primary
121     | 11          | xi         | Primary
```

### Tab 3: `table_of_contents` - TOC Review/Edit

**Tasks:**
1. Review auto-extracted TOC entries
2. Fix any OCR errors in `toc_label`
3. Correct `toc_level` hierarchy if needed
4. Add missing entries (if PDF had incomplete bookmarks)
5. Verify `page_label` mappings

**Example:**
```
book_id | pdf_name         | toc_level | toc_label           | page_number | page_label
121     | bhagavad-gita.pdf| 1         | Introduction        | 15          | xv
121     | bhagavad-gita.pdf| 1         | Chapter 1           | 23          | 1
121     | bhagavad-gita.pdf| 2         | Text 1              | 24          | 2
121     | bhagavad-gita.pdf| 2         | Text 2              | 25          | 3
```

### Tab 4: `glossary` - Manual Entry

**Tasks:**
1. Manually add glossary terms (Part 1 doesn't extract these)
2. Use format: book_id, pdf_name, term, definition, page_number, page_label

### Tab 5: `verse_index` - Manual Entry

**Tasks:**
1. Manually add verse references (Part 1 doesn't extract these)
2. Use format: book_id, pdf_name, verse_name, page_number, page_label

---

## Troubleshooting

### Error: "PDF_FOLDER not found"
- Check that the path in `.env` is correct and absolute
- Verify the folder exists: `ls -la /path/to/PDF_FOLDER`

### Error: "GOOGLE_SERVICE_ACCOUNT_FILE not found"
- Ensure you downloaded the service account JSON from GCP
- Save it to: `credentials/google_service_account.json`
- Update path in `.env`

### Error: "Failed to write to Google Sheets"
- Verify the service account email has Editor permissions on the sheet
- Check the sheet ID in `.env` matches your Google Sheet URL
- Ensure all 5 tabs exist with correct names (case-sensitive)

### Error: "original_book_title violates not-null constraint"
- This shouldn't happen - the script uses a placeholder title
- If it does, check the database schema allows the placeholder format

### Some PDFs have no TOC extracted
- This is normal - not all PDFs have embedded bookmarks
- Content managers will need to manually enter TOC for these books

### Images fail to render
- Check PAGE_FOLDER is writable
- Ensure sufficient disk space
- Verify PyMuPDF (fitz) is installed: `pip install PyMuPDF`

---

## Configuration Reference

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `PDF_FOLDER` | Yes | Source PDF files location | `/Users/.../pbb_books/Harmonist/unsec/` |
| `PAGE_FOLDER` | Yes | WebP output location | `/Users/.../pbb_book_pages/` |
| `DB_HOST` | Yes | PostgreSQL host | `localhost` |
| `DB_PORT` | Yes | PostgreSQL port | `5432` |
| `DB_NAME` | Yes | Database name | `pure_bhakti_vault` |
| `DB_USER` | Yes | Database user | `pbbdbuser` |
| `DB_PASSWORD` | Yes | Database password | `YourPassword` |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Yes | Path to GCP credentials | `.../credentials/google_service_account.json` |
| `GOOGLE_BOOK_LOADER_SHEET_ID` | Yes | Google Sheet ID | `11-O6tPfw-lNnL_cqr...` |
| `RENDER_DPI` | No | Image DPI (default: 150) | `150` |
| `RENDER_FORMAT` | No | Image format (default: webp) | `webp` |
| `RENDER_GRAYSCALE` | No | Grayscale mode (default: false) | `false` |

### Command-Line Options

```bash
python src/prod_utils/book_loader_part1.py [OPTIONS]

Options:
  --dry-run    Validation mode: no database or Google Sheets writes
  --verbose    Enable verbose logging
  --help       Show this message and exit
```

---

## Part 3: Running Book Loader Part 2

After content managers have reviewed and enriched the data in Google Sheets, run Part 2 to sync changes back to the database.

### Step 1: Verify Google Sheets Data

Before running Part 2, ensure:
- [ ] All `original_book_title` fields are updated (no "[TO BE ADDED]" placeholders)
- [ ] All required fields are filled in
- [ ] Data quality checks passed (see [GOOGLE_SHEETS_TEMPLATE.md](GOOGLE_SHEETS_TEMPLATE.md))

### Step 2: Run Dry-Run Test (Recommended First)

```bash
cd /Users/kamaldivi/Development/Python/pure_bhakti_valut
python src/prod_utils/book_loader_part2.py --dry-run
```

This will:
- Read all data from Google Sheets
- Show what would be updated/inserted
- **NOT write anything** to the database

### Step 3: Run Production Mode

```bash
# Sync all books
python src/prod_utils/book_loader_part2.py

# Sync specific books only
python src/prod_utils/book_loader_part2.py --book-ids 121,122,123

# With verbose logging
python src/prod_utils/book_loader_part2.py --verbose
```

### What Happens During Part 2

```
STEP 1: Updating book metadata
├─ Reads 'book' tab from Google Sheets
├─ Filters books with updated titles (skips "[TO BE ADDED]" placeholders)
├─ Updates database book table with:
│   ├─ book_type
│   ├─ original_book_title
│   ├─ edition
│   ├─ original_author
│   ├─ commentary_author
│   ├─ header_height
│   ├─ footer_height
│   └─ book_summary
└─ Only updates fields that have values (skips empty fields)

STEP 2: Updating page maps
├─ Reads 'page_map' tab from Google Sheets
├─ Compares with existing page_map table in database
├─ Identifies changed page_label values
└─ Updates only the changed page labels

STEP 3: Inserting table of contents
├─ Reads 'table_of_contents' tab from Google Sheets
├─ Checks for existing TOC entries (avoids duplicates)
├─ Inserts new TOC entries with:
│   ├─ book_id
│   ├─ toc_level
│   ├─ toc_label
│   ├─ page_number
│   └─ page_label
└─ Uses ON CONFLICT DO NOTHING for safety

STEP 4: Inserting glossary entries
├─ Reads 'glossary' tab from Google Sheets
├─ Filters out empty rows
├─ Checks for existing entries (book_id + term unique key)
├─ Inserts new glossary entries
└─ Updates definition if term already exists

STEP 5: Inserting verse index entries
├─ Reads 'verse_index' tab from Google Sheets
├─ Filters out empty rows
├─ Checks for existing entries (book_id + verse_name + page_number unique key)
└─ Inserts new verse entries
```

### Expected Output

```
======================================================================
📚 BOOK LOADER - PART 2
======================================================================
Mode: PRODUCTION
Processing: ALL books
======================================================================

📖 Reading data from Google Sheets...
  ✅ Read 10 rows from 'book' tab
  ✅ Read 2500 rows from 'page_map' tab
  ✅ Read 350 rows from 'table_of_contents' tab
  ✅ Read 125 rows from 'glossary' tab
  ✅ Read 0 rows from 'verse_index' tab

======================================================================
STEP 1: Updating book metadata
======================================================================
Updating books: 100%|████████████████| 10/10
  ✅ Updated book_id=121: Bhagavad-gita As It Is
  ✅ Updated book_id=122: Jaiva Dharma
  ⚠️  Skipping book_id=123: Title not updated (still placeholder)
  ...

📊 Books updated: 9

======================================================================
STEP 2: Updating page maps
======================================================================
Found 15 page labels that need updating
Updating page maps: 100%|████████████████| 15/15

📊 Page maps updated: 15

======================================================================
STEP 3: Inserting table of contents
======================================================================
Found 0 existing TOC entries
Inserting 350 new TOC entries
Inserting TOC entries: 100%|████████████████| 350/350

📊 TOC entries inserted: 350

======================================================================
STEP 4: Inserting glossary entries
======================================================================
Found 0 existing glossary entries
Inserting 125 new glossary entries
Inserting glossary: 100%|████████████████| 125/125

📊 Glossary entries inserted: 125

======================================================================
STEP 5: Inserting verse index entries
======================================================================
No verse index entries to insert

📊 Verse entries inserted: 0

======================================================================
📊 EXECUTION SUMMARY
======================================================================
Books updated: 9
Page maps updated: 15
TOC entries inserted: 350
Glossary entries inserted: 125
Verse entries inserted: 0
Skipped: 1
Errors: 0
Elapsed time: 0:01:23
======================================================================

🎉 Part 2 completed successfully!

📝 Next steps:
   1. Verify data in database
   2. Test book display in web app
   3. Deploy static assets if needed
======================================================================
```

---

## Part 4: Book Deployment (Manual)

After both Part 1 and Part 2 complete successfully:

### 1. Deploy WebP Images to Nginx

```bash
# Copy rendered images to Docker Nginx static mount
sudo cp -r /Users/kamaldivi/Development/pbb_book_pages/* /opt/pbb_static_content/pbb_book_pages/

# Set correct permissions
sudo chown -R www-data:www-data /opt/pbb_static_content/pbb_book_pages/
```

### 2. Deploy PDF Files for Download

```bash
# Copy original PDFs to download location
sudo cp /Users/kamaldivi/Development/pbb_books/*.pdf /opt/pbb_static_content/pbb_pdf_files/

# Set correct permissions
sudo chown -R www-data:www-data /opt/pbb_static_content/pbb_pdf_files/
```

### 3. Deploy Book Thumbnails (if applicable)

```bash
# Copy thumbnails
sudo cp /path/to/thumbnails/*.jpg /opt/pbb_static_content/pbb_book_thumbnails/

# Set correct permissions
sudo chown -R www-data:www-data /opt/pbb_static_content/pbb_book_thumbnails/
```

### 4. Verify in Web App

1. Open the web application
2. Navigate to the book listing page
3. Verify new books appear with correct metadata
4. Test opening a book and viewing pages
5. Verify TOC navigation works
6. Check glossary and verse index (if applicable)

---

## Troubleshooting Part 2

### Error: "Failed to authenticate with Google Sheets"
- Verify service account credentials file exists
- Check permissions on the Google Sheet
- Ensure Sheet ID in `.env` is correct

### Error: "Title not updated (still placeholder)"
- Content managers need to update the `original_book_title` column
- Remove "[TO BE ADDED]" prefix and add actual book title
- Re-run Part 2 after updating

### Error: "Duplicate key violation"
- This means data already exists in database
- Part 2 uses `ON CONFLICT` to handle duplicates safely
- Check if you're running Part 2 multiple times on the same data

### No TOC/Glossary/Verse entries inserted
- Check if the Google Sheet tabs have data
- Verify tab names are exactly: `table_of_contents`, `glossary`, `verse_index`
- Check if entries already exist in database (Part 2 skips duplicates)

### Book updated but TOC missing
- Verify `table_of_contents` tab has entries for that book_id
- Check that `book_id` values match between tabs
- Run with `--book-ids` filter to focus on specific books

---

## Support

For issues or questions:
- Check this guide first
- Review the error messages in the console output
- Check Google Sheets permissions
- Verify database connection with: `python -c "from pure_bhakti_vault_db import PureBhaktiVaultDB; db = PureBhaktiVaultDB(); print(db.test_connection())"`
- Compare data between Google Sheets and database to identify discrepancies

---

## Quick Reference

### Part 1 (Automated Extraction)
```bash
# Test
python src/prod_utils/book_loader_part1.py --dry-run

# Run
python src/prod_utils/book_loader_part1.py
```

### Part 2 (Sync to Database)
```bash
# Test
python src/prod_utils/book_loader_part2.py --dry-run

# Run all books
python src/prod_utils/book_loader_part2.py

# Run specific books
python src/prod_utils/book_loader_part2.py --book-ids 121,122,123
```

---

**Last Updated**: 2025-01-12
