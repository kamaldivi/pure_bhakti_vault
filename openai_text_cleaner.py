#!/usr/bin/env python3
"""
OpenAI Text Cleaner Utility

This utility processes page content from the content table using OpenAI's API
to clean and correct Sanskrit transliteration and OCR artifacts.

Features:
1. Reads content from PostgreSQL content table based on TEST_BOOK_ID
2. Processes text using OpenAI GPT-4 with specialized Sanskrit cleaning prompt
3. Updates ai_page_content column with cleaned results
4. Supports restart functionality via RESTART_PAGE environment variable
5. Minimal progress tracking with page number messages

Environment Variables Required:
- TEST_BOOK_ID: Comma-separated list of book IDs to process
- OPENAI_API_KEY: OpenAI API key for text processing
- RESTART_PAGE: Optional page number to resume processing from
- Database connection parameters (DB_HOST, DB_PORT, etc.)

Usage:
    python openai_text_cleaner.py
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import openai
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Add src/prod_utils to path for imports
sys.path.append(str(Path(__file__).parent / "src" / "prod_utils"))
from pure_bhakti_vault_db import PureBhaktiVaultDB, DatabaseError


class OpenAITextCleaner:
    """
    Utility to clean page content using OpenAI API and update ai_page_content column.
    """

    SYSTEM_PROMPT = """You are a text cleaner and Sanskrit transliteration corrector.

You will be given text extracted from scanned spiritual books. The text may contain three kinds of content:

1. **English commentary/translation**
   - Leave English text untouched except:
     • Remove extra spaces, duplicate whitespace, and line-break artifacts.
     • Fix obvious OCR artifacts (e.g., random % or symbols in English words).

2. **Roman transliteration of Sanskrit (IAST-like but corrupted)**
   - Correct transliteration errors into standard IAST form.
   - Preserve Sanskrit words in Roman script with proper diacritics (ā, ī, ū, ṛ, ṝ, ḷ, ṃ, ṇ, ñ, ś, ṣ, etc.).
   - Do not translate into English.
   - Example: "harinṛma" → "harināma"; "aparṛdha" → "aparādha"; "saṣjaya" → "sañjaya".

3. **Devanāgarī blocks (Hindi/Sanskrit characters)**
   - If the input contains Devanāgarī script, preserve it as correct Devanāgarī.
   - Fix OCR garbling where possible, keeping the verse intact.
   - Do NOT convert Devanāgarī into Roman transliteration or English. Leave it in Devanāgarī.

---

