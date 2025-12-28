# Google Sheets Template for Book Loader

This document shows exactly how to set up your Google Sheet for the book loader workflow.

## Sheet Setup Instructions

### 1. Create New Google Sheet

1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new blank spreadsheet
3. Name it: **"Pure Bhakti Base - Book Loader"**

### 2. Create 5 Tabs

Rename the default tabs and create the following structure:

#### Tab 1: `book`

**First Row (Headers)**:
```
book_id | pdf_name | book_type | original_book_title | edition | original_author | commentary_author | header_height | footer_height | book_summary
```

**Data Validation** (Optional but recommended):
- Column C (`book_type`): Dropdown list with values: `english`, `tamil`, `rays`

**Column Formatting**:
- Column A: Number format
- Column H-I: Number format (for pixel heights)
- Column J: Wrap text enabled

---

#### Tab 2: `page_map`

**First Row (Headers)**:
```
book_id | page_number | page_label | page_type
```

**Column Formatting**:
- Column A-B: Number format
- Column C: Text format (page labels can be Roman numerals like "xiv")
- Column D: Text format

---

#### Tab 3: `table_of_contents`

**First Row (Headers)**:
```
book_id | pdf_name | toc_level | toc_label | page_number | page_label
```

**Column Formatting**:
- Column A, C, E: Number format
- Column B, D, F: Text format
- Column D: Wrap text enabled (TOC labels can be long)

**Conditional Formatting** (Optional):
- Indent rows by `toc_level`:
  - Level 1: No indent
  - Level 2: Indent 2 spaces
  - Level 3: Indent 4 spaces

---

#### Tab 4: `glossary`

**First Row (Headers)**:
```
book_id | pdf_name | term | definition | page_number | page_label
```

**Column Formatting**:
- Column A, E: Number format
- Column B-D, F: Text format
- Column D: Wrap text enabled (definitions can be long)

**Sorting** (Optional):
- Sort by `book_id` (ascending), then `term` (A-Z)

---

#### Tab 5: `verse_index`

**First Row (Headers)**:
```
book_id | pdf_name | verse_name | page_number | page_label
```

**Column Formatting**:
- Column A, D: Number format
- Column B-C, E: Text format

**Sorting** (Optional):
- Sort by `book_id` (ascending), then `verse_name` (A-Z)

---

## 3. Share with Service Account

### Get Service Account Email

```bash
cat /Users/kamaldivi/Development/Python/pure_bhakti_valut/credentials/google_service_account.json | grep client_email
```

Example output:
```json
"client_email": "book-loader-sa@your-project.iam.gserviceaccount.com"
```

### Share the Sheet

