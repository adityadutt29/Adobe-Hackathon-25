#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
from src.extractor import extract_outline

INPUT_DIR  = Path("/app/input")
OUTPUT_DIR = Path("/app/output")

def process_pdf(pdf_path: Path):
    start = time.perf_counter()
    data = extract_outline(str(pdf_path))
    runtime = time.perf_counter() - start
    json_path = OUTPUT_DIR / f"{pdf_path.stem}.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[✓] {pdf_path.name}  ({runtime:.2f}s)  →  {json_path.name}")

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    pdfs = list(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in /app/input", file=sys.stderr)
        sys.exit(1)
    for pdf in pdfs:
        try:
            process_pdf(pdf)
        except Exception as e:
            print(f"[✗] {pdf.name}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
