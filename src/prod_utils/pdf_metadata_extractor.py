#!/usr/bin/env python3
"""
PDF Metadata Extractor Utility

This script extracts metadata from all PDF files in a specified folder
and outputs the results in JSON format for easy database integration.

Requirements:
    pip install pypdf

Usage:
    python pdf_metadata_extractor.py
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from pypdf import PdfReader

class PDFMetadataExtractor:
    def __init__(self, folder_path: str):
        """
        Initialize the PDF metadata extractor.
        
        Args:
            folder_path (str): Path to the folder containing PDF files
        """
        self.folder_path = Path(folder_path)
        if not self.folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        if not self.folder_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {folder_path}")
    
    def extract_single_pdf_metadata(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from a single PDF file.
        
        Args:
            pdf_path (Path): Path to the PDF file
            
        Returns:
            Dict containing PDF metadata
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PdfReader(file)
                
                # Handle encrypted PDFs
                if reader.is_encrypted:
                    # Try to decrypt with empty password (common for many PDFs)
                    try:
                        reader.decrypt("")
                    except Exception as decrypt_error:
                        return {
                            "file_info": {
                                "filename": pdf_path.name,
                                "filepath": str(pdf_path.absolute()),
                                "extraction_timestamp": datetime.now().isoformat()
                            },
                            "extraction_status": "error",
                            "error_message": f"PDF is encrypted and cannot be decrypted: {str(decrypt_error)}",
                            "pdf_properties": {"is_encrypted": True},
                            "document_metadata": None,
                            "raw_metadata": None
                        }
                
                # Basic file information
                file_stats = pdf_path.stat()
                
                # Extract PDF metadata
                metadata = reader.metadata if reader.metadata else {}
                
                # Prepare structured metadata
                pdf_info = {
                    "file_info": {
                        "filename": pdf_path.name,
                        "filepath": str(pdf_path.absolute()),
                        "file_size_bytes": file_stats.st_size,
                        "file_size_mb": round(file_stats.st_size / (1024 * 1024), 2),
                        "created_date": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                        "modified_date": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                        "extraction_timestamp": datetime.now().isoformat()
                    },
                    "pdf_properties": {
                        "page_count": len(reader.pages),
                        "is_encrypted": reader.is_encrypted
                    },
                    "document_metadata": {
                        "title": self._clean_metadata_value(metadata.get('/Title')),
                        "author": self._clean_metadata_value(metadata.get('/Author')),
                        "subject": self._clean_metadata_value(metadata.get('/Subject')),
                        "creator": self._clean_metadata_value(metadata.get('/Creator')),
                        "producer": self._clean_metadata_value(metadata.get('/Producer')),
                        "creation_date": self._format_pdf_date(metadata.get('/CreationDate')),
                        "modification_date": self._format_pdf_date(metadata.get('/ModDate')),
                        "keywords": self._clean_metadata_value(metadata.get('/Keywords')),
                        "trapped": self._clean_metadata_value(metadata.get('/Trapped'))
                    },
                    "raw_metadata": {str(k): str(v) for k, v in metadata.items()} if metadata else {},
                    "extraction_status": "success",
                    "error_message": None
                }
                
                return pdf_info
                
        except Exception as e:
            return {
                "file_info": {
                    "filename": pdf_path.name,
                    "filepath": str(pdf_path.absolute()),
                    "extraction_timestamp": datetime.now().isoformat()
                },
                "extraction_status": "error",
                "error_message": str(e),
                "pdf_properties": None,
                "document_metadata": None,
                "raw_metadata": None
            }
    
    def _clean_metadata_value(self, value: Any) -> Optional[str]:
        """Clean and normalize metadata values."""
        if value is None:
            return None
        
        # Convert to string and strip whitespace
        cleaned = str(value).strip()
        
        # Return None for empty strings
        return cleaned if cleaned else None
    
    def _format_pdf_date(self, date_value: Any) -> Optional[str]:
        """Format PDF date strings to ISO format."""
        if not date_value:
            return None
        
        date_str = str(date_value)
        
        # PDF dates often start with 'D:' followed by YYYYMMDDHHMMSS
        if date_str.startswith('D:'):
            date_str = date_str[2:]
        
        # Try to parse common PDF date formats
        for fmt in ['%Y%m%d%H%M%S', '%Y%m%d%H%M', '%Y%m%d']:
            try:
                parsed_date = datetime.strptime(date_str[:len(fmt.replace('%', ''))], fmt)
                return parsed_date.isoformat()
            except ValueError:
                continue
        
        # If parsing fails, return the original string
        return date_str
    
    def extract_all_metadata(self, include_errors: bool = True) -> List[Dict[str, Any]]:
        """
        Extract metadata from all PDF files in the folder.
        
        Args:
            include_errors (bool): Whether to include files that had extraction errors
            
        Returns:
            List of dictionaries containing metadata for each PDF
        """
        pdf_files = list(self.folder_path.glob("*.pdf"))
        
        if not pdf_files:
            print(f"No PDF files found in: {self.folder_path}")
            return []
        
        print(f"Found {len(pdf_files)} PDF files. Extracting metadata...")
        
        results = []
        for pdf_file in pdf_files:
            print(f"Processing: {pdf_file.name}")
            metadata = self.extract_single_pdf_metadata(pdf_file)
            
            if include_errors or metadata["extraction_status"] == "success":
                results.append(metadata)
        
        return results
    
    def save_to_json(self, output_file: str, include_errors: bool = True, indent: int = 2) -> None:
        """
        Extract metadata and save to JSON file.
        
        Args:
            output_file (str): Path to output JSON file
            include_errors (bool): Whether to include files with extraction errors
            indent (int): JSON formatting indentation
        """
        metadata_list = self.extract_all_metadata(include_errors)
        
        # Create summary statistics
        summary = {
            "extraction_summary": {
                "total_files_processed": len(metadata_list),
                "successful_extractions": len([m for m in metadata_list if m["extraction_status"] == "success"]),
                "failed_extractions": len([m for m in metadata_list if m["extraction_status"] == "error"]),
                "extraction_date": datetime.now().isoformat(),
                "source_folder": str(self.folder_path.absolute())
            },
            "pdf_metadata": metadata_list
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=indent, ensure_ascii=False)
        
        print(f"\nMetadata saved to: {output_file}")
        print(f"Successfully processed: {summary['extraction_summary']['successful_extractions']} files")
        if summary['extraction_summary']['failed_extractions'] > 0:
            print(f"Failed to process: {summary['extraction_summary']['failed_extractions']} files")

def main():
    """Main function with configuration options."""
    
    # Configuration - modify these paths as needed
    PDF_FOLDER_PATH = "/Users/kamaldivi/Development/pbb_books"  # Path from src/utils to data/input
    OUTPUT_JSON_FILE = "data/output/pdf_metadata_export.json"  # Path to data/output
    
    try:
        # Create extractor instance
        extractor = PDFMetadataExtractor(PDF_FOLDER_PATH)
        
        # Extract and save metadata
        extractor.save_to_json(OUTPUT_JSON_FILE, include_errors=True)
        
        print(f"\n✅ Extraction completed successfully!")
        print(f"📁 Source folder: {PDF_FOLDER_PATH}")
        print(f"📄 Output file: {OUTPUT_JSON_FILE}")
        
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"❌ Configuration Error: {e}")
        print(f"Please update PDF_FOLDER_PATH in the script to point to your PDF folder.")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()