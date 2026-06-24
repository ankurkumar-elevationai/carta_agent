"""Extract images from PDF pages."""
import fitz

pdf_path = r"c:\Users\iaman\Vscode Pycharm\openclaw_carta\docs\investment-table-fields.pdf"
out_dir = r"c:\Users\iaman\Vscode Pycharm\openclaw_carta\scratch\pdf_pages"

import os
os.makedirs(out_dir, exist_ok=True)

doc = fitz.open(pdf_path)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=200)
    out_path = os.path.join(out_dir, f"page_{i+1:02d}.png")
    pix.save(out_path)
    print(f"Saved {out_path} ({pix.width}x{pix.height})")
