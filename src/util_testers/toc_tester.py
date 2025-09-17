#!/usr/bin/env python3
"""
TOC Tester - Core Pages Analysis
================================

This script tests the get_core_book_pages functionality across all PDFs in the configured folder.

For each PDF file:
1. Reads PDF_FOLDER from environment variables
2. Gets book_id from book table using PureBhaktiVaultDB
3. Calculates core pages (start to before appendix/index/glossary)
4. Prints results in a formatted table

Usage:
    python toc_tester.py

Requirements:
    - PDF_FOLDER environment variable set
    - Database configured in PureBhaktiVaultDB
    - TOC data populated in table_of_contents
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Environment variable loading
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not available, using existing environment variables")

from toc_utils import PureBhaktiVaultTOC
from pure_bhakti_vault_db import PureBhaktiVaultDB

# Configure logging to be less verbose for this utility
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format="%(asctime)s [%(levelname)s] %(message)s"
)


class TOCTester:
    """Test utility for analyzing core pages across all PDFs in a folder."""
    
    def __init__(self, pdf_folder: str):
        self.pdf_folder = Path(pdf_folder)
        self.db = PureBhaktiVaultDB()
        self.toc = PureBhaktiVaultTOC()
        
        if not self.pdf_folder.exists():
            raise FileNotFoundError(f"PDF folder not found: {self.pdf_folder}")
    
    def get_pdf_to_book_mapping(self) -> Dict[str, int]:
        """
        Get mapping of PDF filenames to book IDs from the database.
        
        Returns:
            Dict mapping PDF filename to book_id
        """
        mapping = {}
        
        # Get all PDF files in the folder
        pdf_files = sorted(self.pdf_folder.glob("*.pdf"))
        
        for pdf_file in pdf_files:
            pdf_name = pdf_file.name
            
            # Try to get book_id using the database method
            book_id = self.db.get_book_id_by_pdf_name(pdf_name)
            
            # If not found, try with stem (filename without extension)
            if book_id is None:
                stem = pdf_file.stem
                book_id = self.db.get_book_id_by_pdf_name(stem)
            
            if book_id:
                mapping[pdf_name] = book_id
            else:
                print(f"⚠️  Warning: No book_id found for PDF: {pdf_name}")
        
        return mapping
    
    def test_core_pages_for_all_books(self) -> List[Tuple[str, int, Optional[int], Optional[int], str]]:
        """
        Test core pages calculation for all books.
        
        Returns:
            List of tuples: (pdf_name, book_id, core_start, core_end, status)
        """
        pdf_to_book = self.get_pdf_to_book_mapping()
        results = []
        
        print(f"\n🔍 Testing core pages for {len(pdf_to_book)} PDFs...")
        print("=" * 80)
        
        for pdf_name, book_id in pdf_to_book.items():
            try:
                core_start, core_end = self.toc.get_core_book_pages(book_id)
                
                if core_start and core_end:
                    status = f"✅ {core_end - core_start + 1} pages"
                elif core_start:
                    status = f"⚠️  Start only (no appendix found)"
                else:
                    status = "❌ No core pages found"
                
                results.append((pdf_name, book_id, core_start, core_end, status))
                
            except Exception as e:
                status = f"❌ Error: {str(e)[:50]}..."
                results.append((pdf_name, book_id, None, None, status))
        
        return results
    
    def print_results_table(self, results: List[Tuple[str, int, Optional[int], Optional[int], str]]):
        """Print results in a formatted table."""
        
        print(f"\n📊 Core Pages Analysis Results")
        print("=" * 80)
        
        # Print header
        print(f"{'PDF Name':<35} {'Book ID':<8} {'Core Start':<10} {'Core End':<10} {'Status'}")
        print("-" * 80)
        
        # Print results
        total_books = len(results)
        successful_books = 0
        total_core_pages = 0
        
        for pdf_name, book_id, core_start, core_end, status in results:
            # Truncate long PDF names
            display_name = pdf_name[:32] + "..." if len(pdf_name) > 35 else pdf_name
            
            start_str = str(core_start) if core_start else "N/A"
            end_str = str(core_end) if core_end else "N/A"
            
            print(f"{display_name:<35} {book_id:<8} {start_str:<10} {end_str:<10} {status}")
            
            if core_start and core_end:
                successful_books += 1
                total_core_pages += (core_end - core_start + 1)
        
        # Print summary
        print("-" * 80)
        print(f"📈 Summary:")
        print(f"   Total PDFs processed: {total_books}")
        print(f"   Successfully analyzed: {successful_books}")
        print(f"   Total core pages: {total_core_pages:,}")
        
        if successful_books > 0:
            avg_pages = total_core_pages / successful_books
            print(f"   Average core pages per book: {avg_pages:.1f}")
        
        success_rate = (successful_books / total_books) * 100 if total_books > 0 else 0
        print(f"   Success rate: {success_rate:.1f}%")
    
    def run_full_analysis(self):
        """Run the complete core pages analysis."""
        print(f"🚀 Starting TOC Core Pages Analysis")
        print(f"📁 PDF Folder: {self.pdf_folder}")
        
        results = self.test_core_pages_for_all_books()
        self.print_results_table(results)
        
        print(f"\n✅ Analysis complete!")


def main():
    """Main function to run the TOC tester."""
    
    # Get PDF folder from environment
    pdf_folder = os.getenv("PDF_FOLDER")
    if not pdf_folder:
        print("❌ Error: PDF_FOLDER environment variable not set")
        print("Please set PDF_FOLDER in your .env file or environment")
        return
    
    print(f"📚 TOC Core Pages Tester")
    print(f"📁 Using PDF folder: {pdf_folder}")
    
    try:
        tester = TOCTester(pdf_folder)
        tester.run_full_analysis()
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()