#!/usr/bin/env python3
"""
Utility to copy and rename book thumbnails based on pbb_thumbnail.csv
Reads CSV with book_id and thumbnail filename, copies images to processed folder
"""

import csv
import os
import shutil
from pathlib import Path


def copy_and_rename_thumbnails():
    """Copy thumbnails from CSV to processed folder with book_id as filename"""

    # Define paths
    csv_path = Path("/Users/kamaldivi/Downloads/pbb_thumbnail.csv")
    source_folder = Path("/Users/kamaldivi/Development/pbb_thumbnails")
    processed_folder = source_folder / "processed"

    # Create processed folder if it doesn't exist
    processed_folder.mkdir(exist_ok=True)

    # Track statistics
    copied_count = 0
    missing_count = 0
    error_count = 0

    print(f"Reading CSV from: {csv_path}")
    print(f"Source folder: {source_folder}")
    print(f"Destination folder: {processed_folder}")
    print("-" * 60)

    # Read CSV and process each row
    with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            book_id = row['book_id'].strip()
            thumbnail_name = row['Thumbnail'].strip()

            source_path = source_folder / thumbnail_name
            dest_path = processed_folder / f"{book_id}.jpg"

            try:
                if source_path.exists():
                    shutil.copy2(source_path, dest_path)
                    print(f"✓ Copied: {thumbnail_name} → {book_id}.jpg")
                    copied_count += 1
                else:
                    print(f"✗ Missing: {thumbnail_name} (book_id: {book_id})")
                    missing_count += 1
            except Exception as e:
                print(f"✗ Error copying {thumbnail_name}: {e}")
                error_count += 1

    # Print summary
    print("-" * 60)
    print(f"Summary:")
    print(f"  Copied: {copied_count}")
    print(f"  Missing: {missing_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {copied_count + missing_count + error_count}")


if __name__ == "__main__":
    copy_and_rename_thumbnails()
