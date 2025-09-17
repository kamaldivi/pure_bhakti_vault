# PDF Page Renderer

Production-ready Python script for rendering PDF pages to web-ready images based on PostgreSQL database content.

## Overview

This script reads `(book_id, page_number)` pairs from the PostgreSQL `content` table, locates the corresponding PDF files, and renders each page to optimized web-ready images with optional thumbnail generation.

## Features

- **Database Integration**: Reads page data from PostgreSQL `content` table
- **Web-Optimized Output**: Produces compressed WebP or PNG images
- **Grayscale Support**: Reduces file size while maintaining readability
- **Thumbnail Generation**: Optional lightweight preview variants
- **Concurrent Processing**: Multi-threaded rendering for performance
- **Idempotent Operation**: Safe to re-run (skips existing files)
- **Restart Support**: Resume from specific book_id after failures
- **Partial Book Cleanup**: Automatically clean incomplete renderings
- **Comprehensive Logging**: Detailed progress and error reporting
- **Flexible Configuration**: Environment variables + CLI overrides

## Requirements

- Python 3.10+
- PostgreSQL database with the schema from `database_design/pure_bhakti_vault_schema.sql`
- PDF files accessible in the configured folder

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your actual paths and database credentials
```

3. Verify database connection and content:
```bash
# Test that your content table has data
psql -d pure_bhakti_vault -c "SELECT count(*) FROM content;"
```

## Configuration

### Environment Variables (.env)

```bash
# Required Paths
PDF_FOLDER=/path/to/your/pdf/files/
PAGE_FOLDER=/path/to/output/page/images/

# Required Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pure_bhakti_vault
DB_USER=your_db_user
DB_PASSWORD=your_db_password

# Optional Rendering Settings (CLI flags override these)
RENDER_DPI=150
RENDER_FORMAT=webp
RENDER_GRAYSCALE=true
CREATE_THUMBNAILS=false

# Restart Configuration (Optional)
# RESTART_BOOK_ID=79  # Skip to this book_id and higher
# CLEANUP_PARTIAL=true  # Clean up partially rendered books
```

### CLI Options

All environment settings can be overridden via command line:

```bash
./render_pdf_pages.py --dpi 200 --format png --color --thumbnails --workers 8
```

## Usage

### Basic Usage

```bash
# Use default settings from .env
./render_pdf_pages.py

# Verbose logging
./render_pdf_pages.py -v
```

### Advanced Usage

```bash
# High-quality color images with thumbnails
./render_pdf_pages.py --dpi 300 --color --thumbnails --workers 6

# Fast grayscale rendering with custom thumbnail size
./render_pdf_pages.py --dpi 150 --grayscale --thumbnails --thumb-width 250 --thumb-height 350

# PNG fallback for systems without WebP support
./render_pdf_pages.py --format png --dpi 200
```

### Restart and Recovery

```bash
# Resume from book_id 79 after a failure
./render_pdf_pages.py --restart-book-id 79

# Clean up partial books and restart from book 79
./render_pdf_pages.py --restart-book-id 79 --cleanup

# Use .env configuration for persistent restart
echo "RESTART_BOOK_ID=79" >> .env
echo "CLEANUP_PARTIAL=true" >> .env
./render_pdf_pages.py
```

## Output Structure

Images are organized by book ID:

```
{PAGE_FOLDER}/
├── 1/                  # book_id = 1
│   ├── 1.webp         # page 1 full-size
│   ├── 1_thumb.webp   # page 1 thumbnail (if enabled)
│   ├── 2.webp         # page 2 full-size
│   └── 2_thumb.webp   # page 2 thumbnail (if enabled)
├── 2/                  # book_id = 2
│   ├── 1.webp
│   └── 2.webp
└── pdf_render.log     # Detailed log file
```

## Performance Considerations

- **DPI Settings**:
  - 150 DPI: Good balance of quality/size (recommended for web)
  - 200 DPI: Higher quality for detailed text
  - 300+ DPI: Print quality (large files)

- **Concurrent Workers**:
  - Default: 4 workers
  - CPU-bound task: set to number of CPU cores
  - I/O-limited: can use more workers than cores

- **Image Formats**:
  - WebP: ~30% smaller files, excellent browser support
  - PNG: Universal compatibility, larger files

## Database Schema

The script expects this PostgreSQL schema structure:

```sql
-- Required tables
CREATE TABLE book (
    book_id SERIAL PRIMARY KEY,
    pdf_name VARCHAR(255) NOT NULL UNIQUE,
    -- ... other columns
);

