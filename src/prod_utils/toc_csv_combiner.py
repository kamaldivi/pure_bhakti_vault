#!/usr/bin/env python3
"""
TOC CSV Combiner Utility

Processes a multi-book TOC CSV file and combines level 2 entries that have no page_label
with their parent level 1 entries within the same book.

Features:
    - Finds toc_level=2 rows with empty/NULL page_label
    - Combines them with the most recent toc_level=1 row for the same book_id
    - Concatenates labels with " - " separator
    - Deletes the combined level 2 rows
    - Only processes within same book_id (no cross-book merging)
    - Reports edge cases and statistics

Input CSV Format:
    Columns: book_id, toc_level, toc_label, page_label

Output:
    Creates a new processed CSV file in the same directory

Dependencies:
    pip install python-dotenv

Usage:
    python toc_csv_combiner.py
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


class TOCCSVCombiner:
    """
    Utility to combine TOC level 2 entries without page labels with their
    parent level 1 entries within the same book.
    """

    def __init__(self, input_csv_path: str):
        """
        Initialize the TOC CSV combiner.

        Args:
            input_csv_path: Path to the input CSV file
        """
        self.input_path = Path(input_csv_path)
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input CSV file not found: {input_csv_path}")

        # Generate output path
        self.output_path = self.input_path.parent / f"{self.input_path.stem}_processed.csv"

        # Statistics
        self.stats = {
            'total_rows': 0,
            'combined_rows': 0,
            'deleted_rows': 0,
            'edge_cases': [],
            'books_processed': set()
        }

    def _is_empty_page_label(self, page_label: Any) -> bool:
        """
        Check if page_label is empty or NULL.

        Args:
            page_label: The page label value to check

        Returns:
            bool: True if empty/NULL, False otherwise
        """
        if page_label is None:
            return True
        if isinstance(page_label, str) and not page_label.strip():
            return True
        return False

    def process_csv(self) -> Dict[str, Any]:
        """
        Process the CSV file and combine appropriate rows.

        Returns:
            dict: Statistics about the processing
        """
        print(f"Reading input CSV: {self.input_path.name}")
        print("=" * 70)

        # Read all rows
        rows = []
        with open(self.input_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            # Validate required columns
            required_cols = ['book_id', 'toc_level', 'toc_label', 'page_label']
            if not all(col in fieldnames for col in required_cols):
                raise ValueError(
                    f"Missing required columns. Found: {fieldnames}, "
                    f"Required: {required_cols}"
                )

            for row in reader:
                rows.append(row)

        self.stats['total_rows'] = len(rows)
        print(f"Read {len(rows)} rows from input CSV\n")

        # Process rows: track level 1 rows by book_id and combine level 2 rows
        processed_rows = []
        rows_to_delete = set()  # Track indices of rows to delete

        # Track the most recent level 1 row index for each book_id
        last_level1_by_book: Dict[int, int] = {}

        for idx, row in enumerate(rows):
            try:
                book_id = int(row['book_id'])
                toc_level = int(row['toc_level'])
                toc_label = row['toc_label'].strip()
                page_label = row.get('page_label', '')

                self.stats['books_processed'].add(book_id)

                # Track level 1 rows
                if toc_level == 1:
                    last_level1_by_book[book_id] = idx

                # Check for level 2 rows with empty page_label
                elif toc_level == 2 and self._is_empty_page_label(page_label):
                    # Find the most recent level 1 row for this book
                    if book_id in last_level1_by_book:
                        level1_idx = last_level1_by_book[book_id]
                        level1_row = rows[level1_idx]

                        # Combine the labels
                        combined_label = f"{level1_row['toc_label'].strip()} - {toc_label}"
                        level1_row['toc_label'] = combined_label

                        # Mark this level 2 row for deletion
                        rows_to_delete.add(idx)
                        self.stats['combined_rows'] += 1

                        print(f"✓ Combined rows for book_id={book_id}:")
                        print(f"    Level 1: '{level1_row['toc_label'][:60]}...'")
                        print(f"    Level 2: '{toc_label[:60]}...'")
                        print(f"    Result:  '{combined_label[:60]}...'\n")
                    else:
                        # Edge case: level 2 with no page_label but no preceding level 1
                        edge_case = {
                            'row_num': idx + 2,  # +2 because idx is 0-based and header is row 1
                            'book_id': book_id,
                            'toc_level': toc_level,
                            'toc_label': toc_label[:50],
                            'reason': 'No preceding level 1 row found for this book'
                        }
                        self.stats['edge_cases'].append(edge_case)
                        print(f"⚠️  Edge case (row {edge_case['row_num']}): "
                              f"book_id={book_id}, level={toc_level}, "
                              f"label='{toc_label[:40]}...' - {edge_case['reason']}\n")

            except (ValueError, KeyError) as e:
                edge_case = {
                    'row_num': idx + 2,
                    'book_id': row.get('book_id', 'unknown'),
                    'error': str(e)
                }
                self.stats['edge_cases'].append(edge_case)
                print(f"⚠️  Error processing row {edge_case['row_num']}: {e}\n")

        # Build final list of rows (excluding deleted ones)
        for idx, row in enumerate(rows):
            if idx not in rows_to_delete:
                processed_rows.append(row)
            else:
                self.stats['deleted_rows'] += 1

        # Write output CSV
        print("=" * 70)
        print(f"Writing output CSV: {self.output_path.name}")
        with open(self.output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed_rows)

        print(f"✓ Wrote {len(processed_rows)} rows to output CSV\n")

        return self.stats

    def print_summary(self):
        """Print summary of processing results."""
        print("=" * 70)
        print("PROCESSING SUMMARY")
        print("=" * 70)
        print(f"Total rows read:        {self.stats['total_rows']}")
        print(f"Rows combined:          {self.stats['combined_rows']}")
        print(f"Rows deleted:           {self.stats['deleted_rows']}")
        print(f"Edge cases encountered: {len(self.stats['edge_cases'])}")
        print(f"Books processed:        {len(self.stats['books_processed'])} "
              f"({', '.join(map(str, sorted(self.stats['books_processed'])))})")
        print(f"\nOutput file:            {self.output_path}")
        print("=" * 70)

        if self.stats['edge_cases']:
            print("\nEdge Cases:")
            for ec in self.stats['edge_cases']:
                print(f"  Row {ec.get('row_num', '?')}: book_id={ec.get('book_id', '?')}")
                if 'reason' in ec:
                    print(f"    Reason: {ec['reason']}")
                if 'error' in ec:
                    print(f"    Error: {ec['error']}")
                if 'toc_label' in ec:
                    print(f"    Label: '{ec['toc_label']}'")
            print()


def main():
    """Main function to run the TOC CSV combiner."""

    # Configuration
    INPUT_CSV = "/Users/kamaldivi/Development/pbb_books/tobe_processed/harmonist_tocs.csv"

    print("TOC CSV Combiner Utility")
    print("=" * 70)
    print(f"Input file: {INPUT_CSV}")
    print("=" * 70)
    print()

    try:
        # Create combiner instance
        combiner = TOCCSVCombiner(input_csv_path=INPUT_CSV)

        # Process the CSV
        stats = combiner.process_csv()

        # Print summary
        combiner.print_summary()

        if stats['combined_rows'] > 0:
            print(f"\n✅ Successfully combined {stats['combined_rows']} TOC entries!")
        else:
            print("\n⚠️  No rows were combined (no level 2 entries without page_label found)")

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Please check that the input file exists.")
        sys.exit(1)

    except ValueError as e:
        print(f"❌ CSV Format Error: {e}")
        print("Please check that the CSV has the required columns: book_id, toc_level, toc_label, page_label")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
