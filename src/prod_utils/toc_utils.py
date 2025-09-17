"""
Pure Bhakti Vault Table of Contents Utility

A comprehensive utility for managing Table of Contents operations in the Pure Bhakti Vault system.
Handles hierarchical TOC structures, page label resolution, and page range calculations.

Dependencies:
    pip install psycopg2-binary python-dotenv

Usage:
    from toc_utility import PureBhaktiVaultTOC
    
    toc = PureBhaktiVaultTOC()
    chapters = toc.get_level_1_items(book_id=1)
    chapter = toc.get_item_by_label(book_id=1, label="Chapter 3")
    appendices = toc.get_page_ranges_fuzzy(book_id=1, patterns=["appendix", "index"])
"""

import logging
from typing import Optional, Dict, List, Any, Tuple
from pure_bhakti_vault_db import PureBhaktiVaultDB


class TOCError(Exception):
    """Custom exception for TOC-related errors"""
    pass


class PureBhaktiVaultTOC:
    """
    Table of Contents utility for Pure Bhakti Vault system.
    
    Provides comprehensive TOC operations including:
    - Level 1 item retrieval with page computation
    - Item lookup by label with fuzzy matching
    - Page range calculation with label resolution
    - Hierarchical TOC structure handling
    """
    
    def __init__(self, db: PureBhaktiVaultDB = None):
        """
        Initialize the TOC utility.
        
        Args:
            db: Optional PureBhaktiVaultDB instance. Creates new one if None.
        """
        self.db = db or PureBhaktiVaultDB()
        self.logger = self._setup_logger()
        self._page_map_cache = {}  # Cache for page mappings
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the TOC utility."""
        logger = logging.getLogger(f"{__name__}.TOC")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    # =====================================================
    # PAGE LABEL RESOLUTION METHODS
    # =====================================================
    
    def get_page_map_for_book(self, book_id: int, use_cache: bool = True) -> Dict[str, int]:
        """
        Get complete page label to page number mapping for a book.
        
        Args:
            book_id: Book identifier
            use_cache: Whether to use cached mapping if available
            
        Returns:
            Dictionary mapping page labels to page numbers
            
        Example:
            {'i': 1, 'ii': 2, 'iii': 3, '1': 10, '2': 11, ...}
        """
        cache_key = f"book_{book_id}"
        
        if use_cache and cache_key in self._page_map_cache:
            return self._page_map_cache[cache_key]
        
        query = """
            SELECT page_number, page_label, page_type 
            FROM page_map 
            WHERE book_id = %s AND page_label IS NOT NULL
            ORDER BY page_number
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                results = cursor.fetchall()
                
                # Create both directions of mapping
                label_to_number = {}
                number_to_label = {}
                
                for row in results:
                    page_num = row['page_number']
                    page_label = row['page_label'].strip() if row['page_label'] else None
                    
                    if page_label:
                        label_to_number[page_label] = page_num
                        number_to_label[page_num] = page_label
                
                # Cache both mappings
                if use_cache:
                    self._page_map_cache[cache_key] = label_to_number
                    self._page_map_cache[f"book_{book_id}_reverse"] = number_to_label
                
                self.logger.info(f"Loaded {len(label_to_number)} page mappings for book {book_id}")
                return label_to_number
                
        except Exception as e:
            self.logger.error(f"Error loading page map for book {book_id}: {e}")
            raise TOCError(f"Failed to load page map: {e}")
    
    def resolve_page_label_to_number(self, book_id: int, page_label: str) -> Optional[int]:
        """
        Convert page label to physical page number using page_map.
        
        Args:
            book_id: Book identifier
            page_label: Page label (e.g., 'i', '15', 'A-1')
            
        Returns:
            Physical page number if found, None otherwise
            
        Examples:
            resolve_page_label_to_number(1, 'xv') -> 15
            resolve_page_label_to_number(1, '101') -> 125
        """
        if not page_label:
            return None
        
        page_map = self.get_page_map_for_book(book_id)
        page_label = page_label.strip()
        
        # Direct lookup
        if page_label in page_map:
            return page_map[page_label]
        
        # Try case-insensitive lookup
        for label, page_num in page_map.items():
            if label.lower() == page_label.lower():
                return page_num
        
        self.logger.debug(f"Page label '{page_label}' not found in page_map for book {book_id}")
        return None
    
    def resolve_page_number_to_label(self, book_id: int, page_number: int) -> Optional[str]:
        """
        Convert physical page number to page label using page_map.
        
        Args:
            book_id: Book identifier  
            page_number: Physical page number
            
        Returns:
            Page label if found, None otherwise
        """
        cache_key = f"book_{book_id}_reverse"
        
        # Get reverse mapping (create if not cached)
        if cache_key not in self._page_map_cache:
            self.get_page_map_for_book(book_id)  # This populates reverse cache
        
        number_to_label = self._page_map_cache.get(cache_key, {})
        return number_to_label.get(page_number)
    
    # =====================================================
    # PAGE COMPUTATION METHODS  
    # =====================================================
    
    def _find_first_valid_child_page_label(self, book_id: int, parent_toc_id: int, max_depth: int = 3) -> Optional[str]:
        """
        Find the first valid page label from children of a TOC item.
        
        Args:
            book_id: Book identifier
            parent_toc_id: Parent TOC item ID
            max_depth: Maximum recursion depth to prevent infinite loops
            
        Returns:
            First valid page label found, or None
        """
        if max_depth <= 0:
            return None
        
        query = """
            SELECT toc_id, page_label_raw, toc_label
            FROM table_of_contents 
            WHERE book_id = %s AND parent_toc_id = %s 
            ORDER BY toc_id
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id, parent_toc_id))
                children = cursor.fetchall()
                
                for child in children:
                    raw_label = child['page_label_raw']
                    if raw_label and raw_label.strip():
                        # Verify this label exists in page_map
                        if self.resolve_page_label_to_number(book_id, raw_label.strip()):
                            return raw_label.strip()
                    
                    # If child has no valid page label, search its children
                    grandchild_label = self._find_first_valid_child_page_label(
                        book_id, child['toc_id'], max_depth - 1
                    )
                    if grandchild_label:
                        return grandchild_label
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error finding child page label for parent {parent_toc_id}: {e}")
            return None
    
    def _find_next_sibling_page_label(self, book_id: int, toc_item: Dict) -> Optional[str]:
        """
        Find the page label of the next sibling TOC item at the same level.
        
        Args:
            book_id: Book identifier
            toc_item: Current TOC item dictionary
            
        Returns:
            Page label of next sibling, or None if no next sibling
        """
        # Get effective page number for comparison - prioritize effective_start_page if available
        current_page_num = 0
        if toc_item.get('effective_start_page'):
            current_page_num = toc_item['effective_start_page']
        elif toc_item.get('page_label_raw'):
            current_page_num = self.resolve_page_label_to_number(book_id, toc_item['page_label_raw'].strip()) or 0
        
        query = """
            SELECT toc_id, page_label_raw, toc_label, toc_level, parent_toc_id
            FROM table_of_contents 
            WHERE book_id = %s 
              AND toc_level = %s 
              AND COALESCE(parent_toc_id, -1) = COALESCE(%s, -1)
              AND toc_id > %s
            ORDER BY toc_id 
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (
                    book_id,
                    toc_item['toc_level'],
                    toc_item['parent_toc_id'],
                    toc_item['toc_id']
                ))
                siblings = cursor.fetchall()
                
                # Find the first sibling that comes after the current item
                for sibling in siblings:
                    # First try direct page label resolution
                    raw_label = sibling['page_label_raw']
                    if raw_label and raw_label.strip():
                        sibling_page_num = self.resolve_page_label_to_number(book_id, raw_label.strip())
                        if sibling_page_num and sibling_page_num > current_page_num:
                            return raw_label.strip()
                    else:
                        # If no raw label, compute effective page for this sibling
                        sibling_dict = dict(sibling)
                        sibling_dict['book_id'] = book_id  # Ensure book_id is present
                        sibling_effective_page, _ = self.compute_effective_page_number(sibling_dict)
                        if sibling_effective_page > current_page_num:
                            # Return the page label corresponding to this effective page
                            effective_label = self.resolve_page_number_to_label(book_id, sibling_effective_page)
                            if effective_label:
                                return effective_label
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error finding next sibling for TOC item {toc_item['toc_id']}: {e}")
            return None
    
    def _find_next_higher_level_page_label(self, book_id: int, toc_item: Dict) -> Optional[str]:
        """
        Find the page label of the next TOC item at a higher level (lower level number).
        
        Args:
            book_id: Book identifier
            toc_item: Current TOC item dictionary
            
        Returns:
            Page label of next higher-level item, or None
        """
        # Get current effective page for comparison
        current_page_num = 0
        if toc_item.get('effective_start_page'):
            current_page_num = toc_item['effective_start_page']
        elif toc_item.get('page_label_raw'):
            current_page_num = self.resolve_page_label_to_number(book_id, toc_item['page_label_raw'].strip()) or 0
        
        query = """
            SELECT page_label_raw
            FROM table_of_contents 
            WHERE book_id = %s 
              AND toc_level < %s 
              AND toc_id > %s
            ORDER BY toc_id
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (
                    book_id,
                    toc_item['toc_level'],
                    toc_item['toc_id']
                ))
                results = cursor.fetchall()
                
                for row in results:
                    raw_label = row['page_label_raw']
                    if raw_label and raw_label.strip():
                        page_num = self.resolve_page_label_to_number(book_id, raw_label.strip())
                        if page_num and page_num > current_page_num:
                            return raw_label.strip()
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error finding next higher level page: {e}")
            return None
    
    def compute_effective_page_number(self, toc_item: Dict) -> Tuple[int, Dict]:
        """
        Compute the effective start page number for a TOC item using page_label_raw.
        
        Args:
            toc_item: TOC item dictionary with page_label_raw
            
        Returns:
            Tuple of (effective_page_number, metadata_dict)
        """
        book_id = toc_item['book_id']
        raw_page_label = toc_item.get('page_label_raw', '').strip()
        
        metadata = {
            'is_computed_start': False,
            'is_label_resolved': False,
            'resolution_method': 'page_label_raw',
            'raw_page_label': raw_page_label,
            'page_label': raw_page_label
        }
        
        # Try to resolve the raw page label directly
        if raw_page_label:
            resolved_page = self.resolve_page_label_to_number(book_id, raw_page_label)
            if resolved_page:
                metadata['is_label_resolved'] = True
                metadata['resolution_method'] = 'page_label_resolved'
                return resolved_page, metadata
            else:
                self.logger.debug(f"Raw page label '{raw_page_label}' not found in page_map for book {book_id}")
        
        # If raw page label is empty or couldn't be resolved, compute from children
        computed_page_label = self._find_first_valid_child_page_label(book_id, toc_item['toc_id'])
        
        if computed_page_label:
            computed_page = self.resolve_page_label_to_number(book_id, computed_page_label)
            if computed_page:
                metadata['is_computed_start'] = True
                metadata['is_label_resolved'] = True
                metadata['resolution_method'] = 'computed_from_children'
                metadata['page_label'] = computed_page_label
                return computed_page, metadata
        
        # No valid computation possible
        self.logger.warning(f"Could not compute effective page for TOC item: {toc_item['toc_label']} (raw_label: '{raw_page_label}')")
        return 0, metadata
    
    def _resolve_toc_item_pages(self, toc_item: Dict, book_total_pages: int = None) -> Dict:
        """
        Resolve both start and end pages for a TOC item with full metadata.
        
        Args:
            toc_item: TOC item dictionary from database
            book_total_pages: Total pages in book (for end page calculation)
            
        Returns:
            Enhanced TOC item dictionary with resolved page information
        """
        # Compute effective start page using page_label_raw
        effective_start_page, start_metadata = self.compute_effective_page_number(toc_item)
        
        # Find end page by looking for next sibling or higher level item
        end_page = None
        end_page_label = None
        
        if effective_start_page > 0:
            # Try to find next sibling page label - create temp item with effective page
            temp_item = dict(toc_item)
            temp_item['effective_start_page'] = effective_start_page
            next_sibling_label = self._find_next_sibling_page_label(toc_item['book_id'], temp_item)
            if next_sibling_label:
                next_sibling_page = self.resolve_page_label_to_number(toc_item['book_id'], next_sibling_label)
                if next_sibling_page and next_sibling_page > effective_start_page:
                    end_page = next_sibling_page - 1
                    end_page_label = self.resolve_page_number_to_label(toc_item['book_id'], end_page)
            
            # If no sibling found, try next higher level item
            if not end_page:
                # Create temporary item with effective start page for comparison
                temp_item = dict(toc_item)
                temp_item['effective_start_page'] = effective_start_page
                
                next_higher_label = self._find_next_higher_level_page_label(toc_item['book_id'], temp_item)
                if next_higher_label:
                    next_higher_page = self.resolve_page_label_to_number(toc_item['book_id'], next_higher_label)
                    if next_higher_page and next_higher_page > effective_start_page:
                        end_page = next_higher_page - 1
                        end_page_label = self.resolve_page_number_to_label(toc_item['book_id'], end_page)
            
            # If still no end page, use book's total pages
            if not end_page and book_total_pages:
                end_page = book_total_pages
                end_page_label = self.resolve_page_number_to_label(toc_item['book_id'], end_page)
        
        # Calculate page count
        page_count = max(0, (end_page or effective_start_page) - effective_start_page + 1) if effective_start_page > 0 else 0
        
        # Build enhanced result
        result = dict(toc_item)
        result.update({
            'effective_start_page': effective_start_page,
            'end_page': end_page,
            'end_page_label': end_page_label,
            'page_count': page_count,
            'physical_page_number': effective_start_page,  # Alias for compatibility
            **start_metadata
        })
        
        return result
    
    # =====================================================
    # MAIN TOC RETRIEVAL METHODS
    # =====================================================
    
    def get_level_1_items(self, book_id: int, compute_missing_pages: bool = True, 
                          resolve_labels: bool = True, include_children: bool = False) -> List[Dict[str, Any]]:
        """
        Get all Level 1 TOC items for a book with computed page ranges.
        
        Args:
            book_id: Book identifier
            compute_missing_pages: Whether to compute pages for items with page_number=0
            resolve_labels: Whether to resolve page labels via page_map
            include_children: Whether to include child items in results
            
        Returns:
            List of Level 1 TOC items with page range information
        """
        base_query = """
            SELECT toc_id, book_id, toc_label, toc_level, page_label_raw, 
                   parent_toc_id, created_at
            FROM table_of_contents 
            WHERE book_id = %s AND parent_toc_id IS NULL
            ORDER BY toc_id
        """
        
        try:
            # Get book info for total pages
            book_info = self.db.get_book_by_id(book_id)
            book_total_pages = book_info['number_of_pages'] if book_info else None
            
            with self.db.get_cursor() as cursor:
                cursor.execute(base_query, (book_id,))
                results = cursor.fetchall()
                
                enhanced_items = []
                for row in results:
                    toc_item = dict(row)
                    
                    if compute_missing_pages or resolve_labels:
                        toc_item = self._resolve_toc_item_pages(toc_item, book_total_pages)
                    
                    if include_children:
                        toc_item['child_items'] = self._get_children_recursive(book_id, toc_item['toc_id'])
                    
                    enhanced_items.append(toc_item)
                
                self.logger.info(f"Retrieved {len(enhanced_items)} Level 1 TOC items for book {book_id}")
                return enhanced_items
                
        except Exception as e:
            self.logger.error(f"Error getting Level 1 TOC items for book {book_id}: {e}")
            raise TOCError(f"Failed to get Level 1 items: {e}")
    
    def get_item_by_label(self, book_id: int, label: str, exact_match: bool = True,
                         resolve_labels: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get a specific TOC item by its label.
        
        Args:
            book_id: Book identifier
            label: TOC label to search for
            exact_match: Whether to use exact matching or fuzzy matching
            resolve_labels: Whether to resolve page labels
            
        Returns:
            TOC item dictionary if found, None otherwise
        """
        if exact_match:
            query = """
                SELECT toc_id, book_id, toc_label, toc_level, page_label_raw, 
                       parent_toc_id, created_at
                FROM table_of_contents 
                WHERE book_id = %s AND toc_label = %s
                ORDER BY toc_level, toc_id
                LIMIT 1
            """
            params = (book_id, label)
        else:
            query = """
                SELECT toc_id, book_id, toc_label, toc_level, page_label_raw, 
                       parent_toc_id, created_at
                FROM table_of_contents 
                WHERE book_id = %s AND toc_label ILIKE %s
                ORDER BY toc_level, toc_id
                LIMIT 1
            """
            params = (book_id, f"%{label}%")
        
        try:
            # Get book info for total pages
            book_info = self.db.get_book_by_id(book_id)
            book_total_pages = book_info['number_of_pages'] if book_info else None
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()
                
                if result:
                    toc_item = dict(result)
                    
                    if resolve_labels:
                        toc_item = self._resolve_toc_item_pages(toc_item, book_total_pages)
                    
                    self.logger.info(f"Found TOC item '{label}' for book {book_id}")
                    return toc_item
                else:
                    self.logger.info(f"TOC item '{label}' not found for book {book_id}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error finding TOC item '{label}' for book {book_id}: {e}")
            raise TOCError(f"Failed to find TOC item: {e}")
    
    def get_page_ranges_fuzzy(self, book_id: int, patterns: List[str],
                             resolve_labels: bool = True, all_levels: bool = True) -> List[Dict[str, Any]]:
        """
        Get TOC items matching fuzzy patterns (e.g., appendix, index, glossary).
        
        Args:
            book_id: Book identifier
            patterns: List of patterns to search for (case-insensitive)
            resolve_labels: Whether to resolve page labels
            all_levels: Whether to search all TOC levels or just Level 1
            
        Returns:
            List of matching TOC items with page ranges
        """
        # Build ILIKE conditions for all patterns
        where_conditions = []
        params = [book_id]
        
        for pattern in patterns:
            where_conditions.append("toc_label ILIKE %s")
            params.append(f"%{pattern}%")
        
        where_clause = " OR ".join(where_conditions)
        level_clause = "" if all_levels else "AND parent_toc_id IS NULL"
        
        query = f"""
            SELECT toc_id, book_id, toc_label, toc_level, page_label_raw, 
                   parent_toc_id, created_at
            FROM table_of_contents 
            WHERE book_id = %s AND ({where_clause}) {level_clause}
            ORDER BY toc_level, toc_id
        """
        
        try:
            # Get book info for total pages
            book_info = self.db.get_book_by_id(book_id)
            book_total_pages = book_info['number_of_pages'] if book_info else None
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                enhanced_items = []
                for row in results:
                    toc_item = dict(row)
                    
                    if resolve_labels:
                        toc_item = self._resolve_toc_item_pages(toc_item, book_total_pages)
                    
                    # Add pattern matching info
                    matched_patterns = []
                    for pattern in patterns:
                        if pattern.lower() in toc_item['toc_label'].lower():
                            matched_patterns.append(pattern)
                    
                    toc_item['matched_patterns'] = matched_patterns
                    enhanced_items.append(toc_item)
                
                self.logger.info(f"Found {len(enhanced_items)} TOC items matching patterns {patterns} for book {book_id}")
                return enhanced_items
                
        except Exception as e:
            self.logger.error(f"Error searching TOC patterns {patterns} for book {book_id}: {e}")
            raise TOCError(f"Failed to search TOC patterns: {e}")
    
    def _get_children_recursive(self, book_id: int, parent_toc_id: int, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Get all children of a TOC item recursively.
        
        Args:
            book_id: Book identifier
            parent_toc_id: Parent TOC ID
            max_depth: Maximum recursion depth
            
        Returns:
            List of child TOC items with their children
        """
        if max_depth <= 0:
            return []
        
        query = """
            SELECT toc_id, book_id, toc_label, toc_level, page_label_raw, 
                   parent_toc_id, created_at
            FROM table_of_contents 
            WHERE book_id = %s AND parent_toc_id = %s
            ORDER BY toc_id
        """
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id, parent_toc_id))
                results = cursor.fetchall()
                
                children = []
                for row in results:
                    child = dict(row)
                    # Recursively get grandchildren
                    child['child_items'] = self._get_children_recursive(
                        book_id, child['toc_id'], max_depth - 1
                    )
                    children.append(child)
                
                return children
                
        except Exception as e:
            self.logger.error(f"Error getting children for TOC item {parent_toc_id}: {e}")
            return []
    
    # =====================================================
    # UTILITY AND HELPER METHODS
    # =====================================================
    
    def get_toc_hierarchy(self, book_id: int, resolve_labels: bool = True) -> List[Dict[str, Any]]:
        """
        Get complete TOC hierarchy for a book.
        
        Args:
            book_id: Book identifier
            resolve_labels: Whether to resolve page labels
            
        Returns:
            Hierarchical list of all TOC items
        """
        level_1_items = self.get_level_1_items(
            book_id, 
            compute_missing_pages=True, 
            resolve_labels=resolve_labels, 
            include_children=True
        )
        
        return level_1_items
    
    def validate_toc_structure(self, book_id: int) -> Dict[str, Any]:
        """
        Validate TOC structure and identify potential issues.
        
        Args:
            book_id: Book identifier
            
        Returns:
            Validation report with issues and statistics
        """
        issues = []
        statistics = {
            'total_items': 0,
            'level_1_items': 0,
            'items_with_zero_pages': 0,
            'items_with_computed_pages': 0,
            'items_with_resolved_labels': 0,
            'orphaned_items': 0
        }
        
        try:
            # Get all TOC items
            query = """
                SELECT toc_id, toc_label, toc_level, page_label_raw, parent_toc_id
                FROM table_of_contents 
                WHERE book_id = %s
                ORDER BY toc_level, toc_id
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                all_items = cursor.fetchall()
                
                statistics['total_items'] = len(all_items)
                
                for item in all_items:
                    # Count by level
                    if item['toc_level'] == 1:
                        statistics['level_1_items'] += 1
                    
                    # Count items with empty page labels
                    raw_label = item['page_label_raw']
                    if not raw_label or not raw_label.strip():
                        statistics['items_with_zero_pages'] += 1
                        
                        # Check if it has valid children
                        first_child_label = self._find_first_valid_child_page_label(book_id, item['toc_id'])
                        if first_child_label:
                            statistics['items_with_computed_pages'] += 1
                        else:
                            issues.append(f"TOC item '{item['toc_label']}' has no page_label_raw and no valid children")
                    else:
                        # Check page label resolution
                        resolved_page = self.resolve_page_label_to_number(book_id, raw_label.strip())
                        if resolved_page:
                            statistics['items_with_resolved_labels'] += 1
                        else:
                            issues.append(f"TOC item '{item['toc_label']}' page label '{raw_label}' not found in page_map")
                    
                    # Check for orphaned items (parent doesn't exist)
                    if item['parent_toc_id']:
                        parent_exists = any(i['toc_id'] == item['parent_toc_id'] for i in all_items)
                        if not parent_exists:
                            statistics['orphaned_items'] += 1
                            issues.append(f"TOC item '{item['toc_label']}' has non-existent parent_toc_id {item['parent_toc_id']}")
                    
                    # Check for orphaned items (parent doesn't exist)
                    if item['parent_toc_id']:
                        parent_exists = any(i['toc_id'] == item['parent_toc_id'] for i in all_items)
                        if not parent_exists:
                            statistics['orphaned_items'] += 1
                            issues.append(f"TOC item '{item['toc_label']}' has non-existent parent_toc_id {item['parent_toc_id']}")
                
                return {
                    'book_id': book_id,
                    'statistics': statistics,
                    'issues': issues,
                    'validation_passed': len(issues) == 0
                }
                
        except Exception as e:
            self.logger.error(f"Error validating TOC structure for book {book_id}: {e}")
            raise TOCError(f"Failed to validate TOC structure: {e}")
    
    def get_core_book_pages(self, book_id: int) -> Tuple[Optional[int], Optional[int]]:
        """
        Get the core content pages of a book (from first TOC item to before appendices).
        
        This method identifies the main content pages by:
        1. Finding the first TOC item with an actual page number (start of core content)
        2. Finding the first appendix/index/glossary/bibliography item (end of core content)
        3. Returning real PDF page numbers (not page labels)
        
        Args:
            book_id: Book identifier
            
        Returns:
            Tuple of (core_start_page, core_end_page) as PDF page numbers, or (None, None) if not found
        """
        try:
            # Get all TOC items ordered by level and ID
            query = """
                SELECT toc_id, toc_label, toc_level, page_label_raw, parent_toc_id
                FROM table_of_contents 
                WHERE book_id = %s
                ORDER BY toc_level, toc_id
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                all_items = cursor.fetchall()
            
            if not all_items:
                self.logger.warning(f"No TOC items found for book {book_id}")
                return None, None
            
            core_start_page = None
            core_end_page = None
            
            # Find the first TOC item with a resolvable page number (core start)
            for item in all_items:
                item_dict = dict(item)
                item_dict['book_id'] = book_id  # Add book_id for compute_effective_page_number
                effective_page, _ = self.compute_effective_page_number(item_dict)
                if effective_page > 0:
                    core_start_page = effective_page
                    self.logger.debug(f"Found core start at page {core_start_page} for item: {item['toc_label']}")
                    break
            
            if not core_start_page:
                self.logger.warning(f"No TOC items with valid page numbers found for book {book_id}")
                return None, None
            
            # Find the first appendix/index/glossary/bibliography item (core end)
            appendix_patterns = [
                'appendix', 'index', 'glossary'
            ]
            
            # Use get_page_ranges_fuzzy to find appendix-type sections
            appendix_sections = self.get_page_ranges_fuzzy(
                book_id, 
                patterns=appendix_patterns,
                resolve_labels=True,
                all_levels=True
            )
            
            # Find the first appendix section that comes after core start
            if appendix_sections:
                # Sort by effective start page to get the earliest appendix
                valid_appendix_sections = [
                    section for section in appendix_sections 
                    if section.get('effective_start_page', 0) > core_start_page
                ]
                
                if valid_appendix_sections:
                    # Sort by effective start page and take the first one
                    earliest_appendix = min(valid_appendix_sections, key=lambda x: x.get('effective_start_page', float('inf')))
                    
                    core_end_page = earliest_appendix['effective_start_page'] - 1
                    matched_patterns = ', '.join(earliest_appendix.get('matched_patterns', ['unknown']))
                    self.logger.debug(f"Found core end at page {core_end_page} (before appendix: {earliest_appendix['toc_label']}, matched: {matched_patterns})")
                    
            # If no appendix found, use the document's last page
            if not core_end_page:
                # Get the total page count from the page map
                page_map = self.get_page_map_for_book(book_id)
                if page_map:
                    # page_map maps labels to numbers, so get the highest page number
                    core_end_page = max(page_map.values())
                    self.logger.debug(f"Used document's last page as core end: {core_end_page}")
            
            self.logger.info(f"Core pages for book {book_id}: {core_start_page} - {core_end_page}")
            return core_start_page, core_end_page
            
        except Exception as e:
            self.logger.error(f"Error finding core pages for book {book_id}: {e}")
            raise TOCError(f"Failed to find core pages: {e}")
    
    def clear_page_map_cache(self, book_id: int = None):
        """
        Clear page map cache for a specific book or all books.
        
        Args:
            book_id: Book ID to clear cache for, or None to clear all
        """
        if book_id:
            cache_keys = [f"book_{book_id}", f"book_{book_id}_reverse"]
            for key in cache_keys:
                self._page_map_cache.pop(key, None)
            self.logger.info(f"Cleared page map cache for book {book_id}")
        else:
            self._page_map_cache.clear()
            self.logger.info("Cleared all page map cache")


# =====================================================
# EXAMPLE USAGE AND TESTING
# =====================================================

def main():
    """Example usage of the PureBhaktiVaultTOC utility."""
    
    # Initialize the TOC utility
    toc = PureBhaktiVaultTOC()
    
    # Test database connection
    if not toc.db.test_connection():
        print("Failed to connect to database. Check your connection parameters.")
        return
    
    try:
        # Example book ID (adjust as needed)
        book_id = 1
        
        print("=== Pure Bhakti Vault TOC Utility Demo ===\n")
        
        # Example 1: Get all Level 1 TOC items
        print("1. Getting Level 1 TOC items...")
        level_1_items = toc.get_level_1_items(book_id)
        
        print(f"Found {len(level_1_items)} Level 1 items:")
        for item in level_1_items[:3]:  # Show first 3
            print(f"  - {item['toc_label']}")
            print(f"    Raw Label: '{item.get('raw_page_label', 'N/A')}'")
            print(f"    Pages: {item.get('effective_start_page', 'N/A')} - {item.get('end_page', 'N/A')}")
            print(f"    Labels: {item.get('page_label', 'N/A')} - {item.get('end_page_label', 'N/A')}")
            print(f"    Resolution: {item.get('resolution_method', 'N/A')}")
            if item.get('is_computed_start'):
                print(f"    Note: Start page computed from children")
            print()
        
        # Example 2: Get specific item by label
        print("2. Finding specific TOC item...")
        chapter_item = toc.get_item_by_label(book_id, "Chapter 1", exact_match=False)
        if chapter_item:
            print(f"Found: {chapter_item['toc_label']}")
            print(f"  Raw Label: '{chapter_item.get('raw_page_label', 'N/A')}'")
            print(f"  Pages: {chapter_item.get('effective_start_page')} - {chapter_item.get('end_page')}")
            print(f"  Resolution: {chapter_item.get('resolution_method')}")
        else:
            print("  No Chapter 1 found, trying 'Introduction'...")
            intro_item = toc.get_item_by_label(book_id, "Introduction", exact_match=False)
            if intro_item:
                print(f"Found: {intro_item['toc_label']}")
                print(f"  Raw Label: '{intro_item.get('raw_page_label', 'N/A')}'")
                print(f"  Pages: {intro_item.get('effective_start_page')} - {intro_item.get('end_page')}")
        print()
        
        # Example 3: Find appendices, indexes, glossaries
        print("3. Finding appendices, indexes, and glossaries...")
        special_sections = toc.get_page_ranges_fuzzy(
            book_id, 
            patterns=["appendix", "index", "glossary", "bibliography"]
        )
        
        if special_sections:
            print(f"Found {len(special_sections)} special sections:")
            for section in special_sections:
                print(f"  - {section['toc_label']}")
                print(f"    Raw Label: '{section.get('raw_page_label', 'N/A')}'")
                print(f"    Pages: {section.get('effective_start_page')} - {section.get('end_page')}")
                print(f"    Matched: {section.get('matched_patterns')}")
                print()
        else:
            print("  No special sections found")
        
        # Example 4: Get page map sample
        print("4. Page map sample...")
        page_map = toc.get_page_map_for_book(book_id)
        if page_map:
            print(f"Page map has {len(page_map)} entries")
            # Show first 5 mappings
            sample_items = list(page_map.items())[:5]
            for label, page_num in sample_items:
                print(f"  '{label}' -> Page {page_num}")
        print()
        
        # Example 5: Validate TOC structure
        print("5. Validating TOC structure...")
        validation = toc.validate_toc_structure(book_id)
        print(f"Validation passed: {validation['validation_passed']}")
        print(f"Statistics: {validation['statistics']}")
        if validation['issues']:
            print("Issues found:")
            for issue in validation['issues'][:3]:  # Show first 3 issues
                print(f"  - {issue}")
        print()
        
        # Example 6: Test page label resolution
        print("6. Testing page label resolution...")
        test_labels = ['i', 'v', '1', '10', 'xv', '25']
        for label in test_labels:
            page_num = toc.resolve_page_label_to_number(book_id, label)
            if page_num:
                reverse_label = toc.resolve_page_number_to_label(book_id, page_num)
                print(f"  Label '{label}' -> Page {page_num} -> Label '{reverse_label}'")
            else:
                print(f"  Label '{label}' not found in page_map")
        
        # Example 7: Get complete hierarchy
        print("\n7. Getting complete TOC hierarchy...")
        hierarchy = toc.get_toc_hierarchy(book_id)
        print(f"Complete hierarchy has {len(hierarchy)} top-level items")
        
        # Show structure of first item with children
        if hierarchy:
            first_item = hierarchy[0]
            print(f"  First item: {first_item['toc_label']}")
            print(f"    Raw Label: '{first_item.get('raw_page_label', 'N/A')}'")
            if first_item.get('child_items'):
                print(f"    Has {len(first_item['child_items'])} children:")
                for child in first_item['child_items'][:2]:  # Show first 2 children
                    print(f"      - {child['toc_label']} (Level {child['toc_level']}) Raw: '{child.get('page_label_raw', 'N/A')}'")
        
        print("\n=== Demo completed successfully! ===")
        
    except TOCError as e:
        print(f"TOC error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()