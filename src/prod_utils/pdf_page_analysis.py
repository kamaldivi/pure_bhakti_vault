#!/usr/bin/env python3
"""
PDF Page Analysis Utility

Utility to analyze PDF pages using PyMuPDF and generate detailed reports about:
1. Number of text blocks per page
2. Text block locations using quadrants
3. Fonts used in each text block

This utility:
1. Reads configuration from .env file (PDF_FOLDER, PROCESS_FOLDER, TEST_PDF_NAMES)
2. Uses PyMuPDF to extract text blocks with metadata
3. Analyzes text block locations using page quadrants
4. Generates tabular output files in the process folder

USAGE:
    python pdf_page_analysis.py                    # Process all PDFs from TEST_PDF_NAMES
    python pdf_page_analysis.py --pdf filename.pdf # Process specific PDF
    python pdf_page_analysis.py --all-pdfs         # Process all PDFs in PDF_FOLDER

ENVIRONMENT VARIABLES:
    PDF_FOLDER: Directory containing PDF files
    PROCESS_FOLDER: Directory for output files
    TEST_PDF_NAMES: Comma-separated list of PDF filenames to process

OUTPUT:
    - CSV file with page-level analysis in PROCESS_FOLDER
    - Columns: pdf_name, page_num, total_blocks, quadrant_1_blocks, quadrant_2_blocks,
              quadrant_3_blocks, quadrant_4_blocks, unique_fonts, font_details
"""

import os
import sys
import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv
import fitz  # PyMuPDF
import json
from datetime import datetime

# Load environment variables
load_dotenv()