1. Click the **Share** button (top right of Google Sheets)
2. Paste the service account email
3. Select **Editor** permission
4. **Uncheck** "Notify people" (service accounts don't receive emails)
5. Click **Share**

---

## 4. Get Sheet ID

The Sheet ID is in the URL:

```
https://docs.google.com/spreadsheets/d/11-O6tPfw-lNnL_cqrnL7VcF6v2Nvroz0Ecq1jQ_Cv68/edit
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                                     This is the Sheet ID
```

Add to your `.env` file:
```bash
GOOGLE_BOOK_LOADER_SHEET_ID=11-O6tPfw-lNnL_cqrnL7VcF6v2Nvroz0Ecq1jQ_Cv68
```

---

## Sample Data (For Reference)

### `book` Tab Example

| book_id | pdf_name | book_type | original_book_title | edition | original_author | commentary_author | header_height | footer_height | book_summary |
|---------|----------|-----------|---------------------|---------|-----------------|-------------------|---------------|---------------|--------------|
| 121 | bhagavad-gita-4ed.pdf | english | Bhagavad-gita As It Is | 4th Edition | A.C. Bhaktivedanta Swami Prabhupada | | 80 | 60 | The timeless classic on self-realization... |
| 122 | jaiva-dharma.pdf | english | Jaiva Dharma | 2019 Edition | Srila Bhaktivinoda Thakura | | 75 | 65 | A spiritual novel presenting... |

### `page_map` Tab Example

| book_id | page_number | page_label | page_type |
|---------|-------------|------------|-----------|
| 121 | 1 | i | Primary |
| 121 | 2 | ii | Primary |
| 121 | 10 | x | Primary |
| 121 | 15 | xv | Primary |
| 121 | 16 | 1 | Primary |
| 121 | 17 | 2 | Primary |

### `table_of_contents` Tab Example

| book_id | pdf_name | toc_level | toc_label | page_number | page_label |
|---------|----------|-----------|-----------|-------------|------------|
| 121 | bhagavad-gita-4ed.pdf | 1 | Introduction | 15 | xv |
| 121 | bhagavad-gita-4ed.pdf | 1 | Chapter 1: Observing the Armies | 23 | 1 |
| 121 | bhagavad-gita-4ed.pdf | 2 | Text 1 | 24 | 2 |
| 121 | bhagavad-gita-4ed.pdf | 2 | Text 2 | 25 | 3 |
| 121 | bhagavad-gita-4ed.pdf | 1 | Chapter 2: Contents of the Gita | 89 | 67 |

### `glossary` Tab Example

| book_id | pdf_name | term | definition | page_number | page_label |
|---------|----------|------|------------|-------------|------------|
| 121 | bhagavad-gita-4ed.pdf | Bhakti | Devotional service to the Supreme Lord | 850 | 828 |
| 121 | bhagavad-gita-4ed.pdf | Karma | Action performed in accordance with prescribed duties | 850 | 828 |

### `verse_index` Tab Example

| book_id | pdf_name | verse_name | page_number | page_label |
|---------|----------|------------|-------------|------------|
| 121 | bhagavad-gita-4ed.pdf | Bhagavad-gita 1.1 | 23 | 1 |
| 121 | bhagavad-gita-4ed.pdf | Bhagavad-gita 1.2 | 24 | 2 |
| 121 | bhagavad-gita-4ed.pdf | Srimad-Bhagavatam 1.2.6 | 45 | 23 |

---

## Tips for Content Managers

### Efficient Data Entry

1. **Use filters** to work on one book at a time
2. **Freeze the header row** (View → Freeze → 1 row) for easier scrolling
3. **Use data validation** for consistent values (especially `book_type`)
4. **Sort by book_id** to keep related entries together
5. **Use comments** to flag uncertain entries for review

### Common Pitfalls to Avoid

1. **Don't modify `book_id` or `page_number`** - these are auto-generated/extracted
2. **Don't delete header rows** - the script expects them in row 1
3. **Don't rename tabs** - the script looks for exact tab names
4. **Be careful with Roman numerals** in `page_label` (i, ii, iii, iv, v, etc.)
5. **Don't add extra columns** - stick to the template structure

### Data Quality Checks

Before running Part 2:

- [ ] All `book_type` values are valid (english, tamil, or rays)
- [ ] All `original_book_title` values are updated (no "[TO BE ADDED]" placeholders)
- [ ] `header_height` and `footer_height` are reasonable (typically 50-100 pixels)
- [ ] `toc_level` values are sequential (no level 3 without level 2)
- [ ] Page labels match the actual PDF page labels
- [ ] No duplicate TOC entries
- [ ] Glossary terms are alphabetically sorted (per book)

---

## Troubleshooting

### "Error: Worksheet not found"
- Check tab names are exactly: `book`, `page_map`, `table_of_contents`, `glossary`, `verse_index`
- Tab names are case-sensitive

### "Error: Permission denied"
- Verify service account email has **Editor** permissions
- Re-share the sheet if needed

### Data doesn't appear after running script
- Check you're looking at the correct Google Sheet (verify Sheet ID in .env)
- Ensure script completed without errors
- Try refreshing the Google Sheet (Ctrl+R or Cmd+R)

### Formatting gets messed up
- After the script writes data, you can format cells as needed
- The script only appends data, it doesn't modify formatting

---

## Quick Setup Checklist

- [ ] Create Google Sheet with 5 tabs
- [ ] Add header rows to each tab (see above)
- [ ] Get service account email from credentials file
- [ ] Share sheet with service account email (Editor permission)
- [ ] Copy Sheet ID from URL
- [ ] Add Sheet ID to `.env` file as `GOOGLE_BOOK_LOADER_SHEET_ID`
- [ ] Run test: `python src/prod_utils/google_sheets_test.py`
- [ ] Ready to run book loader!

---

**Last Updated**: 2025-01-12
