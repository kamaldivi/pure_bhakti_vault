#!/usr/bin/env python3
"""
Integrated Page Type Identifier

A comprehensive page classification system that combines multiple detection methods
to accurately categorize all pages in a PDF document.

Dependencies:
    - pure_bhakti_vault_db.py (database utility)
    - sanskrit_utils.py (text processing)
    - PyMuPDF (fitz)
    - python-dotenv

Usage:
    from page_type_identifier import PageTypeIdentifier
    
    classifier = PageTypeIdentifier()
    results = classifier.classify_book_pages(book_id=123)
"""

import os
import re
import fitz  # PyMuPDF
from typing import Dict, List, Tuple, Optional, Any, Set
from enum import Enum
from dataclasses import dataclass
from dotenv import load_dotenv

# Import existing utilities
try:
    from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError
    from sanskrit_utils import fix_iast_glyphs
    from page_content_extractor import PageContentExtractor, ExtractionType
    from toc_utils import PureBhaktiVaultTOC
except ImportError as e:
    print(f"Warning: Could not import required utilities: {e}")
    print("Make sure pure_bhakti_vault_db.py, sanskrit_utils.py, page_content_extractor.py, and toc_utils.py are in your path")
    # Continue without PageContentExtractor for fallback compatibility
    PageContentExtractor = None
    ExtractionType = None
    PureBhaktiVaultTOC = None

load_dotenv()

class PageType(Enum):
    TOC = "Table of Contents"
    GLOSSARY = "Glossary"
    VERSE_INDEX = "Verse Index"
    EMPTY = "Empty"
    PUBLISHER = "Publisher Info"
    PRIMARY = "Primary"
    PREFIX = "Prefix"
    POSTFIX = "Postfix"
    INDEX = "Index"
    APPENDIX = "Appendix"
    IMAGE_PAGE = "Image Page"
    CORE_PAGE = "Core"

@dataclass
class PageClassification:
    """Data structure for page classification results."""
    page_number: int
    page_type: PageType
    confidence: str  # 'high', 'medium', 'low', 'very_low'
    score: float
    reasons: List[str]
    metadata: Dict[str, Any]


