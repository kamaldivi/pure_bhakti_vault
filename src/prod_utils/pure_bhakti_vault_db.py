"""
Pure Bhakti Vault Database Utility

A comprehensive database utility class for the Pure Bhakti Vault system.
Provides methods for common database operations that can be used by multiple classes.

Dependencies:
    pip install psycopg2-binary python-dotenv

Usage:
    from pure_bhakti_vault_db import PureBhaktiVaultDB
    
    db = PureBhaktiVaultDB()
    book_id = db.get_book_id_by_pdf_name("bhagavad-gita-4ed-eng.pdf")
"""

import os
import logging
from typing import Optional, Dict, List, Any, Tuple
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import Error as PostgreSQLError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class DatabaseError(Exception):
    """Custom exception for database-related errors"""
    pass


class PureBhaktiVaultDB:
    """
    Database utility class for Pure Bhakti Vault system.
    
    Provides common database operations for books, pages, content, and indexes.
    Designed to be used by multiple classes throughout the application.
    """
    
    def __init__(self, connection_params: Optional[Dict[str, str]] = None):
        """
        Initialize the database utility.
        
        Args:
            connection_params: Optional dict with database connection parameters.
                              If None, uses environment variables.
        """
        self.connection_params = connection_params or self._get_connection_params()
        self.logger = self._setup_logger()
        
    def _get_connection_params(self) -> Dict[str, str]:
        """Get database connection parameters from environment variables."""
        # Check if DATABASE_URL is provided (PostgreSQL connection string format)
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            # If DATABASE_URL is provided, psycopg2 can use it directly
            # But we'll extract components for consistency
            import urllib.parse as urlparse
            try:
                url = urlparse.urlparse(database_url)
                return {
                    'host': url.hostname,
                    'port': str(url.port) if url.port else '5432',
                    'database': url.path[1:],  # Remove leading slash
                    'user': url.username,
                    'password': url.password,
                }
            except Exception as e:
                self.logger.warning(f"Failed to parse DATABASE_URL: {e}, falling back to individual params")
        
        # Fall back to individual environment variables
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'pbb_books'),
            'user': os.getenv('DB_USER', 'pbbdbuser'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the database utility."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        
        Yields:
            psycopg2.connection: Database connection object
            
        Raises:
            DatabaseError: If connection fails
        """
        connection = None
        try:
            connection = psycopg2.connect(**self.connection_params)
            yield connection
        except PostgreSQLError as e:
            self.logger.error(f"Database connection error: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}")
        finally:
            if connection:
                connection.close()
    
    @contextmanager
    def get_cursor(self, dictionary=True):
        """
        Context manager for database cursors.
        
        Args:
            dictionary: If True, returns RealDictCursor for dict-like results
            
        Yields:
            psycopg2.cursor: Database cursor object
        """
        with self.get_connection() as connection:
            cursor_factory = RealDictCursor if dictionary else None
            cursor = connection.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                connection.commit()
            except Exception as e:
                connection.rollback()
                raise e
            finally:
                cursor.close()
    
    # =====================================================
    # BOOK-RELATED METHODS
    # =====================================================
    
    def get_book_id_by_pdf_name(self, pdf_name: str) -> Optional[int]:
        """
        Get book ID by PDF filename.
        
        Args:
            pdf_name: The PDF filename to search for
            
        Returns:
            int: Book ID if found, None otherwise
            
        Raises:
            DatabaseError: If database query fails
        """
        query = "SELECT book_id FROM book WHERE pdf_name = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (pdf_name,))
                result = cursor.fetchone()
                
                if result:
                    book_id = result['book_id']
                    self.logger.info(f"Found book_id {book_id} for PDF: {pdf_name}")
                    return book_id
                else:
                    self.logger.warning(f"No book found for PDF: {pdf_name}")
                    return None
                    
        except PostgreSQLError as e:
            self.logger.error(f"Error getting book ID for {pdf_name}: {e}")
            raise DatabaseError(f"Failed to get book ID: {e}")
    
    def get_book_by_id(self, book_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete book information by book ID.
        
        Args:
            book_id: The book ID to search for
            
        Returns:
            dict: Book information if found, None otherwise
        """
        query = """
            SELECT book_id, pdf_name, original_book_title, english_book_title,
                   edition, number_of_pages, file_size_bytes, original_author,
                   commentary_author, header_height, footer_height,
                   page_label_location, toc_pages, verse_pages, glossary_pages,
                   created_at, updated_at
            FROM book 
            WHERE book_id = %s
        """
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                if result:
                    self.logger.info(f"Found book: {result['original_book_title']}")
                    return dict(result)
                else:
                    self.logger.warning(f"No book found with ID: {book_id}")
                    return None
                    
        except PostgreSQLError as e:
            self.logger.error(f"Error getting book by ID {book_id}: {e}")
            raise DatabaseError(f"Failed to get book: {e}")
    
    def search_books(self, search_term: str, search_fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search books by various fields.
        
        Args:
            search_term: Term to search for
            search_fields: List of fields to search in. 
                          Defaults to ['original_book_title', 'english_book_title', 'original_author']
            
        Returns:
            list: List of matching books
        """
        if search_fields is None:
            search_fields = ['original_book_title', 'english_book_title', 'original_author']
        
        # Build dynamic WHERE clause
        where_conditions = []
        for field in search_fields:
            where_conditions.append(f"{field} ILIKE %s")
        
        where_clause = " OR ".join(where_conditions)
        
        query = f"""
            SELECT book_id, pdf_name, original_book_title, english_book_title,
                   edition, number_of_pages, file_size_bytes, original_author, 
                   commentary_author
            FROM book 
            WHERE {where_clause}
            ORDER BY original_book_title
        """
        
        # Create parameters for each field
        search_pattern = f"%{search_term}%"
        params = [search_pattern] * len(search_fields)
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                books = [dict(row) for row in results]
                self.logger.info(f"Found {len(books)} books matching '{search_term}'")
                return books
                
        except PostgreSQLError as e:
            self.logger.error(f"Error searching books for '{search_term}': {e}")
            raise DatabaseError(f"Failed to search books: {e}")
    
    def get_all_books(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all books with optional limit.
        
        Args:
            limit: Maximum number of books to return
            
        Returns:
            list: List of all books
        """
        query = """
            SELECT book_id, pdf_name, original_book_title, english_book_title,
                   edition, number_of_pages, file_size_bytes, original_author,
                   commentary_author, header_height, footer_height,
                   page_label_location, toc_pages, verse_pages, glossary_pages
            FROM book 
            ORDER BY original_book_title
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                
                books = [dict(row) for row in results]
                self.logger.info(f"Retrieved {len(books)} books")
                return books
                
        except PostgreSQLError as e:
            self.logger.error(f"Error getting all books: {e}")
            raise DatabaseError(f"Failed to get books: {e}")
    
    # =====================================================
    # PAGE AND CONTENT METHODS
    # =====================================================
    
    def get_page_count(self, book_id: int) -> int:
        """
        Get the number of pages for a book.
        
        Args:
            book_id: The book ID
            
        Returns:
            int: Number of pages
        """
        query = "SELECT COUNT(*) as page_count FROM page_map WHERE book_id = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                return result['page_count'] if result else 0
                
        except PostgreSQLError as e:
            self.logger.error(f"Error getting page count for book {book_id}: {e}")
            raise DatabaseError(f"Failed to get page count: {e}")
    
    def get_page_content(self, book_id: int, page_number: int) -> Optional[str]:
        """
        Get content for a specific page.
        
        Args:
            book_id: The book ID
            page_number: The page number
            
        Returns:
            str: Page content if found, None otherwise
        """
        query = """
            SELECT page_content 
            FROM content 
            WHERE book_id = %s AND page_number = %s
        """
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id, page_number))
                result = cursor.fetchone()
                return result['page_content'] if result else None
                
        except PostgreSQLError as e:
            self.logger.error(f"Error getting content for book {book_id}, page {page_number}: {e}")
            raise DatabaseError(f"Failed to get page content: {e}")
    
    # =====================================================
    # SEARCH AND INDEX METHODS
    # =====================================================
    
    def search_content(self, search_term: str, book_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Search for content across pages.
        
        Args:
            search_term: Term to search for
            book_id: Optional book ID to limit search to specific book
            
        Returns:
            list: List of matching content with page information
        """
        base_query = """
            SELECT c.book_id, c.page_number, c.page_content,
                   b.pdf_name, b.original_book_title,
                   pm.page_label, pm.page_type
            FROM content c
            JOIN book b ON c.book_id = b.book_id
            LEFT JOIN page_map pm ON c.book_id = pm.book_id AND c.page_number = pm.page_number
            WHERE c.page_content ILIKE %s
        """
        
        params = [f"%{search_term}%"]
        
        if book_id:
            base_query += " AND c.book_id = %s"
            params.append(book_id)
        
        base_query += " ORDER BY b.original_book_title, c.page_number"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(base_query, params)
                results = cursor.fetchall()
                
                matches = [dict(row) for row in results]
                self.logger.info(f"Found {len(matches)} content matches for '{search_term}'")
                return matches
                
        except PostgreSQLError as e:
            self.logger.error(f"Error searching content for '{search_term}': {e}")
            raise DatabaseError(f"Failed to search content: {e}")
    
    def get_verse_locations(self, verse_name: str, book_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get locations where a verse appears.
        
        Args:
            verse_name: Name of the verse to search for
            book_id: Optional book ID to limit search
            
        Returns:
            list: List of verse locations
        """
        query = """
            SELECT vi.verse_id, vi.book_id, vi.verse_name, vi.page_number,
                   b.pdf_name, b.original_book_title
            FROM verse_index vi
            JOIN book b ON vi.book_id = b.book_id
            WHERE vi.verse_name ILIKE %s
        """
        
        params = [f"%{verse_name}%"]
        
        if book_id:
            query += " AND vi.book_id = %s"
            params.append(book_id)
        
        query += " ORDER BY b.original_book_title, vi.page_number"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                locations = [dict(row) for row in results]
                self.logger.info(f"Found {len(locations)} locations for verse '{verse_name}'")
                return locations
                
        except PostgreSQLError as e:
            self.logger.error(f"Error getting verse locations for '{verse_name}': {e}")
            raise DatabaseError(f"Failed to get verse locations: {e}")
    
    # =====================================================
    # PAGE RANGE METHODS
    # =====================================================
    
    def _parse_page_range(self, range_obj) -> Optional[Tuple[int, int]]:
        """
        Parse PostgreSQL int4range object or string to Python tuple.
        
        Args:
            range_obj: PostgreSQL NumericRange object or string representation
            
        Returns:
            tuple: (start_page, end_page) if valid range, None otherwise
        """
        if not range_obj:
            return None
            
        try:
            # Handle PostgreSQL NumericRange object (check for non-string with lower/upper attributes)
            if (hasattr(range_obj, 'lower') and hasattr(range_obj, 'upper') 
                and not isinstance(range_obj, str) and hasattr(range_obj.lower, '__call__')):
                # This is a psycopg2 NumericRange object
                start_val = range_obj.lower() if callable(range_obj.lower) else range_obj.lower
                end_val = range_obj.upper() if callable(range_obj.upper) else range_obj.upper
                
                if start_val is not None and end_val is not None:
                    # NumericRange upper bound is typically exclusive
                    # Convert to inclusive tuple for consistency
                    if start_val > 0 and end_val > start_val:
                        return (start_val, end_val - 1)  # Make end inclusive
                return None
            
            # Handle string representation like '[1,10)' or '[1,10]'
            range_string = str(range_obj)
            if not range_string or range_string.lower() == 'none':
                return None
            
            # Parse the string format
            clean_parts = range_string.strip('[]()').split(',')
            if len(clean_parts) != 2:
                return None
            
            try:
                start_page = int(clean_parts[0].strip())
                end_page = int(clean_parts[1].strip())
            except (ValueError, TypeError):
                return None
            
            # Adjust for exclusive end bracket
            if range_string.endswith(')'):
                end_page = end_page - 1  # Make end inclusive
            
            if start_page > 0 and end_page >= start_page:
                return (start_page, end_page)
                
        except (ValueError, AttributeError, TypeError) as e:
            self.logger.warning(f"Could not parse range {range_obj}: {e}")
            
        return None
    
    def get_toc_pages(self, book_id: int) -> Optional[Tuple[int, int]]:
        """
        Get table of contents page range for a book.
        
        Args:
            book_id: The book ID
            
        Returns:
            tuple: (start_page, end_page) if TOC pages are defined, None otherwise
        """
        query = "SELECT toc_pages FROM book WHERE book_id = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                if result and result['toc_pages']:
                    return self._parse_page_range(result['toc_pages'])
                
                return None
                
        except (PostgreSQLError, ValueError) as e:
            self.logger.error(f"Error getting TOC pages for book {book_id}: {e}")
            raise DatabaseError(f"Failed to get TOC pages: {e}")
    
    def get_verse_pages(self, book_id: int) -> Optional[Tuple[int, int]]:
        """
        Get verse pages range for a book.
        
        Args:
            book_id: The book ID
            
        Returns:
            tuple: (start_page, end_page) if verse pages are defined, None otherwise
        """
        query = "SELECT verse_pages FROM book WHERE book_id = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                if result and result['verse_pages']:
                    return self._parse_page_range(result['verse_pages'])
                
                return None
                
        except (PostgreSQLError, ValueError) as e:
            self.logger.error(f"Error getting verse pages for book {book_id}: {e}")
            raise DatabaseError(f"Failed to get verse pages: {e}")
    
    def get_glossary_pages(self, book_id: int) -> Optional[Tuple[int, int]]:
        """
        Get glossary pages range for a book.
        
        Args:
            book_id: The book ID
            
        Returns:
            tuple: (start_page, end_page) if glossary pages are defined, None otherwise
        """
        query = "SELECT glossary_pages FROM book WHERE book_id = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                if result and result['glossary_pages']:
                    return self._parse_page_range(result['glossary_pages'])
                
                return None
                
        except (PostgreSQLError, ValueError) as e:
            self.logger.error(f"Error getting glossary pages for book {book_id}: {e}")
            raise DatabaseError(f"Failed to get glossary pages: {e}")
    
    def get_page_label_location(self, book_id: int) -> Optional[str]:
        """
        Get page label location for a book.
        
        Args:
            book_id: The book ID
            
        Returns:
            str: Page label location if defined, None otherwise
        """
        query = "SELECT page_label_location FROM book WHERE book_id = %s"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (book_id,))
                result = cursor.fetchone()
                
                return result['page_label_location'] if result else None
                
        except PostgreSQLError as e:
            self.logger.error(f"Error getting page label location for book {book_id}: {e}")
            raise DatabaseError(f"Failed to get page label location: {e}")

    # =====================================================
    # UTILITY METHODS
    # =====================================================
    
    def execute_query(self, query: str, params: Tuple = None, fetch: str = 'all') -> Any:
        """
        Execute a custom query.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: 'all', 'one', or 'none' for fetchall(), fetchone(), or no fetch
            
        Returns:
            Query results based on fetch parameter
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                
                if fetch == 'all':
                    return [dict(row) for row in cursor.fetchall()]
                elif fetch == 'one':
                    result = cursor.fetchone()
                    return dict(result) if result else None
                else:
                    return None
                    
        except PostgreSQLError as e:
            self.logger.error(f"Error executing query: {e}")
            raise DatabaseError(f"Failed to execute query: {e}")
    
    def test_connection(self) -> bool:
        """
        Test the database connection.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            with self.get_connection():
                self.logger.info("Database connection test successful")
                return True
        except DatabaseError:
            self.logger.error("Database connection test failed")
            return False


# =====================================================
# EXAMPLE USAGE AND TESTING
# =====================================================

def test_page_range_parsing():
    """Test the _parse_page_range method with various input formats."""
    print("🧪 Testing _parse_page_range method:")
    print("=" * 50)
    
    db = PureBhaktiVaultDB()
    
    # Test cases for different input formats
    test_cases = [
        # (input, description)
        ('[1,10)', 'String with exclusive end'),
        ('[1,10]', 'String with inclusive end'), 
        ('(1,10)', 'String with exclusive start and end'),
        ('[5,15]', 'Standard inclusive range'),
        ('[100,200)', 'Large range with exclusive end'),
        ('', 'Empty string'),
        (None, 'None value'),
        ('invalid', 'Invalid format'),
        ('[1,1]', 'Single page range'),
        ('[10,5]', 'Invalid order (end < start)'),
    ]
    
    for test_input, description in test_cases:
        try:
            result = db._parse_page_range(test_input)
            print(f"Input: {repr(test_input):15s} → {result} ({description})")
        except Exception as e:
            print(f"Input: {repr(test_input):15s} → ERROR: {e} ({description})")
    
    print("\n" + "=" * 50)


def main():
    """Example usage of the PureBhaktiVaultDB utility."""
    
    # Initialize the database utility
    db = PureBhaktiVaultDB()
    
    # Test connection
    if not db.test_connection():
        print("Failed to connect to database. Check your connection parameters.")
        return
    
    try:
        # Example 1: Get book ID by PDF name
        pdf_name = "bhagavad-gita-4ed-eng.pdf"
        book_id = db.get_book_id_by_pdf_name(pdf_name)
        print(f"Book ID for {pdf_name}: {book_id}")
        
        # Example 2: Get book information
        if book_id:
            book_info = db.get_book_by_id(book_id)
            print(f"Book info: {book_info['original_book_title']}")
        
        # Example 3: Search books
        search_results = db.search_books("Bhagavad")
        print(f"Found {len(search_results)} books matching 'Bhagavad'")
        
        # Example 4: Get all books (limited)
        all_books = db.get_all_books(limit=5)
        print(f"First 5 books:")
        for book in all_books:
            print(f"  - {book['original_book_title']}")
        
        # Example 5: Test page range methods
        print(f"\n📄 Testing page range methods for book ID {book_id}:")
        
        # Test TOC pages
        toc_pages = db.get_toc_pages(book_id)
        print(f"TOC pages: {toc_pages}")
        
        # Test verse pages  
        verse_pages = db.get_verse_pages(book_id)
        print(f"Verse pages: {verse_pages}")
        
        # Test glossary pages
        glossary_pages = db.get_glossary_pages(book_id)
        print(f"Glossary pages: {glossary_pages}")
        
        # Test with multiple books to see different range formats
        print(f"\n📚 Testing page ranges across multiple books:")
        test_books = db.get_all_books(limit=3)
        for book in test_books:
            test_id = book['book_id']
            title = book['original_book_title'][:30] + "..." if len(book['original_book_title']) > 30 else book['original_book_title']
            
            toc = db.get_toc_pages(test_id)
            verse = db.get_verse_pages(test_id) 
            glossary = db.get_glossary_pages(test_id)
            
            print(f"Book {test_id} ({title}):")
            print(f"  TOC: {toc}, Verse: {verse}, Glossary: {glossary}")
            
    except DatabaseError as e:
        print(f"Database error: {e}")


if __name__ == "__main__":
    # Run the range parsing tests first
    test_page_range_parsing()
    
    # Then run the main database tests
    main()