### Output Rules
- Keep the output in the **same structure** as input (don't merge or reorder blocks).
- Only fix spacing, diacritics, and OCR errors as described.
- Do not add explanations, translations, or commentary — return **cleaned text only**."""

    def __init__(self):
        """Initialize the text cleaner with database and OpenAI connections."""
        self.logger = self._setup_logger()
        self.db = PureBhaktiVaultDB()

        # Initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        openai.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)

        # Get configuration
        self.test_book_ids = self._get_book_ids()
        self.restart_page = self._get_restart_page()

        self.logger.info(f"Initialized OpenAI Text Cleaner for book IDs: {self.test_book_ids}")
        if self.restart_page:
            self.logger.info(f"Will restart from page: {self.restart_page}")

    def _setup_logger(self) -> logging.Logger:
        """Setup logging for the text cleaner."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _get_book_ids(self) -> List[int]:
        """Get book IDs from TEST_BOOK_ID environment variable."""
        book_ids_str = os.getenv('TEST_BOOK_ID', '')
        if not book_ids_str:
            raise ValueError("TEST_BOOK_ID environment variable is required")

        try:
            return [int(id.strip()) for id in book_ids_str.split(',') if id.strip()]
        except ValueError as e:
            raise ValueError(f"Invalid TEST_BOOK_ID format: {book_ids_str}") from e

    def _get_restart_page(self) -> Optional[int]:
        """Get restart page number from RESTART_PAGE environment variable."""
        restart_str = os.getenv('RESTART_PAGE', '')
        if restart_str:
            try:
                return int(restart_str)
            except ValueError as e:
                self.logger.warning(f"Invalid RESTART_PAGE value: {restart_str}, ignoring")
        return None

    def _ensure_ai_column_exists(self):
        """Ensure ai_page_content column exists in content table."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check if column exists
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'content' AND column_name = 'ai_page_content'
                    """)

                    if not cursor.fetchone():
                        self.logger.info("Adding ai_page_content column to content table")
                        cursor.execute("""
                            ALTER TABLE content
                            ADD COLUMN ai_page_content TEXT
                        """)
                        conn.commit()
                        self.logger.info("Successfully added ai_page_content column")
                    else:
                        self.logger.debug("ai_page_content column already exists")
        except Exception as e:
            raise DatabaseError(f"Failed to ensure ai_page_content column exists: {e}")

    def _get_content_to_process(self) -> List[Dict[str, Any]]:
        """Retrieve content records that need processing."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    placeholders = ','.join(['%s'] * len(self.test_book_ids))

                    # Base query
                    query = f"""
                        SELECT content_id, book_id, page_number, page_content
                        FROM content
                        WHERE book_id IN ({placeholders})
                        AND page_content IS NOT NULL
                        AND page_content != ''
                        AND (ai_page_content IS NULL OR ai_page_content = '')
                    """

                    # Add restart condition if specified
                    if self.restart_page is not None:
                        query += " AND page_number >= %s"
                        params = self.test_book_ids + [self.restart_page]
                    else:
                        params = self.test_book_ids

                    query += " ORDER BY book_id, page_number"

                    cursor.execute(query, params)
                    return cursor.fetchall()

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve content to process: {e}")

    def _clean_text_with_openai(self, content: str) -> str:
        """Send content to OpenAI for cleaning and return the result."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ],
                temperature=0,  # Deterministic output for text cleaning
                max_tokens=4000  # Adjust based on typical content length
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            raise Exception(f"OpenAI API call failed: {e}")

    def _update_ai_content(self, content_id: int, cleaned_content: str):
        """Update the ai_page_content column with cleaned content."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE content
                        SET ai_page_content = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE content_id = %s
                    """, (cleaned_content, content_id))
                    conn.commit()

        except Exception as e:
            raise DatabaseError(f"Failed to update ai_page_content for content_id {content_id}: {e}")

    def process_content(self):
        """Main method to process all content records."""
        try:
            # Ensure ai_page_content column exists
            self._ensure_ai_column_exists()

            # Get content to process
            records = self._get_content_to_process()

            if not records:
                self.logger.info("No content records found to process")
                return

            self.logger.info(f"Found {len(records)} records to process")

            processed_count = 0
            failed_count = 0

            for record in records:
                content_id = record['content_id']
                book_id = record['book_id']
                page_number = record['page_number']
                page_content = record['page_content']

                try:
                    # Progress message
                    self.logger.info(f"Processing book {book_id}, page {page_number}")

                    # Clean content with OpenAI
                    cleaned_content = self._clean_text_with_openai(page_content)

                    # Update database
                    self._update_ai_content(content_id, cleaned_content)

                    processed_count += 1
                    self.logger.debug(f"Successfully processed content_id {content_id}")

                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"Failed to process book {book_id}, page {page_number}: {e}")
                    continue

            # Summary
            self.logger.info(f"""
Processing complete:
- Total records: {len(records)}
- Successfully processed: {processed_count}
- Failed: {failed_count}
- Success rate: {(processed_count/len(records)*100):.1f}%
            """)

            if failed_count > 0:
                last_successful = None
                for i, record in enumerate(records):
                    if i < processed_count:
                        last_successful = record['page_number']

                if last_successful:
                    next_restart = last_successful + 1
                    self.logger.info(f"To restart from failures, set RESTART_PAGE={next_restart}")

        except Exception as e:
            self.logger.error(f"Critical error in process_content: {e}")
            raise


def main():
    """Main function to run the text cleaner."""
    try:
        cleaner = OpenAITextCleaner()
        cleaner.process_content()
    except Exception as e:
        logging.error(f"Failed to run text cleaner: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()