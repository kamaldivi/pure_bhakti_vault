import os
import csv
import glob
from pathlib import Path

import fitz  # PyMuPDF

# Import your detector
from page_boundaries import detect_page_boundaries, BoundaryConfig


class PDFBoundaryTester:
    def __init__(self, folder_path: str, header_margin_pts: float = 2.0, footer_margin_pts: float = 2.0):
        self.folder_path = Path(folder_path)
        self.out_folder = self.folder_path / "headers_footers"
        self.out_folder.mkdir(parents=True, exist_ok=True)
        self.header_margin_pts = float(header_margin_pts)
        self.footer_margin_pts = float(footer_margin_pts)

    def run_tests(self):
        pdf_files = sorted(glob.glob(str(self.folder_path / "*.pdf")))
        if not pdf_files:
            print(f"No PDF files found in {self.folder_path}")
            return

        # Ask detector to return NORMALIZED boundaries so we can scale per page
        cfg = BoundaryConfig(
            ignored_pages=None,
            min_body_ratio=0.70,
            use_dbscan_like=True,
            eps_multiplier=3.0,
            min_cluster_coverage=0.4,
            return_normalized=True,   # <-- key change
            diagnostics=True,
        )

        for pdf_path in pdf_files:
            pdf_name = os.path.basename(pdf_path)
            print(f"▶️  Processing: {pdf_name} ...")
            try:
                header_norm, footer_norm, stats, _ = detect_page_boundaries(pdf_path, cfg)
                rows, found_hdr_pages, found_ftr_pages = self._extract_header_footer_rows(
                    pdf_path, pdf_name, header_norm, footer_norm, cfg
                )

                # Write CSV
                out_csv = self.out_folder / f"{pdf_name}.csv"
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["pdf_name", "pdf_page_number", "header_text", "footer_text"])
                    writer.writerows(rows)

                print(
                    f"✅ Completed: {pdf_name} | pages_measured={stats.get('pages_measured')} | "
                    f"header_norm={header_norm:.4f} footer_norm={footer_norm:.4f} | "
                    f"headers_on_pages={found_hdr_pages} footers_on_pages={found_ftr_pages} | "
                    f"csv: {out_csv}"
                )
            except Exception as e:
                print(f"❌ ERROR for {pdf_name}: {e}")

    # -------- helpers --------

    def _extract_header_footer_rows(self, pdf_path: str, pdf_name: str,
                                    header_norm: float, footer_norm: float,
                                    cfg: BoundaryConfig):
        """
        For each page, build header/footer rectangles from normalized Y boundaries,
        then extract text with page.get_text(..., clip=rect).
        """
        rows = []
        doc = fitz.open(pdf_path)
        n = len(doc)

        pages_with_header = 0
        pages_with_footer = 0

        for i in range(n):
            try:
                if cfg.ignored_pages and i in cfg.ignored_pages:
                    rows.append([pdf_name, i + 1, "", ""])
                    continue

                page = doc.load_page(i)
                pw, ph = page.rect.width, page.rect.height

                # Per-page absolute Y from normalized thresholds
                header_y = max(0.0, min(ph, header_norm * ph))
                footer_y = max(0.0, min(ph, footer_norm * ph))

                # Construct rectangles (with tiny margins to catch borderline glyphs)
                header_rect = fitz.Rect(0, 0, pw, max(0.0, header_y + self.header_margin_pts))
                footer_rect = fitz.Rect(0, max(0.0, footer_y - self.footer_margin_pts), pw, ph)

                # Extract text
                header_text_raw = page.get_text("text", clip=header_rect) or ""
                footer_text_raw = page.get_text("text", clip=footer_rect) or ""

                # Normalize spacing for CSV (single line each)
                header_text = " | ".join([t.strip() for t in header_text_raw.splitlines() if t.strip()])
                footer_text = " | ".join([t.strip() for t in footer_text_raw.splitlines() if t.strip()])

                if header_text:
                    pages_with_header += 1
                if footer_text:
                    pages_with_footer += 1

                rows.append([pdf_name, i + 1, header_text, footer_text])

                # Progress every 50 pages and on completion
                if (i + 1) % 50 == 0 or (i + 1) == n:
                    print(f"   … {pdf_name}: processed {i + 1}/{n} pages")
            except Exception as ex:
                # Keep going; emit row with empty text on failure
                rows.append([pdf_name, i + 1, "", ""])
                print(f"   ⚠️  Page {i + 1}: {ex}")

        return rows, pages_with_header, pages_with_footer


if __name__ == "__main__":
    tester = PDFBoundaryTester("/Users/kamaldivi/Development/Gurudev_Books", header_margin_pts=2.0, footer_margin_pts=2.0)
    tester.run_tests()
