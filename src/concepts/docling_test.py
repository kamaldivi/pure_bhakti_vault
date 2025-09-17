from docling.document_converter import DocumentConverter
source = "/Users/kamaldivi/Development/Gurudev_Books/My_Siksa-guru_Priya-bandhu_4Ed_2012.pdf"  # document per local path or URL
converter = DocumentConverter()
result = converter.convert(source)
output_txt = "/Users/kamaldivi/Development/Gurudev_Books/PageMapping/output_book_1.txt"

with open(output_txt, "w", encoding="utf-8") as f:
        f.write(result.document.export_to_markdown())

print(f"✅ Cleaned text written to: {output_txt}")