CREATE TABLE content (
    content_id SERIAL PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES book(book_id),
    page_number INTEGER NOT NULL,
    page_content TEXT,
    -- ... other columns
);
```

## Error Handling

The script handles various error conditions:

- Missing PDF files (logged, skipped)
- Invalid page numbers (logged, skipped)
- Database connection issues (fatal error)
- Insufficient disk space (logged per file)
- WebP support detection (auto-fallback to PNG)

## Logging

Two levels of logging available:

- **Standard**: Progress bars and summary statistics
- **Verbose** (`-v`): Detailed file-by-file operations

Log file `pdf_render.log` contains complete execution history.

## Restart and Recovery

The script includes robust restart capabilities for handling failures:

### When to Use Restart
- **Process Crashed**: Script terminated unexpectedly
- **Disk Full**: Ran out of storage space mid-rendering
- **Memory Issues**: System ran out of memory on large PDFs
- **Network Issues**: Database connection interrupted

### Restart Options

1. **CLI Restart**:
   ```bash
   # Resume from book 79
   ./render_pdf_pages.py --restart-book-id 79
   ```

2. **Environment Restart**:
   ```bash
   # Set in .env for persistent configuration
   echo "RESTART_BOOK_ID=79" >> .env
   ./render_pdf_pages.py
   ```

3. **Automatic Suggestions**:
   - Script shows next restart point when failures occur
   - Displays book range processed for easy restart configuration

### Partial Book Cleanup

**Problem**: Books that were partially rendered (some pages missing)
**Solution**: Enable cleanup to remove incomplete book folders

```bash
# Clean up partial books before restart
./render_pdf_pages.py --restart-book-id 79 --cleanup
```

**How it works**:
- Scans existing book folders
- Compares actual page count vs expected (from database)
- Removes folders with 0 < actual < expected pages
- Logs which books were cleaned up

### Recovery Strategy

1. **Check the logs**: Review `pdf_render.log` for last successful book
2. **Set restart point**: Use `--restart-book-id` with last successful book + 1
3. **Enable cleanup**: Use `--cleanup` to remove partial books
4. **Monitor progress**: Watch for repeated failures on same books

## Troubleshooting

### Common Issues

1. **"PDF not found" errors**:
   - Verify `PDF_FOLDER` path in `.env`
   - Check that `book.pdf_name` matches actual file names

2. **Database connection failed**:
   - Verify database credentials in `.env`
   - Test connection: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

3. **WebP fallback to PNG**:
   - Normal behavior if system lacks WebP support
   - Install/update Pillow with WebP support if needed

4. **Memory issues with large PDFs**:
   - Reduce `--workers` count
   - Lower `--dpi` setting
   - Process books individually

5. **Process failed at book 79 (or any specific book)**:
   ```bash
   # Resume from the failed book
   ./render_pdf_pages.py --restart-book-id 79 --cleanup
   ```

6. **Partial renderings after system crash**:
   ```bash
   # Clean up incomplete books and restart
   ./render_pdf_pages.py --cleanup
   ```

7. **Want to skip completed books**:
   - The script automatically skips existing files (idempotent)
   - Use restart to skip entire book ranges
   - Use cleanup only if books are partially rendered

### Performance Optimization

```bash
# Fast preview generation (low DPI, grayscale)
./render_pdf_pages.py --dpi 100 --grayscale --workers 8

# Production quality (balanced)
./render_pdf_pages.py --dpi 150 --grayscale --thumbnails --workers 4

# High-quality archive (slow but best quality)
./render_pdf_pages.py --dpi 300 --color --format png --workers 2

# Resume failed batch with lower resource usage
./render_pdf_pages.py --restart-book-id 79 --dpi 150 --workers 2
```

## Example Output

```
2024-01-15 10:30:15,123 - INFO - Initialized renderer: DPI=150, format=webp, grayscale=True, thumbnails=False
2024-01-15 10:30:15,456 - INFO - Found 1,250 pages to render
2024-01-15 10:30:15,457 - INFO - Starting to render 1,250 pages using 4 workers
Rendering pages: 100%|████████████████| 1250/1250 [03:45<00:00, 5.54it/s]
2024-01-15 10:34:01,234 - INFO - Rendering complete: 1248/1250 pages successful

=== Rendering Summary ===
Total pages: 1,250
Successful: 1,248
Failed: 2
Success rate: 99.8%
```

## License

This script is designed for the Pure Bhakti Vault project. Modify as needed for your use case.