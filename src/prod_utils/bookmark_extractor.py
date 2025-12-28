#!/usr/bin/env python3
"""
PDF Bookmark Extractor Utility

This script extracts bookmarks (outline/table of contents) from all PDF files
in the TOC_FOLDER specified in .env and creates CSV files with bookmark text
and page references.

Features:
    - Reads PDFs from TOC_FOLDER environment variable (from .env file)
    - Extracts bookmarks/table of contents from each PDF
    - Creates a CSV file for each PDF in TOC_FOLDER/bookmarks/
    - CSV format: Bookmark Text, Page
    - Supports hierarchical bookmarks with indentation
    - Creates empty CSV files for PDFs without bookmarks

Output:
    - Creates TOC_FOLDER/bookmarks/ directory if it doesn't exist
    - Generates {pdf_name}.csv for each PDF file
    - CSV columns: "Bookmark Text", "Page"
    - Hierarchical bookmarks are indented with "  " (2 spaces per level)

Requirements:
    pip install PyMuPDF python-dotenv

Usage:
    # Use TOC_FOLDER from .env:
    python bookmark_extractor.py

    # Specify custom folder:
    python bookmark_extractor.py /path/to/pdf/folder

    # Include hierarchy level column in CSV:
    python bookmark_extractor.py --include-level

Example .env file:
    TOC_FOLDER=/Users/username/Documents/pdfs/

Example output CSV:
    Bookmark Text,Page
    Chapter 1,5
      Section 1.1,6
      Section 1.2,8
    Chapter 2,10
"""

import os
import csv
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
import fitz  # PyMuPDF

class BookmarkExtractor:
    def __init__(self, toc_folder: str):
        """
        Initialize the bookmark extractor.

        Args:
            toc_folder (str): Path to the folder containing PDF files
        """
        self.toc_folder = Path(toc_folder)
        if not self.toc_folder.exists():
            raise FileNotFoundError(f"TOC folder not found: {toc_folder}")
        if not self.toc_folder.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {toc_folder}")

        # Create bookmarks output directory
        self.bookmarks_folder = self.toc_folder / "bookmarks"
        self.bookmarks_folder.mkdir(exist_ok=True)
        print(f"Bookmarks will be saved to: {self.bookmarks_folder}")

    def extract_bookmarks_from_pdf(self, pdf_path: Path) -> Tuple[List[Dict[str, Any]], str]:
        """
        Extract bookmarks from a single PDF file.

        Args:
            pdf_path (Path): Path to the PDF file

        Returns:
            Tuple of (list of bookmark dictionaries, status message)
        """
        try:
            doc = fitz.open(pdf_path)

            # Get the outline (bookmarks/table of contents)
            toc = doc.get_toc(simple=False)

            if not toc:
                doc.close()
                return [], "No bookmarks found"

            bookmarks = []
            for entry in toc:
                # PyMuPDF TOC format: [level, title, page, dest_dict]
                # level: hierarchy level (1 = top level, 2 = sub-level, etc.)
                # title: bookmark text
                # page: page number (1-based)
                # dest_dict: destination dictionary (optional)

                level = entry[0]
                title = entry[1]
                page = entry[2]

                bookmarks.append({
                    'level': level,
                    'title': title.strip() if title else "",
                    'page': page
                })

            doc.close()
            return bookmarks, f"Successfully extracted {len(bookmarks)} bookmarks"

        except Exception as e:
            return [], f"Error: {str(e)}"

    def save_bookmarks_to_csv(self, bookmarks: List[Dict[str, Any]], output_path: Path,
                              include_level: bool = False) -> None:
        """
        Save bookmarks to a CSV file.

        Args:
            bookmarks (List[Dict]): List of bookmark dictionaries
            output_path (Path): Path to the output CSV file
            include_level (bool): Whether to include the hierarchy level column
        """
        if not bookmarks:
            # Create empty CSV with headers
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                if include_level:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Level', 'Bookmark Text', 'Page'])
                else:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Bookmark Text', 'Page'])
            return

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            if include_level:
                writer = csv.writer(csvfile)
                writer.writerow(['Level', 'Bookmark Text', 'Page'])
                for bookmark in bookmarks:
                    writer.writerow([
                        bookmark['level'],
                        bookmark['title'],
                        bookmark['page']
                    ])
            else:
                writer = csv.writer(csvfile)
                writer.writerow(['Bookmark Text', 'Page'])
                for bookmark in bookmarks:
                    # Add indentation based on level for visual hierarchy
                    indent = "  " * (bookmark['level'] - 1)
                    writer.writerow([
                        f"{indent}{bookmark['title']}",
                        bookmark['page']
                    ])

    def process_all_pdfs(self, include_level: bool = False) -> Dict[str, Any]:
        """
        Process all PDF files in the TOC folder and extract their bookmarks.

        Args:
            include_level (bool): Whether to include hierarchy level in CSV output

        Returns:
            Dictionary with processing statistics
        """
        pdf_files = list(self.toc_folder.glob("*.pdf"))

        if not pdf_files:
            print(f"No PDF files found in: {self.toc_folder}")
            return {
                'total_files': 0,
                'successful': 0,
                'with_bookmarks': 0,
                'without_bookmarks': 0,
                'errors': 0
            }

        print(f"Found {len(pdf_files)} PDF files. Extracting bookmarks...\n")

        stats = {
            'total_files': len(pdf_files),
            'successful': 0,
            'with_bookmarks': 0,
            'without_bookmarks': 0,
            'errors': 0,
            'details': []
        }

        for pdf_file in pdf_files:
            print(f"Processing: {pdf_file.name}")

            bookmarks, status_msg = self.extract_bookmarks_from_pdf(pdf_file)

            # Create CSV filename (replace .pdf with .csv)
            csv_filename = pdf_file.stem + '.csv'
            csv_path = self.bookmarks_folder / csv_filename

            if "Error" in status_msg:
                stats['errors'] += 1
                print(f"  ❌ {status_msg}\n")
                stats['details'].append({
                    'file': pdf_file.name,
                    'status': 'error',
                    'message': status_msg
                })
            elif not bookmarks:
                stats['without_bookmarks'] += 1
                stats['successful'] += 1
                print(f"  ⚠️  {status_msg}")
                print(f"  📄 Created empty CSV: {csv_filename}\n")

                # Still create the CSV file (empty with headers)
                self.save_bookmarks_to_csv(bookmarks, csv_path, include_level)

                stats['details'].append({
                    'file': pdf_file.name,
                    'status': 'no_bookmarks',
                    'message': status_msg
                })
            else:
                stats['with_bookmarks'] += 1
                stats['successful'] += 1
                print(f"  ✅ {status_msg}")
                print(f"  📄 Saved to: {csv_filename}\n")

                # Save bookmarks to CSV
                self.save_bookmarks_to_csv(bookmarks, csv_path, include_level)

                stats['details'].append({
                    'file': pdf_file.name,
                    'status': 'success',
                    'message': status_msg,
                    'bookmark_count': len(bookmarks)
                })

        return stats

    def print_summary(self, stats: Dict[str, Any]) -> None:
        """
        Print a summary of the extraction process.

        Args:
            stats (Dict): Statistics dictionary from process_all_pdfs
        """
        print("\n" + "=" * 60)
        print("EXTRACTION SUMMARY")
        print("=" * 60)
        print(f"Total PDF files processed: {stats['total_files']}")
        print(f"Successful: {stats['successful']}")
        print(f"  - With bookmarks: {stats['with_bookmarks']}")
        print(f"  - Without bookmarks: {stats['without_bookmarks']}")
        print(f"Errors: {stats['errors']}")
        print(f"\nOutput folder: {self.bookmarks_folder}")
        print("=" * 60)


