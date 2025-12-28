"""
Utility to split double-page layout PDFs into single pages.
Splits each page in half along the X-axis (width) and creates a new PDF
with sequential single pages.
"""

import fitz  # PyMuPDF
from pathlib import Path


def split_double_page_pdf(input_pdf_path: str) -> str:
    """
    Split a double-page layout PDF into single pages.
    Handles page rotation automatically.

    Args:
        input_pdf_path: Path to the input PDF file

    Returns:
        Path to the output PDF file
    """
    input_path = Path(input_pdf_path)
    output_path = input_path.parent / f"{input_path.stem}_split.pdf"

    # Open the input PDF
    input_doc = fitz.open(input_pdf_path)

    # Create a new PDF for output
    output_doc = fitz.open()

    # Process each page
    for page_num in range(len(input_doc)):
        page = input_doc[page_num]

        # Get page rotation and reset it to 0 for processing
        rotation = page.rotation
        page.set_rotation(360)

        # Get the page dimensions after rotation reset
        rect = page.rect
        width = rect.width
        height = rect.height

        print(f"Page {page_num + 1}: Original rotation={rotation}°, Width={width:.1f}, Height={height:.1f}")

        # Determine if we need to split vertically (height) or horizontally (width)
        # For landscape double-page spreads, width > height, split vertically down the middle
        if width > height:
            # Split vertically (along width)
            midpoint = width / 2

            # Right half (first page in sequence)
            right_rect = fitz.Rect(midpoint, 0, width, height)
            right_page = output_doc.new_page(width=midpoint, height=height)
            right_page.show_pdf_page(
                fitz.Rect(0, 0, midpoint, height),
                input_doc,
                page_num,
                clip=right_rect
            )
            right_page.set_rotation(90)

            # Left half (second page in sequence)
            left_rect = fitz.Rect(0, 0, midpoint, height)
            left_page = output_doc.new_page(width=midpoint, height=height)
            left_page.show_pdf_page(left_page.rect, input_doc, page_num, clip=left_rect)
            left_page.set_rotation(90)
        else:
            # Split horizontally (along height) - for portrait double-page spreads
            midpoint = height / 2

            # Bottom half (first page)
            bottom_rect = fitz.Rect(0, midpoint, width, height)
            bottom_page = output_doc.new_page(width=width, height=midpoint)
            bottom_page.show_pdf_page(
                fitz.Rect(0, 0, width, midpoint),
                input_doc,
                page_num,
                clip=bottom_rect
            )
            bottom_page.set_rotation(90)

            # Top half (second page)
            top_rect = fitz.Rect(0, 0, width, midpoint)
            top_page = output_doc.new_page(width=width, height=midpoint)
            top_page.show_pdf_page(top_page.rect, input_doc, page_num, clip=top_rect)
            top_page.set_rotation(90)

    # Save the output PDF
    output_doc.save(str(output_path))
    output_doc.close()
    input_doc.close()

    return str(output_path)


if __name__ == "__main__":
    input_pdf = "/Users/kamaldivi/Development/pbb_books/tobe_processed/double_page_books/Sri_Slokamritam.pdf"
    output_pdf = split_double_page_pdf(input_pdf)
    print(f"Split PDF saved to: {output_pdf}")