class PDFPageAnalyzer:
    """
    Utility to analyze PDF pages using PyMuPDF and generate detailed reports.
    """

    def __init__(self):
        """Initialize the PDF analyzer with environment variables."""
        self.pdf_folder = os.getenv('PDF_FOLDER')
        self.process_folder = os.getenv('PROCESS_FOLDER')
        self.test_pdf_names = os.getenv('TEST_PDF_NAMES', '')

        # Validate required environment variables
        if not self.pdf_folder:
            raise ValueError("PDF_FOLDER environment variable is required")
        if not self.process_folder:
            raise ValueError("PROCESS_FOLDER environment variable is required")

        # Ensure directories exist
        self.pdf_folder = Path(self.pdf_folder)
        self.process_folder = Path(self.process_folder)

        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")
        if not self.process_folder.exists():
            self.process_folder.mkdir(parents=True, exist_ok=True)

    def get_quadrant(self, bbox: Tuple[float, float, float, float], page_width: float, page_height: float) -> int:
        """
        Determine which quadrant a bounding box primarily belongs to.

        Args:
            bbox: Bounding box (x0, y0, x1, y1)
            page_width: Page width
            page_height: Page height

        Returns:
            Quadrant number (1-4):
            1: Top-left, 2: Top-right, 3: Bottom-left, 4: Bottom-right
        """
        x0, y0, x1, y1 = bbox
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2

        mid_x = page_width / 2
        mid_y = page_height / 2

        if center_x < mid_x and center_y < mid_y:
            return 1  # Top-left
        elif center_x >= mid_x and center_y < mid_y:
            return 2  # Top-right
        elif center_x < mid_x and center_y >= mid_y:
            return 3  # Bottom-left
        else:
            return 4  # Bottom-right

    def extract_text_blocks(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """
        Extract text blocks with metadata from a page.

        Args:
            page: PyMuPDF page object

        Returns:
            List of text block dictionaries with bbox, text, and font info
        """
        blocks = []
        text_dict = page.get_text("dict")

        for block in text_dict["blocks"]:
            if "lines" in block:  # Text block
                block_bbox = block["bbox"]
                block_text = ""
                fonts = set()

                for line in block["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"]
                        fonts.add(f"{span['font']}-{span['size']:.1f}")

                blocks.append({
                    "bbox": block_bbox,
                    "text": block_text.strip(),
                    "fonts": list(fonts),
                    "quadrant": self.get_quadrant(block_bbox, page.rect.width, page.rect.height)
                })

        return blocks

    def analyze_page(self, page: fitz.Page, page_num: int) -> Dict[str, Any]:
        """
        Analyze a single page and return statistics.

        Args:
            page: PyMuPDF page object
            page_num: Page number

        Returns:
            Dictionary with page analysis results
        """
        blocks = self.extract_text_blocks(page)

        # Count blocks by quadrant
        quadrant_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        all_fonts = set()

        for block in blocks:
            quadrant_counts[block["quadrant"]] += 1
            all_fonts.update(block["fonts"])

        return {
            "page_num": page_num,
            "total_blocks": len(blocks),
            "quadrant_1_blocks": quadrant_counts[1],
            "quadrant_2_blocks": quadrant_counts[2],
            "quadrant_3_blocks": quadrant_counts[3],
            "quadrant_4_blocks": quadrant_counts[4],
            "unique_fonts": len(all_fonts),
            "font_details": "; ".join(sorted(all_fonts)),
            "blocks_detail": blocks
        }

    def analyze_pdf(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """
        Analyze all pages in a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of page analysis results
        """
        results = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                analysis = self.analyze_page(page, page_num + 1)
                analysis["pdf_name"] = pdf_path.name
                results.append(analysis)

                print(f"Analyzed {pdf_path.name} page {page_num + 1}/{len(doc)}")

            doc.close()

        except Exception as e:
            print(f"Error analyzing {pdf_path}: {e}")

        return results

    def write_results_to_csv(self, results: List[Dict[str, Any]], output_path: Path):
        """
        Write analysis results to CSV file.

        Args:
            results: List of page analysis results
            output_path: Path to output CSV file
        """
        if not results:
            print("No results to write")
            return

        fieldnames = [
            "pdf_name", "page_num", "total_blocks",
            "quadrant_1_blocks", "quadrant_2_blocks",
            "quadrant_3_blocks", "quadrant_4_blocks",
            "unique_fonts", "font_details"
        ]

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                # Create a copy without the blocks_detail for CSV output
                csv_result = {k: v for k, v in result.items() if k != "blocks_detail"}
                writer.writerow(csv_result)

        print(f"Results written to: {output_path}")

    def write_detailed_json(self, results: List[Dict[str, Any]], output_path: Path):
        """
        Write detailed analysis results to JSON file.

        Args:
            results: List of page analysis results
            output_path: Path to output JSON file
        """
        if not results:
            print("No results to write")
            return

        output_data = {
            "analysis_timestamp": datetime.now().isoformat(),
            "total_pages_analyzed": len(results),
            "pages": results
        }

        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(output_data, jsonfile, indent=2, ensure_ascii=False)

        print(f"Detailed results written to: {output_path}")

    def get_pdf_list(self, specific_pdf: Optional[str] = None, all_pdfs: bool = False) -> List[Path]:
        """
        Get list of PDF files to process.

        Args:
            specific_pdf: Specific PDF filename to process
            all_pdfs: Process all PDFs in the folder

        Returns:
            List of PDF file paths
        """
        if specific_pdf:
            pdf_path = self.pdf_folder / specific_pdf
            if pdf_path.exists():
                return [pdf_path]
            else:
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if all_pdfs:
            return list(self.pdf_folder.glob("*.pdf"))

        # Use TEST_PDF_NAMES from environment
        pdf_names = [name.strip() for name in self.test_pdf_names.split(',') if name.strip()]
        pdf_paths = []

        for pdf_name in pdf_names:
            pdf_path = self.pdf_folder / pdf_name
            if pdf_path.exists():
                pdf_paths.append(pdf_path)
            else:
                print(f"Warning: PDF file not found: {pdf_path}")

        return pdf_paths

    def run_analysis(self, specific_pdf: Optional[str] = None, all_pdfs: bool = False):
        """
        Run the complete PDF analysis workflow.

        Args:
            specific_pdf: Specific PDF filename to process
            all_pdfs: Process all PDFs in the folder
        """
        pdf_files = self.get_pdf_list(specific_pdf, all_pdfs)

        if not pdf_files:
            print("No PDF files to process")
            return

        print(f"Processing {len(pdf_files)} PDF file(s)...")

        all_results = []

        for pdf_path in pdf_files:
            print(f"\nAnalyzing: {pdf_path.name}")
            results = self.analyze_pdf(pdf_path)
            all_results.extend(results)

        if all_results:
            # Generate output filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_output = self.process_folder / f"pdf_page_analysis_{timestamp}.csv"
            json_output = self.process_folder / f"pdf_page_analysis_detailed_{timestamp}.json"

            # Write results
            self.write_results_to_csv(all_results, csv_output)
            self.write_detailed_json(all_results, json_output)

            # Print summary
            total_pages = len(all_results)
            total_blocks = sum(r["total_blocks"] for r in all_results)
            unique_pdfs = len(set(r["pdf_name"] for r in all_results))

            print(f"\n=== Analysis Summary ===")
            print(f"PDFs processed: {unique_pdfs}")
            print(f"Total pages analyzed: {total_pages}")
            print(f"Total text blocks found: {total_blocks}")
            print(f"Average blocks per page: {total_blocks/total_pages:.1f}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Analyze PDF pages using PyMuPDF and generate detailed reports"
    )

    parser.add_argument(
        "--pdf",
        help="Specific PDF filename to process"
    )

    parser.add_argument(
        "--all-pdfs",
        action="store_true",
        help="Process all PDFs in PDF_FOLDER"
    )

    args = parser.parse_args()

    try:
        analyzer = PDFPageAnalyzer()
        analyzer.run_analysis(specific_pdf=args.pdf, all_pdfs=args.all_pdfs)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()