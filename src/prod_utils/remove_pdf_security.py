"""
Remove PDF Security Restrictions Utility

Reads all PDF files from SEC_IN_FOLDER and creates new copies without any security
restrictions in SEC_OUT_FOLDER. Uses PyMuPDF to copy all pages to a new PDF with
no encryption or restrictions.

Features:
    - Processes all *.pdf files in SEC_IN_FOLDER
    - Creates unsecured copies in SEC_OUT_FOLDER with same filename
    - Optional page size normalization
    - Progress tracking for large batches

Dependencies:
    pip install PyMuPDF python-dotenv

Usage:
    python remove_pdf_security.py

Environment Variables (.env):
    SEC_IN_FOLDER=/path/to/input/folder/
    SEC_OUT_FOLDER=/path/to/output/folder/
"""

import os
import sys
import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)


def remove_pdf_security(input_pdf_path: str, output_pdf_path: str = None, normalize_size: bool = True) -> str:
    """
    Remove security restrictions from a PDF by copying all pages to a new PDF.
    Optionally normalizes all pages to the same size (largest dimensions found).

    Args:
        input_pdf_path: Path to the input PDF file
        output_pdf_path: Optional path to output PDF. If None, uses input_name_processed.pdf
        normalize_size: If True, makes all pages the same size without truncating content

    Returns:
        Path to the output PDF file
    """
    input_path = Path(input_pdf_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf_path}")

    # Generate output path if not provided
    if output_pdf_path is None:
        output_path = input_path.parent / f"{input_path.stem}_processed.pdf"
    else:
        output_path = Path(output_pdf_path)

    print(f"Reading PDF: {input_path.name}")

    # Open the input PDF
    input_doc = fitz.open(input_pdf_path)

    # Find the maximum page dimensions if normalizing
    max_width = 0
    max_height = 0
    if normalize_size:
        print("Analyzing page sizes...")
        for page_num in range(len(input_doc)):
            page = input_doc[page_num]
            rect = page.rect
            max_width = max(max_width, rect.width)
            max_height = max(max_height, rect.height)
        print(f"  Maximum dimensions found: {max_width:.1f} x {max_height:.1f} points")

    # Create a new PDF without restrictions
    output_doc = fitz.open()

    # Copy all pages to the new document
    print(f"Copying {len(input_doc)} pages...")
    for page_num in range(len(input_doc)):
        # Show progress for large PDFs
        if (page_num + 1) % 50 == 0 or page_num == 0:
            print(f"  Processing page {page_num + 1}/{len(input_doc)}...")

        input_page = input_doc[page_num]

        if normalize_size:
            # Create new page with maximum dimensions
            new_page = output_doc.new_page(width=max_width, height=max_height)

            # Get the original page size
            src_rect = input_page.rect

            # Calculate positioning to center content (or you can align top-left)
            # Using top-left alignment to preserve original layout
            target_rect = fitz.Rect(0, 0, src_rect.width, src_rect.height)

            # Copy the page content to the new page
            new_page.show_pdf_page(target_rect, input_doc, page_num)
        else:
            # Copy the page as-is
            output_doc.insert_pdf(input_doc, from_page=page_num, to_page=page_num)

    # Save the output PDF without encryption
    print(f"Saving to: {output_path.name}")
    output_doc.save(
        str(output_path),
        garbage=4,  # Maximum garbage collection for smaller file size
        deflate=True,  # Compress streams
        encryption=fitz.PDF_ENCRYPT_NONE  # No encryption
    )

    # Close documents
    output_doc.close()
    input_doc.close()

    print(f"✓ Successfully created unrestricted PDF: {output_path}")
    print(f"  Original size: {input_path.stat().st_size:,} bytes")
    print(f"  New size: {output_path.stat().st_size:,} bytes")
    if normalize_size:
        print(f"  All pages normalized to: {max_width:.1f} x {max_height:.1f} points")

    return str(output_path)


def process_all_pdfs(
    input_folder: str,
    output_folder: str,
    normalize_size: bool = True
) -> Dict[str, Any]:
    """
    Process all PDF files in the input folder and create unsecured copies in output folder.

    Args:
        input_folder: Path to folder containing secured PDFs
        output_folder: Path to folder for unsecured PDFs
        normalize_size: If True, normalizes page sizes in each PDF

    Returns:
        dict: Statistics with counts of processed files
    """
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    # Validate input folder
    if not input_path.exists():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    if not input_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {input_folder}")

    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"Output folder: {output_path}")
    print()

    # Find all PDF files
    pdf_files = sorted(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {input_path}")
        return {
            'total_files': 0,
            'successful': 0,
            'errors': 0,
            'details': []
        }

    print(f"Found {len(pdf_files)} PDF file(s) to process")
    print("=" * 70)
    print()

    stats = {
        'total_files': len(pdf_files),
        'successful': 0,
        'errors': 0,
        'details': []
    }

    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"[{idx}/{len(pdf_files)}] Processing: {pdf_file.name}")
        print("-" * 70)

        # Output path with same filename
        output_file = output_path / pdf_file.name

        try:
            remove_pdf_security(
                input_pdf_path=str(pdf_file),
                output_pdf_path=str(output_file),
                normalize_size=normalize_size
            )
            stats['successful'] += 1
            stats['details'].append({
                'file': pdf_file.name,
                'status': 'success',
                'output': str(output_file)
            })

        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {e}")
            stats['errors'] += 1
            stats['details'].append({
                'file': pdf_file.name,
                'status': 'error',
                'message': str(e)
            })

        print()

    return stats


def print_summary(stats: Dict[str, Any]) -> None:
    """Print summary of processing results."""
    print("=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)
    print(f"Total PDF files: {stats['total_files']}")
    print(f"Successfully processed: {stats['successful']}")
    print(f"Errors: {stats['errors']}")
    print("=" * 70)

    if stats['errors'] > 0:
        print("\nFiles with errors:")
        for detail in stats['details']:
            if detail['status'] == 'error':
                print(f"  ❌ {detail['file']}: {detail['message']}")


def main():
    """Main function to process all PDFs from SEC_IN_FOLDER to SEC_OUT_FOLDER."""

    # Get folders from environment
    input_folder = os.getenv("SEC_IN_FOLDER")
    output_folder = os.getenv("SEC_OUT_FOLDER")

    if not input_folder:
        print("❌ Error: SEC_IN_FOLDER not set in .env file")
        print("Please add SEC_IN_FOLDER=/path/to/input/folder/ to your .env file")
        sys.exit(1)

    if not output_folder:
        print("❌ Error: SEC_OUT_FOLDER not set in .env file")
        print("Please add SEC_OUT_FOLDER=/path/to/output/folder/ to your .env file")
        sys.exit(1)

    print("PDF Security Removal Utility")
    print("=" * 70)
    print(f"Input folder:  {input_folder}")
    print(f"Output folder: {output_folder}")
    print("=" * 70)
    print()

    try:
        # Process all PDFs (with page size normalization)
        stats = process_all_pdfs(
            input_folder=input_folder,
            output_folder=output_folder,
            normalize_size=True
        )

        # Print summary
        print_summary(stats)

        if stats['total_files'] > 0 and stats['errors'] == 0:
            print("\n✅ All PDFs processed successfully!")
        elif stats['successful'] > 0:
            print(f"\n⚠️  Processed {stats['successful']} PDFs with {stats['errors']} errors")
        else:
            print("\n❌ No PDFs were processed successfully")

    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"❌ Configuration Error: {e}")
        print("Please check that SEC_IN_FOLDER and SEC_OUT_FOLDER point to valid directories.")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