def main():
    """Main function that reads configuration from .env and processes PDFs."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Extract bookmarks from PDF files and save to CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use TOC_FOLDER from .env:
  python bookmark_extractor.py

  # Specify custom folder:
  python bookmark_extractor.py /path/to/pdfs

  # Include hierarchy level column:
  python bookmark_extractor.py --include-level
        """
    )
    parser.add_argument(
        'folder',
        nargs='?',
        help='Path to folder containing PDF files (overrides TOC_FOLDER from .env)'
    )
    parser.add_argument(
        '--include-level',
        action='store_true',
        help='Include hierarchy level as a separate column in CSV output'
    )

    args = parser.parse_args()

    # Determine TOC folder: use command-line arg if provided, otherwise use .env
    if args.folder:
        toc_folder = args.folder
        print(f"Using folder from command line: {toc_folder}\n")
    else:
        # Load environment variables from .env file (override=True to override system env vars)
        load_dotenv(override=True)
        toc_folder = os.getenv('TOC_FOLDER')

        if not toc_folder:
            print("❌ Error: TOC_FOLDER not found in .env file")
            print("Please ensure your .env file contains the TOC_FOLDER variable")
            print("Or provide a folder path as a command-line argument")
            sys.exit(1)

        print(f"TOC Folder from .env: {toc_folder}\n")

    try:
        # Create extractor instance
        extractor = BookmarkExtractor(toc_folder)

        # Process all PDFs and extract bookmarks
        stats = extractor.process_all_pdfs(include_level=args.include_level)

        # Print summary
        extractor.print_summary(stats)

        if stats['total_files'] > 0:
            print("\n✅ Bookmark extraction completed!")
        else:
            print("\n⚠️  No PDF files found to process")

    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"❌ Configuration Error: {e}")
        print(f"Please check that the folder path points to a valid directory.")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
