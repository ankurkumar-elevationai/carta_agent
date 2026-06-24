"""Extract text from investment-table-fields.pdf using multiple methods."""
import fitz
import sys

pdf_path = r"c:\Users\iaman\Vscode Pycharm\openclaw_carta\docs\investment-table-fields.pdf"
doc = fitz.open(pdf_path)
print(f"Total pages: {len(doc)}")

for i, page in enumerate(doc):
    text = page.get_text()
    if text.strip():
        print(f"\n=== PAGE {i+1} ===")
        print(text)
    else:
        # Try extracting from images via OCR or blocks
        blocks = page.get_text("dict")["blocks"]
        text_blocks = [b for b in blocks if b.get("type") == 0]
        image_blocks = [b for b in blocks if b.get("type") == 1]
        print(f"\n=== PAGE {i+1} (no text, {len(text_blocks)} text blocks, {len(image_blocks)} image blocks) ===")
        
        # Try extracting text from text blocks anyway
        for tb in text_blocks:
            for line in tb.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        print(span["text"], end=" ")
            print()
        
        if image_blocks:
            print(f"  [Contains {len(image_blocks)} embedded images - likely screenshot/scan]")
            # Save first image for inspection
            for img_idx, img_block in enumerate(image_blocks[:2]):
                xref = img_block.get("image")
                if not xref:
                    images = page.get_images()
                    if images:
                        print(f"  Page images: {len(images)}")
                        for img in images[:3]:
                            print(f"    Image xref={img[0]}, size={img[2]}x{img[3]}")