class PublisherPageDetector:
    """Detects publisher information pages using heuristic patterns."""
    
    def __init__(self):
        # Regex patterns for publisher detection
        self.url_re = re.compile(r"(?:https?://|www\.)", re.I)
        self.email_re = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
        self.phone_re = re.compile(r"\+?\d[\d\s().-]{6,}")
        self.allcaps_title_re = re.compile(r"^[A-Z][\w'''\-\":;,() ]{2,}$")
        self.short_title_re = re.compile(r"^(?:[A-Z][\w'''\-\"]+(?:[ :][A-Z][\w'''\-\"]+){0,7})$")
        
        # Positive patterns (increase publisher score)
        self.positive_patterns = [
            re.compile(r"©|copyright|creative\s+commons|some\s+rights\s+reserved", re.I),
            re.compile(r"\bISBN\b|\bISSN\b|\bLibrary of Congress Control Number\b|\bBritish Library Cataloguing\b", re.I),
            re.compile(r"Cataloging in Publication Data|CIP\b|D\.K\. Agencies", re.I),
            re.compile(r"First Edition|Second Edition|Third Edition|Fourth Edition|Printed at|Printed by|edition\b|reprint", re.I),
            re.compile(r"Worldwide (Centers|Centres) & Contacts|OUR WEBSITES|our websites|contact\s+us", re.I),
            re.compile(r"\bbooks by\b|\benglish titles published by\b|\btitles published by\b|\bBOOKS BY\b", re.I),
            re.compile(r"Permissions beyond the scope of this license|Attribution-No Derivative Works|creativecommons\.org", re.I),
        ]
        
        # Negative patterns (decrease publisher score)
        self.negative_patterns = [
            re.compile(r"\bContents\b|\bTable of Contents\b|\bChapter\b|\bPreface\b|\bIntroduction\b", re.I)
        ]
        
        self.threshold = 6  # Score threshold for publisher classification
    
    def analyze_text_stats(self, text: str) -> Dict[str, int]:
        """Analyze text for various statistical features."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        words = re.findall(r"\b[\w''']+\b", text)
        numerics = re.findall(r"\b\d+\b", text)
        urls = self.url_re.findall(text)
        emails = self.email_re.findall(text)
        phones = self.phone_re.findall(text)
        
        short_title_like = sum(
            1 for ln in lines if 3 <= len(ln) <= 80 and self.short_title_re.match(ln)
        )
        allcaps_title_like = sum(
            1 for ln in lines if 3 <= len(ln) <= 80 and self.allcaps_title_re.match(ln) and ln.upper() == ln
        )
        
        return {
            "line_count": len(lines),
            "word_count": len(words),
            "numeric_count": len(numerics),
            "url_count": len(urls),
            "email_count": len(emails),
            "phone_count": len(phones),
            "short_title_like": short_title_like,
            "allcaps_title_like": allcaps_title_like,
        }
    
    def score_page(self, text: str) -> Tuple[float, List[str], str]:
        """Score a page for publisher content likelihood."""
        reasons = []
        score = 0.0
        
        # Pattern matches
        for pattern in self.positive_patterns:
            if pattern.search(text):
                score += 3
                reasons.append(f"positive_pattern: {pattern.pattern[:50]}...")
        
        for pattern in self.negative_patterns:
            if pattern.search(text):
                score -= 2
                reasons.append(f"negative_pattern: {pattern.pattern[:50]}...")
        
        stats = self.analyze_text_stats(text)
        word_count = stats["word_count"]
        
        # Contact information density
        if stats["url_count"] >= 3:
            score += 2
            reasons.append("high_url_density")
        if stats["email_count"] >= 1:
            score += 1
            reasons.append("contains_email")
        if stats["phone_count"] >= 3:
            score += 2
            reasons.append("high_phone_density")
        
        # Heavy contact info in low word count suggests publisher page
        if word_count <= 250 and (stats["url_count"] + stats["email_count"] + stats["phone_count"]) >= 5:
            score += 3
            reasons.append("contact_heavy_low_wordcount")
        
        # Numeric density (catalogs, phone lists)
        if stats["numeric_count"] >= 30 and word_count <= 500:
            score += 2
            reasons.append("numeric_heavy")
        
        # Title-list patterns (publisher catalogs)
        if stats["short_title_like"] >= 8:
            score += 2
            reasons.append("many_short_titles")
        if stats["allcaps_title_like"] >= 4:
            score += 1
            reasons.append("many_allcaps_titles")
        
        # License indicators
        if "license" in text.lower() and "creative" in text.lower():
            score += 2
            reasons.append("license_text")
        
        # Near-blank pages (don't auto-classify unless strong positive signals)
        if word_count < 10 and score < 3:
            reasons.append("near_blank_text")
        
        # Determine confidence
        if score >= self.threshold + 3:
            confidence = "high"
        elif score >= self.threshold:
            confidence = "medium"
        elif score >= self.threshold - 2:
            confidence = "low"
        else:
            confidence = "very_low"
        
        return score, reasons, confidence
    
    def is_publisher_page(self, text: str) -> Tuple[bool, float, List[str], str]:
        """Determine if page is a publisher page."""
        score, reasons, confidence = self.score_page(text)
        is_publisher = score >= self.threshold
        return is_publisher, score, reasons, confidence


class ImagePageDetector:
    """Detects image-heavy pages using visual content analysis."""
    
    def __init__(self):
        self.dominant_threshold = 0.90  # 90% coverage for dominant image
        self.significant_threshold = 0.10  # 10% coverage for significant elements
    
    def analyze_page_images(self, page: fitz.Page, content_rect: Optional[fitz.Rect] = None) -> Dict[str, Any]:
        """Analyze images and drawings on a page."""
        if content_rect is None:
            content_rect = page.rect
        
        content_area = content_rect.width * content_rect.height
        if content_area <= 0:
            return self._empty_analysis()
        
        results = {
            'images': [],
            'drawings': [],
            'total_image_coverage': 0.0,
            'total_drawing_coverage': 0.0,
            'largest_image_coverage': 0.0,
            'largest_drawing_coverage': 0.0,
        }
        
        # Analyze images
        try:
            image_list = page.get_images(full=True)
            for i, img in enumerate(image_list):
                try:
                    img_rect = page.get_image_bbox(img)
                    if img_rect:
                        intersection = img_rect & content_rect
                        if intersection and intersection.width > 0 and intersection.height > 0:
                            intersection_area = intersection.width * intersection.height
                            coverage = intersection_area / content_area
                            
                            if coverage >= 0.01:  # Only consider images with >1% coverage
                                results['images'].append({
                                    'index': i + 1,
                                    'bbox': img_rect,
                                    'coverage': coverage
                                })
                                results['total_image_coverage'] += coverage
                                results['largest_image_coverage'] = max(results['largest_image_coverage'], coverage)
                except Exception as e:
                    continue  # Skip problematic images
        except Exception as e:
            pass  # Skip if image analysis fails
        
        # # Analyze drawings
        # try:
        #     drawings = page.get_drawings()
        #     for i, drawing in enumerate(drawings):
        #         try:
        #             if 'rect' in drawing:
        #                 draw_rect = fitz.Rect(drawing['rect'])
        #                 intersection = draw_rect & content_rect
        #                 if intersection and intersection.width > 0 and intersection.height > 0:
        #                     intersection_area = intersection.width * intersection.height
        #                     coverage = intersection_area / content_area
                            
        #                     if coverage >= self.significant_threshold:
        #                         results['drawings'].append({
        #                             'index': i + 1,
        #                             'bbox': draw_rect,
        #                             'coverage': coverage,
        #                             'type': drawing.get('type', 'unknown')
        #                         })
        #                         results['total_drawing_coverage'] += coverage
        #                         results['largest_drawing_coverage'] = max(results['largest_drawing_coverage'], coverage)
        #         except Exception as e:
        #             continue  # Skip problematic drawings
        # except Exception as e:
        #     pass  # Skip if drawing analysis fails
        
        return results
    
    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            'images': [],
            'drawings': [],
            'total_image_coverage': 0.0,
            'total_drawing_coverage': 0.0,
            'largest_image_coverage': 0.0,
            'largest_drawing_coverage': 0.0,
        }
    
    def classify_image_content(self, analysis: Dict[str, Any]) -> Tuple[bool, str, List[str]]:
        """Classify if page is image-heavy based on analysis."""
        reasons = []
        
        # Check for dominant single image
        if (analysis['largest_image_coverage'] >= self.dominant_threshold and 
            len(analysis['images']) <= 2):
            return True, "high", ["dominant_single_image"]
        
        # Check for significant visual content
        total_visual_coverage = analysis['total_image_coverage'] + analysis['total_drawing_coverage']
        
        if total_visual_coverage >= 0.90:  # 90% total coverage
            reasons.extend(["high_visual_coverage", f"total_coverage_{total_visual_coverage:.1%}"])
            return True, "high", reasons
        elif total_visual_coverage >= 0.75:  # 75% total coverage
            reasons.extend(["medium_visual_coverage", f"total_coverage_{total_visual_coverage:.1%}"])
            return True, "medium", reasons
        elif analysis['largest_image_coverage'] >= 0.80:  # Single image >80%
            reasons.extend(["large_single_image", f"largest_{analysis['largest_image_coverage']:.1%}"])
            return True, "high", reasons
        
        return False, "very_low", ["minimal_visual_content"]


class PageTypeIdentifier:
    """
    Integrated page type classification system.
    
    Orchestrates multiple detection methods to comprehensively classify
    all pages in a PDF document based on content and context.
    """
    
    def __init__(self, db_params: Optional[Dict[str, str]] = None):
        """Initialize the page type identifier."""
        self.db = PureBhaktiVaultDB(db_params)
        self.publisher_detector = PublisherPageDetector()
        self.image_detector = ImagePageDetector()
        self.pdf_folder = os.getenv('PDF_FOLDER', '')
        
        # Initialize TOC utility for core page detection
        self.toc_util = None
        if PureBhaktiVaultTOC:
            try:
                self.toc_util = PureBhaktiVaultTOC()
                print("Using PureBhaktiVaultTOC for core page range detection")
            except Exception as e:
                print(f"Warning: Could not initialize PureBhaktiVaultTOC: {e}")
                print("Falling back to legacy page classification")
        
        # Initialize page content extractor if available
        self.page_extractor = None
        if PageContentExtractor:
            try:
                self.page_extractor = PageContentExtractor()
                print("Using PageContentExtractor for precise content area detection")
            except Exception as e:
                print(f"Warning: Could not initialize PageContentExtractor: {e}")
                print("Falling back to basic header/footer calculation")
        
        # Parse skip list for image detection
        self.skip_image_detection = self._parse_skip_list()
    
    def _parse_skip_list(self) -> Set[str]:
        """Parse SKIP_IMAGE_DETECTION environment variable."""
        skip_list_str = os.getenv('SKIP_IMAGE_DETECTION', '')
        if not skip_list_str:
            return set()
        
        # Parse comma-separated PDF names
        skip_list = set()
        for pdf_name in skip_list_str.split(','):
            pdf_name = pdf_name.strip()
            if pdf_name:
                skip_list.add(pdf_name)
        
        if skip_list:
            print(f"Image detection will be skipped for: {', '.join(sorted(skip_list))}")
        
        return skip_list
    
    def get_core_page_range(self, book_id: int) -> Tuple[Optional[int], Optional[int]]:
        """
        Get core page range using TOC-based analysis.
        
        Args:
            book_id: Book identifier
            
        Returns:
            Tuple of (core_start_page, core_end_page) or (None, None) if not available
        """
        if not self.toc_util:
            print(f"ℹ️  TOC utility not available for core page detection")
            return None, None
        
        try:
            core_start, core_end = self.toc_util.get_core_book_pages(book_id)
            if core_start and core_end:
                print(f"📖 Core pages for book {book_id}: {core_start} - {core_end}")
                return core_start, core_end
            else:
                print(f"ℹ️  No core page range found for book {book_id} (no TOC data)")
                return None, None
        except Exception as e:
            print(f"⚠️ Error getting core pages for book {book_id}: {e}")
            return None, None
        
    def get_book_ranges(self, book_id: int) -> Dict[str, Optional[range]]:
        """Get page ranges for special sections from book metadata."""
        try:
            book_info = self.db.get_book_by_id(book_id)
            if not book_info:
                return {'toc': None, 'verse': None, 'glossary': None}
            
            def parse_range(range_obj) -> Optional[range]:
                """Parse PostgreSQL int4range object or string to Python range."""
                if not range_obj:
                    return None
                
                try:
                    # Handle PostgreSQL NumericRange object
                    if hasattr(range_obj, 'lower') and hasattr(range_obj, 'upper'):
                        # This is a psycopg2 NumericRange object
                        start = range_obj.lower if range_obj.lower is not None else 0
                        end = range_obj.upper if range_obj.upper is not None else 0
                        
                        # NumericRange upper bound is typically exclusive
                        # Convert to inclusive Python range
                        if start > 0 and end > start:
                            return range(start, end)  # end is already exclusive in NumericRange
                        return None
                    
                    # Handle string representation like '[1,10)' 
                    range_str = str(range_obj)
                    if not range_str or range_str.lower() == 'none':
                        return None
                    
                    # Remove brackets and split
                    clean_range = range_str.strip('[]()').split(',')
                    if len(clean_range) != 2:
                        return None
                    
                    start = int(clean_range[0].strip())
                    end = int(clean_range[1].strip())
                    
                    # Adjust for inclusive/exclusive bounds if needed
                    if range_str.endswith(')'):
                        # Exclusive end - keep as is for Python range
                        return range(start, end)
                    else:
                        # Inclusive end - add 1 for Python range
                        return range(start, end + 1)
                        
                except (ValueError, AttributeError, TypeError):
                    return None
            
            return {
                'toc': parse_range(book_info.get('toc_pages')),
                'verse': parse_range(book_info.get('verse_pages')),
                'glossary': parse_range(book_info.get('glossary_pages')),
            }
            
        except DatabaseError as e:
            print(f"⚠️ Could not get book ranges: {e}")
            return {'toc': None, 'verse': None, 'glossary': None}
    
    def extract_page_text(self, pdf_path: str, page_num: int, 
                         content_rect: Optional[fitz.Rect] = None) -> str:
        """Extract text from a specific page, optionally from a specific region."""
        try:
            doc = fitz.open(pdf_path)
            page = doc.load_page(page_num - 1)  # Convert to 0-based
            
            if content_rect:
                text = page.get_text("text", clip=content_rect)
            else:
                text = page.get_text("text")
            
            doc.close()
            return fix_iast_glyphs(text.strip())
        except Exception as e:
            print(f"⚠️ Error extracting text from page {page_num}: {e}")
            return ""
    
    def get_content_rect(self, book_info: Dict[str, Any], page: fitz.Page, pdf_name: str, page_num: int) -> fitz.Rect:
        """Calculate content area excluding headers and footers using PageContentExtractor if available."""
        
        page_rect = page.rect
        
        # Try to use PageContentExtractor for precise content area
        if self.page_extractor:
            try:
                # Get the main body content area using PageContentExtractor
                body_content = self.page_extractor.extract_page_content(pdf_name, page_num, ExtractionType.BODY)
                
                # Get book metadata to determine content area coordinates
                book_metadata = self.page_extractor.get_book_metadata(pdf_name)
                if book_metadata and body_content is not None:
                    header_height = float(book_metadata['header_height'] or 0.0)
                    footer_height = float(book_metadata['footer_height'] or 0.0)
                    
                    # Use PageContentExtractor logic: footer_height is Y-coordinate where footer starts
                    content_x0 = page_rect.x0
                    content_y0 = page_rect.y0 + header_height
                    content_x1 = page_rect.x1
                    content_y1 = footer_height  # Footer start coordinate, not height from bottom
                    
                    # Validate rectangle bounds
                    if content_y0 < content_y1 and content_x0 < content_x1:
                        return fitz.Rect(content_x0, content_y0, content_x1, content_y1)
                    else:
                        print(f"Warning: Invalid content rect for {pdf_name} page {page_num} - using fallback")
                        
            except Exception as e:
                print(f"Warning: PageContentExtractor failed for {pdf_name} page {page_num}: {e}")
                print("Falling back to basic calculation")
        
        # Fallback to basic header/footer calculation
        # Treat these as actual heights from edges, not coordinates
        header_height = float(book_info.get('header_height', 0) or 0)
        footer_height = float(book_info.get('footer_height', 0) or 0)
        
        # Check if footer_height looks like a coordinate (large value close to page height)
        if footer_height > page_rect.height * 0.5:
            # Treat as Y-coordinate where footer starts
            content_y1 = footer_height
        else:
            # Treat as height from bottom
            content_y1 = page_rect.y1 - footer_height
        
        content_x0 = page_rect.x0
        content_y0 = page_rect.y0 + header_height
        content_x1 = page_rect.x1
        
        # Ensure valid rectangle
        if content_y0 >= content_y1 or content_x0 >= content_x1:
            print(f"Warning: Invalid fallback content rect for {pdf_name} page {page_num} - using full page")
            return page_rect
        
        return fitz.Rect(content_x0, content_y0, content_x1, content_y1)
    
    def is_empty_page(self, text: str, page: fitz.Page, content_rect: fitz.Rect) -> bool:
        """Determine if a page is effectively empty."""
        
        # Check text content with meaningful threshold
        cleaned_text = text.strip()
        if len(cleaned_text) > 5:  # More than just a few characters/artifacts
            return False
        
        # Allow for very minimal text (page numbers, etc.) but check word count
        words = cleaned_text.split()
        if len(words) > 2:  # More than 2 words suggests real content
            return False
        
        content_area = content_rect.width * content_rect.height
        if content_area <= 0:
            return True  # Invalid content area
        
        return True
    
    def classify_book_pages(self, book_id: int) -> List[PageClassification]:
        """
        Classify all pages in a book using TOC-based core page ranges as the foundation.
        
        New processing order:
        1. Get core page ranges from TOC analysis
        2. Initial assignment: Prefix (before core), Core (within range), Postfix (after core) 
        3. Override with specific detections: TOC, Glossary, Verse Index, Empty, Publisher, Image
        
        If no core ranges available, all pages default to Core and specific detections override.
        """
        
        # Get book information
        try:
            book_info = self.db.get_book_by_id(book_id)
            if not book_info:
                raise ValueError(f"Book with ID {book_id} not found")
            
            pdf_name = book_info['pdf_name']
            total_pages = book_info['number_of_pages']
            pdf_path = os.path.join(self.pdf_folder, pdf_name)
            
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        except Exception as e:
            print(f"❌ Error getting book information: {e}")
            return []
        
        # Step 1: Get core page range from TOC analysis
        print(f"📖 Classifying pages for: {pdf_name} ({total_pages} pages)")
        core_start, core_end = self.get_core_page_range(book_id)
        
        # Get page ranges for special sections (legacy metadata)
        ranges = self.get_book_ranges(book_id)
        toc_range = ranges['toc']
        glossary_range = ranges['glossary']
        verse_range = ranges['verse']
        
        if toc_range:
            print(f"📑 TOC pages (metadata): {toc_range}")
        if glossary_range:
            print(f"📚 Glossary pages (metadata): {glossary_range}")
        if verse_range:
            print(f"📜 Verse index pages (metadata): {verse_range}")
        
        # Initialize results
        results = []
        
        # Step 2: Initial core-based assignment
        print("🔍 Step 1: Core-based initial assignment...")
        
        if core_start and core_end:
            # Use core page ranges for initial classification
            prefix_count = core_start - 1
            core_count = core_end - core_start + 1
            postfix_count = total_pages - core_end
            
            # print(f"   📋 Prefix: pages 1-{core_start-1} ({prefix_count} pages)")
            # print(f"   📖 Core: pages {core_start}-{core_end} ({core_count} pages)")
            # print(f"   📝 Postfix: pages {core_end+1}-{total_pages} ({postfix_count} pages)")
            
            # Assign Prefix pages (before core)
            for page_num in range(1, core_start):
                results.append(PageClassification(
                    page_number=page_num,
                    page_type=PageType.PREFIX,
                    confidence="medium",
                    score=6.0,
                    reasons=["toc_based_prefix"],
                    metadata={'core_start': core_start, 'core_end': core_end}
                ))
            
            # Assign Core pages (within range)
            for page_num in range(core_start, core_end + 1):
                results.append(PageClassification(
                    page_number=page_num,
                    page_type=PageType.CORE_PAGE,
                    confidence="medium", 
                    score=6.0,
                    reasons=["toc_based_core"],
                    metadata={'core_start': core_start, 'core_end': core_end}
                ))
            
            # Assign Postfix pages (after core)
            for page_num in range(core_end + 1, total_pages + 1):
                results.append(PageClassification(
                    page_number=page_num,
                    page_type=PageType.POSTFIX,
                    confidence="medium",
                    score=6.0,
                    reasons=["toc_based_postfix"],
                    metadata={'core_start': core_start, 'core_end': core_end}
                ))
        else:
            # No core ranges available - default all to Core
            print("   ℹ️  No core ranges available, defaulting all pages to Core")
            for page_num in range(1, total_pages + 1):
                results.append(PageClassification(
                    page_number=page_num,
                    page_type=PageType.CORE_PAGE,
                    confidence="low",
                    score=3.0,
                    reasons=["fallback_core_all"],
                    metadata={'reason': 'no_toc_data'}
                ))
        
        # Step 3: Override with specific detections
        # print("🔍 Step 2: Overriding with specific page type detections...")
        
        # Open PDF for content analysis
        doc = fitz.open(pdf_path)
        
        try:
            # Override with known sections from metadata
            override_count = 0
            if toc_range:
                for page_num in toc_range:
                    if 1 <= page_num <= len(results):
                        results[page_num - 1] = PageClassification(
                            page_number=page_num,
                            page_type=PageType.TOC,
                            confidence="high",
                            score=10.0,
                            reasons=["metadata_toc_range"],
                            metadata={'source': 'book_metadata'}
                        )
                        override_count += 1
            
            if glossary_range:
                for page_num in glossary_range:
                    if 1 <= page_num <= len(results):
                        results[page_num - 1] = PageClassification(
                            page_number=page_num,
                            page_type=PageType.GLOSSARY,
                            confidence="high",
                            score=10.0,
                            reasons=["metadata_glossary_range"],
                            metadata={'source': 'book_metadata'}
                        )
                        override_count += 1
            
            if verse_range:
                for page_num in verse_range:
                    if 1 <= page_num <= len(results):
                        results[page_num - 1] = PageClassification(
                            page_number=page_num,
                            page_type=PageType.VERSE_INDEX,
                            confidence="high",
                            score=10.0,
                            reasons=["metadata_verse_range"],
                            metadata={'source': 'book_metadata'}
                        )
                        override_count += 1
            
            print(f"   📋 Overrode {override_count} pages with metadata ranges")
            
            # OPTIMIZED: Single-pass content detection with early exit logic
            print("   🔍 Single-pass detection: Empty → Publisher → Image...")
            empty_count = 0
            publisher_count = 0
            image_count = 0
            skip_images = pdf_name in self.skip_image_detection
            
            for i, classification in enumerate(results):
                page_num = classification.page_number
                page = doc.load_page(page_num - 1)
                content_rect = self.get_content_rect(book_info, page, pdf_name, page_num)
                text = self.extract_page_text(pdf_path, page_num, content_rect)
                
                # 1. EMPTY CHECK (highest priority - skip all other checks if empty)
                if self.is_empty_page(text, page, content_rect):
                    results[i] = PageClassification(
                        page_number=page_num,
                        page_type=PageType.EMPTY,
                        confidence="high",
                        score=9.0,
                        reasons=["no_meaningful_content"],
                        metadata={'text_length': len(text), 'original_type': classification.page_type.value}
                    )
                    empty_count += 1
                    continue  # Skip publisher and image checks for empty pages
                
                # 2. PUBLISHER CHECK (second priority - only if not empty, skip image check if publisher)
                # Only check prefix and postfix pages for publisher content
                is_publisher_candidate = classification.page_type in [PageType.PREFIX, PageType.POSTFIX, PageType.CORE_PAGE]
                
                if is_publisher_candidate:
                    is_publisher, score, reasons, confidence = self.publisher_detector.is_publisher_page(text)
                    
                    if is_publisher and confidence in ['high', 'medium']:
                        results[i] = PageClassification(
                            page_number=page_num,
                            page_type=PageType.PUBLISHER,
                            confidence=confidence,
                            score=score,
                            reasons=reasons + ["publisher_content"],
                            metadata={'text_length': len(text), 'original_type': classification.page_type.value}
                        )
                        publisher_count += 1
                        continue  # Skip image check for publisher pages
                
                # 3. IMAGE CHECK (lowest priority - only for CORE pages not classified as empty or publisher)
                if not skip_images and classification.page_type == PageType.CORE_PAGE:
                    image_analysis = self.image_detector.analyze_page_images(page, content_rect)
                    is_image_heavy, confidence, reasons = self.image_detector.classify_image_content(image_analysis)
                    
                    if is_image_heavy and confidence in ['high', 'medium']:
                        results[i] = PageClassification(
                            page_number=page_num,
                            page_type=PageType.IMAGE_PAGE,
                            confidence=confidence,
                            score=8.0,
                            reasons=reasons + ["image_heavy_content"],
                            metadata={
                                'image_count': len(image_analysis['images']),
                                'drawing_count': len(image_analysis['drawings']),
                                'total_coverage': image_analysis['total_image_coverage'] + image_analysis['total_drawing_coverage'],
                                'original_type': classification.page_type.value
                            }
                        )
                        image_count += 1
            
            print(f"   📄 Found {empty_count} empty pages")
            print(f"   🏢 Found {publisher_count} publisher pages")
            if skip_images:
                print(f"   ⏭️  Skipped image detection for {pdf_name}")
            else:
                print(f"   🖼️ Found {image_count} image-heavy pages")
            
        finally:
            doc.close()
        
        # Sort results by page number
        results.sort(key=lambda x: x.page_number)
        
        # Print summary
        print(f"\n📊 Classification Summary:")
        print(f"{'='*50}")
        type_counts = {}
        for result in results:
            page_type = result.page_type.value
            type_counts[page_type] = type_counts.get(page_type, 0) + 1
        
        for page_type, count in sorted(type_counts.items()):
            print(f"{page_type:20s}: {count:3d} pages")
        print(f"{'='*50}")
        print(f"Total pages processed: {len(results)}")
        
        return results
    
    def get_books_with_only_primary_page_types(self) -> List[int]:
        """Find all book_ids where ALL pages are classified as 'Primary' (need reclassification)."""
        try:
            query = """
                SELECT book_id 
                FROM page_map 
                GROUP BY book_id 
                HAVING COUNT(DISTINCT page_type) = 1 
                   AND MAX(page_type) = 'Primary'
                ORDER BY book_id
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                
                book_ids = [row['book_id'] for row in results]
                print(f"📋 Found {len(book_ids)} books with only 'Primary' page_types: {book_ids}")
                return book_ids
                
        except DatabaseError as e:
            print(f"❌ Error querying books with only Primary page_types: {e}")
            return []
    
    def get_primary_pages_for_book(self, book_id: int) -> List[int]:
        """Get all page_numbers that are currently classified as 'Primary' for a specific book."""
        try:
            query = """
                SELECT page_number 
                FROM page_map 
                WHERE book_id = %s AND page_type = 'Primary'
                ORDER BY page_number
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                results = cursor.fetchall()
                
                page_numbers = [row['page_number'] for row in results]
                return page_numbers
                
        except DatabaseError as e:
            print(f"❌ Error getting Primary pages for book {book_id}: {e}")
            return []
    
    def update_database_page_types(self, book_id: int, classifications: List[PageClassification]) -> bool:
        """Update the database with page type classifications."""
        try:
            # Update page_map table with page types
            updated_count = 0
            for classification in classifications:
                query = """
                    UPDATE page_map 
                    SET page_type = %s 
                    WHERE book_id = %s AND page_number = %s
                """
                params = (classification.page_type.value, book_id, classification.page_number)
                
                with self.db.get_cursor() as cursor:
                    cursor.execute(query, params)
                    if cursor.rowcount > 0:
                        updated_count += 1
            
            print(f"✅ Updated {updated_count} page_type records in database for book {book_id}")
            return True
            
        except DatabaseError as e:
            print(f"❌ Error updating database: {e}")
            return False
    
    def classify_and_update_primary_pages(self) -> None:
        """
        Main method: Find all books with only 'Primary' page_types and properly classify them.
        
        This implements the user's updated requirements:
        1. Get book_ids where DISTINCT page_type = 'Primary' (all pages are just Primary)
        2. For each book, identify correct page_type for each page_number  
        3. Update page_map with the assessed page_type
        """
        print("🚀 Starting Primary page_type reclassification and update process...")
        print("=" * 70)
        
        # Step 1: Find books with only 'Primary' page_types
        book_ids = self.get_books_with_only_primary_page_types()
        
        if not book_ids:
            print("✅ No books found with only 'Primary' page_types. All pages are properly classified!")
            return
        
        total_books = len(book_ids)
        total_pages_updated = 0
        successful_books = 0
        
        # Step 2: Process each book
        for i, book_id in enumerate(book_ids, 1):
            print(f"\n📖 Processing book {i}/{total_books}: Book ID {book_id}")
            print("-" * 50)
            
            try:
                # Get pages that need reclassification (currently 'Primary')
                primary_pages = self.get_primary_pages_for_book(book_id)
                print(f"   Found {len(primary_pages)} pages currently classified as 'Primary'")
                
                if not primary_pages:
                    print("   No Primary pages found for this book (may have been processed)")
                    continue
                
                # Step 3: Classify all pages for this book
                classifications = self.classify_book_pages(book_id)
                
                if not classifications:
                    print(f"   ❌ Failed to classify pages for book {book_id}")
                    continue
                
                # Filter classifications to only pages that were Primary and have changed
                changed_classifications = [
                    c for c in classifications 
                    if c.page_number in primary_pages and c.page_type.value != 'Primary'
                ]
                
                print(f"   Found {len(changed_classifications)} pages that need reclassification")
                
                if not changed_classifications:
                    print(f"   ℹ️  All pages remain as Primary (no reclassification needed)")
                    successful_books += 1  # Still count as success
                    continue
                
                # Step 4: Update database with new classifications
                success = self.update_database_page_types(book_id, changed_classifications)
                
                if success:
                    successful_books += 1
                    total_pages_updated += len(changed_classifications)
                    print(f"   ✅ Successfully reclassified {len(changed_classifications)} pages")
                    
                    # Show breakdown of new classifications
                    type_breakdown = {}
                    for c in changed_classifications:
                        type_name = c.page_type.value
                        type_breakdown[type_name] = type_breakdown.get(type_name, 0) + 1
                    
                    breakdown_str = ', '.join([f"{t}: {count}" for t, count in type_breakdown.items()])
                    print(f"   📊 Breakdown: {breakdown_str}")
                else:
                    print(f"   ❌ Failed to update database for book {book_id}")
                    
            except Exception as e:
                print(f"   ❌ Error processing book {book_id}: {e}")
                continue
        
        # Final summary
        print(f"\n🎉 Primary page_type reclassification complete!")
        print("=" * 70)
        print(f"📊 Summary:")
        print(f"   • Books processed: {successful_books}/{total_books}")
        print(f"   • Total pages reclassified: {total_pages_updated}")
        print(f"   • Success rate: {(successful_books/total_books)*100:.1f}%")
        
        if successful_books < total_books:
            failed_books = total_books - successful_books
            print(f"   • Failed books: {failed_books}")
            print(f"   ⚠️  Check logs above for specific error details")
        
        print("=" * 70)
    
    def export_classification_results(self, classifications: List[PageClassification], 
                                    output_path: str) -> bool:
        """Export classification results to CSV file."""
        try:
            import csv
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['page_number', 'page_type', 'confidence', 'score', 'reasons', 'metadata']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for classification in classifications:
                    writer.writerow({
                        'page_number': classification.page_number,
                        'page_type': classification.page_type.value,
                        'confidence': classification.confidence,
                        'score': classification.score,
                        'reasons': '; '.join(classification.reasons),
                        'metadata': str(classification.metadata)
                    })
            
            print(f"✅ Exported classification results to {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error exporting results: {e}")
            return False


def main():
    """
    Main function: Process all books with only 'Primary' page_types and properly classify them.
    
    This implements the user's updated requirements:
    - Find all books where DISTINCT page_type = 'Primary' (all pages are just Primary)
    - Classify page types for each book using comprehensive analysis
    - Update page_map table with assessed page_types
    """
    
    # Initialize the classifier
    classifier = PageTypeIdentifier()
    
    # Test database connection
    if not classifier.db.test_connection():
        print("❌ Failed to connect to database. Check your connection parameters.")
        return
    
    # Check if user wants to process a specific book instead of all NULL books
    specific_book_id = os.getenv('TEST_BOOK_ID')
    
    try:
        if specific_book_id:
            # Single book processing for testing
            book_id = int(specific_book_id)
            print(f"🚀 Testing page classification for specific book ID: {book_id}")
            print("=" * 60)
            
            # Classify all pages
            classifications = classifier.classify_book_pages(book_id)
            
            if not classifications:
                print("❌ No classifications generated. Check book ID and PDF file.")
                return
            
            # Display detailed results
            print(f"\n📋 Detailed Classification Results:")
            print("=" * 80)
            
            current_type = None
            for classification in classifications:
                if classification.page_type != current_type:
                    current_type = classification.page_type
                    print(f"\n🔸 {current_type.value.upper()} PAGES:")
                    print("-" * 40)
                
                reasons_str = ', '.join(classification.reasons[:3])  # Show first 3 reasons
                if len(classification.reasons) > 3:
                    reasons_str += f" (+{len(classification.reasons)-3} more)"
                
                confidence_emoji = {
                    'high': '🟢',
                    'medium': '🟡', 
                    'low': '🟠',
                    'very_low': '🔴'
                }.get(classification.confidence, '⚪')
                
                print(f"  Page {classification.page_number:3d}: {confidence_emoji} {classification.confidence:8s} "
                      f"(score: {classification.score:4.1f}) - {reasons_str}")
            
            # Optional: Update database
            update_db = os.getenv('UPDATE_DATABASE', 'false').lower() == 'true'
            if update_db:
                print(f"\n💾 Updating database...")
                success = classifier.update_database_page_types(book_id, classifications)
                if success:
                    print("✅ Database updated successfully")
                else:
                    print("❌ Database update failed")
            
            # Optional: Export to CSV
            export_path = os.getenv('EXPORT_PATH')
            if export_path:
                print(f"\n📄 Exporting results to: {export_path}")
                success = classifier.export_classification_results(classifications, export_path)
                if success:
                    print("✅ Results exported successfully")
                else:
                    print("❌ Export failed")
            
            print(f"\n🎉 Classification complete! Processed {len(classifications)} pages.")
            
        else:
            # Default behavior: Process all books with only 'Primary' page_types
            print("🚀 Processing ALL books with only 'Primary' page_types...")
            classifier.classify_and_update_primary_pages()
        
    except Exception as e:
        print(f"❌ Error during classification: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()