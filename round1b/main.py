#!/usr/bin/env python3
# main.py

import json, sys, time
from pathlib import Path
from datetime import datetime, timezone

from src.extractor import extract_outline, extract_section_content
from src.relevance import SemanticRanker

INPUT_DIR  = Path("/app/input")
OUTPUT_DIR = Path("/app/output")
INPUT_JSON = INPUT_DIR / "challenge1b_input.json"
OUTPUT_JSON = OUTPUT_DIR / "challenge1b_output.json"

def process_document_collection():
    start_time = time.perf_counter()
    if not INPUT_JSON.exists():
        print(f"Error: Input file not found at {INPUT_JSON}", file=sys.stderr)
        sys.exit(1)
    with open(INPUT_JSON, 'r') as f:
        job_details = json.load(f)
    persona = job_details.get("persona")
    job_to_be_done = job_details.get("job_to_be_done")
    document_files = job_details.get("documents", [])
    print(f"Starting processing for Persona: {persona}")
    print(f"Task: {job_to_be_done}")
    all_sections = []
    document_outlines = {}
    for doc_name in document_files:
        pdf_path = INPUT_DIR / doc_name
        if not pdf_path.exists():
            print(f"Warning: Document {doc_name} not found, skipping.", file=sys.stderr)
            continue
        print(f"Extracting outline from {doc_name}...")
        outline_data = extract_outline(str(pdf_path))
        headings_list = outline_data.get('outline', [])
        for heading in headings_list:
            heading['document'] = doc_name
        all_sections.extend(headings_list)
        document_outlines[doc_name] = headings_list
    ranker = SemanticRanker()
    ranked_sections = ranker.rank_sections(persona, job_to_be_done, all_sections)
    top_n = 10
    final_extracted_sections = []
    for section in ranked_sections[:top_n]:
        doc_name = section['document']
        pdf_path = str(INPUT_DIR / doc_name)
        print(f"Extracting content for top section: '{section['text']}' from {doc_name}")
        refined_text = extract_section_content(pdf_path, section, document_outlines[doc_name])
        final_extracted_sections.append({
            "document": doc_name,
            "page_number": section['page'],
            "section_title": section['text'],
            "importance_rank": section['relevance_score'],
            "refined_text": refined_text
        })
    output_data = {
        "metadata": {
            "input_documents": document_files,
            "persona": persona,
            "job_to_be_done": job_to_be_done,
            "processing_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "extracted_sections": final_extracted_sections
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    runtime = time.perf_counter() - start_time
    print(f"\n[✓] Processing complete in {runtime:.2f}s")
    print(f"Output saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    process_document_collection()
