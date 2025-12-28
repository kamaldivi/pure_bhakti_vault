"""
Glossary Vector Embeddings Generator
Creates vector embeddings for glossary entries using Ollama's bge-m3 model
and stores them in PostgreSQL with pgvector extension.
"""

import os
import sys
import psycopg2
import requests
from dotenv import load_dotenv
from typing import List, Optional

# Load environment variables
load_dotenv()


class GlossaryVectorizer:
    """Handles creation of vector embeddings for glossary entries"""

    def __init__(self, model: str = None, ollama_url: str = None):
        """
        Initialize the vectorizer

        Args:
            model: Ollama model to use for embeddings (defaults to env var or bge-m3:latest)
            ollama_url: Base URL for Ollama API (defaults to env var or http://localhost:11434)
        """
        self.model = model or os.getenv('OLLAMA_MODEL', 'bge-m3:latest')
        self.ollama_url = ollama_url or os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.embedding_dim = int(os.getenv('EMBEDDING_DIM', '1024'))  # bge-m3 produces 1024-dimensional embeddings

        # Database connection parameters
        self.db_params = {
            'dbname': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT')
        }

        self.conn = None

    def connect_db(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**self.db_params)
            print(f"Connected to database: {self.db_params['dbname']}")
        except Exception as e:
            print(f"Error connecting to database: {e}")
            sys.exit(1)

    def close_db(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("Database connection closed")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding from local Ollama instance

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        url = f"{self.ollama_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }

        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                return response.json()["embedding"]
            else:
                print(f"Error getting embedding: {response.text}")
                return None
        except Exception as e:
            print(f"Exception getting embedding: {e}")
            return None

    def create_embeddings_table(self):
        """Create table for storing glossary embeddings"""
        with self.conn.cursor() as cur:
            # Create table if it doesn't exist
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS glossary_embeddings (
                    glossary_id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    term VARCHAR(255) NOT NULL,
                    embedding vector({self.embedding_dim}) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (glossary_id) REFERENCES glossary(glossary_id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES book(book_id) ON DELETE CASCADE
                );
            """)

            # Create index for faster similarity searches
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_glossary_embeddings_vector
                ON glossary_embeddings USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)

            self.conn.commit()
            print("Created glossary_embeddings table with vector index")

    def fetch_glossary_entries(self) -> List[tuple]:
        """
        Fetch all glossary entries from the database

        Returns:
            List of tuples (glossary_id, book_id, term, description)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT glossary_id, book_id, term, description
                FROM glossary
                ORDER BY glossary_id
            """)
            entries = cur.fetchall()
            print(f"Fetched {len(entries)} glossary entries")
            return entries

    def check_existing_embeddings(self) -> set:
        """
        Check which glossary entries already have embeddings

        Returns:
            Set of glossary_ids that already have embeddings
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT glossary_id FROM glossary_embeddings")
                existing = {row[0] for row in cur.fetchall()}
                print(f"Found {len(existing)} existing embeddings")
                return existing
        except psycopg2.errors.UndefinedTable:
            # Table doesn't exist yet
            return set()

    def insert_embedding(self, glossary_id: int, book_id: int, term: str, embedding: List[float]):
        """
        Insert or update embedding in database

        Args:
            glossary_id: ID of the glossary entry
            book_id: ID of the book
            term: Glossary term
            embedding: Embedding vector
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO glossary_embeddings (glossary_id, book_id, term, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (glossary_id)
                DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    updated_at = CURRENT_TIMESTAMP
            """, (glossary_id, book_id, term, embedding))

    def process_glossary(self, batch_size: int = 10, skip_existing: bool = True):
        """
        Process all glossary entries and generate embeddings

        Args:
            batch_size: Number of entries to process before committing
            skip_existing: Whether to skip entries that already have embeddings
        """
        # Fetch all glossary entries
        entries = self.fetch_glossary_entries()

        if not entries:
            print("No glossary entries found")
            return

        # Check existing embeddings if needed
        existing_ids = self.check_existing_embeddings() if skip_existing else set()

        # Process entries
        processed = 0
        skipped = 0
        errors = 0

        for idx, (glossary_id, book_id, term, description) in enumerate(entries):
            # Skip if already processed
            if skip_existing and glossary_id in existing_ids:
                skipped += 1
                continue

            # Combine term and definition for embedding
            text_to_embed = f"{term}: {description}"

            # Get embedding from Ollama
            embedding = self.get_embedding(text_to_embed)

            if embedding is None:
                print(f"Failed to get embedding for glossary_id={glossary_id}, term='{term}'")
                errors += 1
                continue

            # Verify embedding dimension
            if len(embedding) != self.embedding_dim:
                print(f"Warning: Expected {self.embedding_dim} dimensions, got {len(embedding)} for term '{term}'")

            # Insert into database
            try:
                self.insert_embedding(glossary_id, book_id, term, embedding)
                processed += 1

                # Commit in batches
                if processed % batch_size == 0:
                    self.conn.commit()
                    print(f"Processed {processed}/{len(entries) - len(existing_ids)} entries (skipped: {skipped}, errors: {errors})")

            except Exception as e:
                print(f"Error inserting embedding for glossary_id={glossary_id}: {e}")
                errors += 1
                continue

        # Final commit
        self.conn.commit()

        print(f"\n=== Summary ===")
        print(f"Total entries: {len(entries)}")
        print(f"Processed: {processed}")
        print(f"Skipped: {skipped}")
        print(f"Errors: {errors}")

    def verify_embeddings(self):
        """Verify the created embeddings"""
        with self.conn.cursor() as cur:
            # Count total embeddings
            cur.execute("SELECT COUNT(*) FROM glossary_embeddings")
            count = cur.fetchone()[0]
            print(f"\nTotal embeddings in database: {count}")

            # Show sample entries
            cur.execute("""
                SELECT ge.glossary_id, ge.term,
                       pg_column_size(ge.embedding) as embedding_size
                FROM glossary_embeddings ge
                LIMIT 5
            """)

            print("\nSample entries:")
            for row in cur.fetchall():
                print(f"  ID={row[0]}, Term='{row[1]}', Embedding size={row[2]} bytes")

    def search_similar(self, query: str, limit: int = 5):
        """
        Search for similar glossary terms using vector similarity

        Args:
            query: Search query
            limit: Number of results to return
        """
        # Get embedding for query
        query_embedding = self.get_embedding(query)

        if query_embedding is None:
            print("Failed to get embedding for query")
            return

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ge.glossary_id, ge.term, g.description,
                       1 - (ge.embedding <=> %s::vector) as similarity
                FROM glossary_embeddings ge
                JOIN glossary g ON ge.glossary_id = g.glossary_id
                ORDER BY ge.embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, limit))

            results = cur.fetchall()

            print(f"\nTop {limit} similar terms for query: '{query}'")
            for idx, (gid, term, desc, similarity) in enumerate(results, 1):
                print(f"\n{idx}. {term} (similarity: {similarity:.4f})")
                print(f"   {desc[:100]}...")


def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(description='Generate vector embeddings for glossary entries')
    parser.add_argument('--model', default='bge-m3:latest', help='Ollama model to use')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for commits')
    parser.add_argument('--force', action='store_true', help='Reprocess all entries, even if embeddings exist')
    parser.add_argument('--search', type=str, help='Search for similar terms')
    parser.add_argument('--limit', type=int, default=5, help='Number of search results to return')
    parser.add_argument('--verify-only', action='store_true', help='Only verify existing embeddings')

    args = parser.parse_args()

    # Initialize vectorizer
    vectorizer = GlossaryVectorizer(model=args.model)

    try:
        # Connect to database
        vectorizer.connect_db()

        if args.search:
            # Search mode
            vectorizer.search_similar(args.search, limit=args.limit)
        elif args.verify_only:
            # Verify only
            vectorizer.verify_embeddings()
        else:
            # Create/update embeddings
            vectorizer.create_embeddings_table()
            vectorizer.process_glossary(
                batch_size=args.batch_size,
                skip_existing=not args.force
            )
            vectorizer.verify_embeddings()

    finally:
        # Close connection
        vectorizer.close_db()


if __name__ == "__main__":
    main()
