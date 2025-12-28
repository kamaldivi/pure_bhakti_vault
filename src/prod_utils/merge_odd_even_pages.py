import fitz  # PyMuPDF

odd_file = "/Users/kamaldivi/Development/pbb_books/tobe_processed/double_page_books/Remembering Srila Prabhupada_odd.pdf"
even_file = "/Users/kamaldivi/Development/pbb_books/tobe_processed/double_page_books/Remembering Srila Prabhupada_even.pdf"
output_file = "/Users/kamaldivi/Development/pbb_books/tobe_processed/double_page_books/Remembering Srila Prabhupada_combined.pdf"

odd_doc = fitz.open(odd_file)
even_doc = fitz.open(even_file)
out = fitz.open()

# Interleave pages
for i in range(max(len(odd_doc), len(even_doc))):
    if i < len(odd_doc):
        out.insert_pdf(odd_doc, from_page=i, to_page=i)
    if i < len(even_doc):
        out.insert_pdf(even_doc, from_page=i, to_page=i)

out.save(output_file)
out.close()
odd_doc.close()
even_doc.close()

print(f"✅ Interleaved PDF saved to {output_file}")