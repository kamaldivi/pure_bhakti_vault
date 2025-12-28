# 📘 Pure Bhakti Base – Book Loading Process

This document describes the step-by-step process to onboard a new book (PDF) into the **Pure Bhakti Base** library.
It involves preparing metadata, generating derived assets (page maps, TOC, images, etc.), and deploying them into the production static content mount.

---

## Step 1: Prepare Source PDFs

1. Save all book PDF files to be loaded into a local working folder, for example:

   ```bash
   ~/pbb_data/book_pdfs/
   ```

2. Verify each PDF is clean and readable.

---

## Step 2: Compile and Load Book Metadata

1. Manually record metadata for all books in a **Google Sheet** using the following template columns:

   | pdf_name | book_type | original_book_title | edition | original_author | commentary_author | header_height | footer_height | book_summary |
   |----------|-----------|---------------------|---------|-----------------|-------------------|---------------|---------------|--------------|

2. Export the sheet as a CSV and save it locally (e.g., `book_metadata.csv`).

3. Use the **Python Book Loader Utility** ([src/prod_utils/book_loader.py](src/prod_utils/book_loader.py)) to load metadata into the `book` table:

   ```bash
   python src/prod_utils/book_loader.py --input book_metadata.csv
   ```

   This utility automatically assigns a `book_id` to each entry in the database.

---

## Step 3: Generate Page Map

1. Run the **Page Map Builder Utility** ([src/prod_utils/page_map_builder.py](src/prod_utils/page_map_builder.py)) from the command line.

2. This utility reads PDFs from the folder and cross-references them with the `book` table to identify `book_id` values:

   ```bash
   python src/prod_utils/page_map_builder.py --pdf_folder ~/pbb_data/book_pdfs --db_url postgresql://user:pass@localhost/pbb_db
   ```

3. The utility populates the `page_map` table with one record per PDF page, including `page_number`, `page_label`, and file mapping.

---

## Step 4: Create Table of Contents (TOC)

1. Manually compile the TOC for each book using a CSV with the following format:

   | book_id | pdf_name | toc_level | toc_label | page_label |
   |---------|----------|-----------|-----------|------------|

2. Save the CSV (e.g., `toc_entries.csv`).

3. Load the TOC using the **TOC Loader Utility** ([src/prod_utils/toc_loader.py](src/prod_utils/toc_loader.py)):

   ```bash
   python src/prod_utils/toc_loader.py --input toc_entries.csv
   ```

---

## Step 5: Generate WebP Page Images

1. Run the **Render PDF Pages Utility** ([src/prod_utils/render_pdf_pages.py](src/prod_utils/render_pdf_pages.py)) to convert all PDF pages into `.webp` images for web display:

   ```bash
   python src/prod_utils/render_pdf_pages.py --pdf_folder ~/pbb_data/book_pdfs
   ```

2. The script generates page images in the following folder structure:

   ```
   {book_id}/{page_number}.webp
   ```

3. After generation, manually copy the image folders into the Docker Nginx mount for static content:

   ```bash
   /opt/pbb_static_content/pbb_book_pages/
   ```

---

## Step 6: Deploy Book Thumbnails

Copy the thumbnail images for each book cover into the Docker Nginx static mount:

```bash
/opt/pbb_static_content/pbb_book_thumbnails/
```

You can use the **Copy Thumbnails Utility** ([src/prod_utils/copy_thumbnails.py](src/prod_utils/copy_thumbnails.py)) to automate this process.

---

## Step 7: Deploy Downloadable PDFs

Copy the original PDF files (for user downloads) into:

```bash
/opt/pbb_static_content/pbb_pdf_files/
```

---

## Step 8: Extract Glossaries (if applicable)

For books containing glossaries, use a combination of:

- ChatGPT-assisted extraction (for semantic parsing of definitions)
- **Python Glossary Utilities** ([src/prod_utils/glossary_extractor.py](src/prod_utils/glossary_extractor.py)) to structure entries and load them into the `glossary` table

---

## Step 9: Extract Verse Index (if applicable)

For books containing Sanskrit or verse references, use:

- **Python Verse Index Utility** ([src/prod_utils/verse_index_extractor.py](src/prod_utils/verse_index_extractor.py)) for parsing and normalization
- ChatGPT-assisted transliteration verification (IAST and Unicode mapping)
- Load verified entries into the `verse_index` table

---

## ✅ Final Validation Checklist

- [ ] Book metadata loaded and verified in `book` table
- [ ] Page map entries generated and linked to correct `book_id`
- [ ] TOC entries loaded successfully
- [ ] All WebP page images available under `/opt/pbb_static_content/pbb_book_pages/`
- [ ] Thumbnails and downloadable PDFs deployed correctly
- [ ] Glossary and verse index (if applicable) extracted and verified
- [ ] Reader page and TOC navigation tested in the web app

---

## 📝 Notes

- All utilities assume proper configuration of your `.env` file (database credentials, paths, and environment variables)
- Ensure Docker containers for API and Nginx are running before copying static files
- Always back up the database before running bulk insert utilities

---

## 🔧 Related Utilities

Additional utilities that may be useful during the book loading process:

- [src/prod_utils/bookmark_extractor.py](src/prod_utils/bookmark_extractor.py) - Extract PDF bookmarks/outlines
- [src/prod_utils/pdf_metadata_extractor.py](src/prod_utils/pdf_metadata_extractor.py) - Extract metadata from PDF files
- [src/prod_utils/sanskrit_utils.py](src/prod_utils/sanskrit_utils.py) - Sanskrit text processing and transliteration
- [src/prod_utils/split_double_page_pdf.py](src/prod_utils/split_double_page_pdf.py) - Split double-page spreads
- [src/prod_utils/merge_odd_even_pages.py](src/prod_utils/merge_odd_even_pages.py) - Merge separately scanned odd/even pages
- [src/prod_utils/remove_pdf_security.py](src/prod_utils/remove_pdf_security.py) - Remove PDF password protection
- [src/prod_utils/toc_csv_combiner.py](src/prod_utils/toc_csv_combiner.py) - Combine multiple TOC CSV files


