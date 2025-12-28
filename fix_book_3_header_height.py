#!/usr/bin/env python3
"""
Fix the header height for book_id 3 to prevent truncation
"""
import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'pure_bhakti_vault'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

# New header height that includes the "T" but excludes "Introduction"
# Based on analysis: "Introduction" is at y=40-173, "T" is at y=40-62.5, content starts at y=66.3
# So header should be around 39.0 to include the "T"
new_header_height = 39.0

print(f"Updating header height for book_id 3 to {new_header_height}")

try:
    conn = psycopg2.connect(**db_config)

    with conn.cursor() as cur:
        # Get current value
        cur.execute("SELECT header_height FROM book WHERE book_id = 3")
        current = cur.fetchone()
        print(f"Current header height: {current[0]}")

        # Update header height
        cur.execute("UPDATE book SET header_height = %s WHERE book_id = 3", (new_header_height,))

        # Verify update
        cur.execute("SELECT header_height FROM book WHERE book_id = 3")
        updated = cur.fetchone()
        print(f"Updated header height: {updated[0]}")

        conn.commit()
        print("✅ Header height updated successfully!")

        # Test extraction with new height
        print(f"\nTesting extraction with new height...")

        import fitz
        pdf_folder = os.getenv('PDF_FOLDER', '/Users/kamaldivi/Development/pbb_books/')
        pdf_path = os.path.join(pdf_folder, 'beyond_liberation_4th_ed.pdf')

        if os.path.exists(pdf_path):
            doc = fitz.open(pdf_path)
            page = doc.load_page(8)  # Page 9
            page_rect = page.rect

            # Test with new header height
            content_y0 = page_rect.y0 + new_header_height
            content_y1 = 450.0  # footer height

            content_rect = fitz.Rect(page_rect.x0, content_y0, page_rect.x1, content_y1)
            content_text = page.get_text("text", clip=content_rect)
            first_line = content_text.split('\n')[0].strip()

            print(f"First line with new header height: '{first_line}'")

            if first_line.startswith("The purpose"):
                print("✅ Problem fixed! First line now starts with 'The purpose'")
            else:
                print("❌ Issue still exists")

            doc.close()

    conn.close()

except Exception as e:
    print(f"Error: {e}")
    if 'conn' in locals():
        conn.rollback()
        conn.close()