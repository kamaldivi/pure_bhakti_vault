# import fitz  # PyMuPDF
import os

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not available, using default paths")

import fitz  # PyMuPDF
from pathlib import Path
import csv

import re



def export_page_labels():
    pdf_folder = os.getenv('PDF_FOLDER')
    pdf_name = os.getenv('TEST_PDF_NAMES')

    doc = fitz.open(os.path.join(pdf_folder, "Lord-of-Sweetness-1ed-2015.pdf"))

    toc = doc.get_toc()

    print(toc)
    return len(toc) > 0

    

# Example
if __name__ == "__main__":
    labels = export_page_labels()


