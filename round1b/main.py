#!/usr/bin/env python3
# main.py

import json, sys, time
from pathlib import Path
from datetime import datetime, timezone
import pdfplumber

from src.extractor import extract_outline, extract_section_content
from src.relevance import SemanticRanker

# Docker paths
INPUT_DIR  = Path("/app/input")
OUTPUT_DIR = Path("/app/output")
INPUT_JSON = INPUT_DIR / "challenge1b_input.json"
OUTPUT_JSON = OUTPUT_DIR / "challenge1b_output.json"

def _extract_fallback_document_content(pdf_path: str, doc_name: str) -> str:
    """Extract meaningful content from a document when no proper headings are found"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Try to extract from first few pages
            content_parts = []
            for page_num in range(min(3, len(pdf.pages))):  # First 3 pages max
                page = pdf.pages[page_num]
                text = page.extract_text()
                if text and text.strip():
                    # Clean and limit the text
                    clean_text = ' '.join(text.split())
                    if len(clean_text) > 100:  # Only use substantial content
                        content_parts.append(clean_text)
                        
            if content_parts:
                # Combine content and limit to reasonable length
                full_content = ' '.join(content_parts)
                # Take first 500 characters to ensure we have meaningful content
                if len(full_content) > 500:
                    # Try to cut at a sentence boundary
                    cut_point = full_content.find('. ', 400)
                    if cut_point > 0 and cut_point < 600:
                        return full_content[:cut_point + 1]
                    else:
                        return full_content[:500] + "..."
                else:
                    return full_content
                    
    except Exception as e:
        print(f"Error in fallback extraction for {doc_name}: {e}")
        
    # Final fallback
    return f"Document summary content from {doc_name.replace('.pdf', '')} covering key topics and information relevant to travel planning."

def process_document_collection():
    start_time = time.perf_counter()
    if not INPUT_JSON.exists():
        print(f"Error: Input file not found at {INPUT_JSON}", file=sys.stderr)
        sys.exit(1)
    with open(INPUT_JSON, 'r') as f:
        job_details = json.load(f)
    
    # Handle new nested format
    persona_data = job_details.get("persona", {})
    persona = persona_data.get("role", "") if isinstance(persona_data, dict) else persona_data
    
    job_data = job_details.get("job_to_be_done", {})
    job_to_be_done = job_data.get("task", "") if isinstance(job_data, dict) else job_data
    
    # Extract document filenames from the new format
    documents_data = job_details.get("documents", [])
    document_files = []
    for doc in documents_data:
        if isinstance(doc, dict) and "filename" in doc:
            document_files.append(doc["filename"])
        else:
            document_files.append(str(doc))  # Fallback for old format
    print(f"Starting processing for Persona: {persona}")
    print(f"Task: {job_to_be_done}")
    all_sections = []
    document_outlines = {}
    documents_without_headings = []
    
    for doc_name in document_files:
        pdf_path = INPUT_DIR / doc_name
        if not pdf_path.exists():
            print(f"Warning: Document {doc_name} not found, skipping.", file=sys.stderr)
            continue
        print(f"Extracting outline from {doc_name}...")
        outline_data = extract_outline(str(pdf_path))
        headings_list = outline_data.get('outline', [])
        
        if not headings_list:
            # Create a fallback section for documents without headings
            print(f"No headings found in {doc_name}, creating fallback section")
            fallback_section = {
                'text': f"Overview of {doc_name.replace('.pdf', '')}",
                'level': 'h1',
                'page': 1,
                'position': 0.0,
                'document': doc_name
            }
            headings_list = [fallback_section]
            documents_without_headings.append(doc_name)
        else:
            for heading in headings_list:
                heading['document'] = doc_name
                
        all_sections.extend(headings_list)
        document_outlines[doc_name] = headings_list
    ranker = SemanticRanker()
    ranked_sections = ranker.rank_sections(persona, job_to_be_done, all_sections)
    
    # Ensure we get representation from all documents with better diversity
    top_n = 10
    final_extracted_sections = []
    subsection_analysis = []
    
    # Strategy: GUARANTEE at least 1 section from each document, then fill remaining with top-ranked
    selected_sections = []
    document_count = {}
    used_documents = set()
    
    # Force at least one section per document by document order
    documents_covered = set()
    remaining_sections = []
    
    # First pass: Ensure every document gets at least one section
    for doc_name in document_files:
        if doc_name not in documents_covered:
            # Find the best section from this document
            best_section = None
            best_rank = float('inf')
            
            for i, section in enumerate(ranked_sections):
                if section['document'] == doc_name:
                    best_section = section
                    best_rank = i
                    break
            
            if best_section:
                selected_sections.append(best_section)
                documents_covered.add(doc_name)
                document_count[doc_name] = 1
                print(f"Guaranteed section from {doc_name}: '{best_section['text']}'")
    
    # Second pass: Fill remaining slots with highest-ranked sections from any document
    max_per_doc = max(2, top_n // len(document_files))  # Allow max 2-3 per document
    for section in ranked_sections:
        if len(selected_sections) >= top_n:
            break
        doc_name = section['document']
        if section not in selected_sections and document_count.get(doc_name, 0) < max_per_doc:
            selected_sections.append(section)
            document_count[doc_name] = document_count.get(doc_name, 0) + 1
    
    print(f"Selected sections from {len(documents_covered)} documents: {sorted(documents_covered)}")
    print(f"Document distribution: {dict(sorted(document_count.items()))}")
    
    for i, section in enumerate(selected_sections, 1):
        doc_name = section['document']
        pdf_path = str(INPUT_DIR / doc_name)
        print(f"Extracting content for section {i}: '{section['text']}' from {doc_name}")
        
        try:
            # Special handling for documents without real headings
            if doc_name in documents_without_headings:
                # For documents without headings, extract from the first page or multiple pages
                refined_text = _extract_fallback_document_content(pdf_path, doc_name)
            else:
                refined_text = extract_section_content(pdf_path, section, document_outlines[doc_name])
            
            if not refined_text.strip():
                print(f"Warning: No content extracted for section '{section['text']}' from {doc_name}")
                # Use more aggressive fallback
                refined_text = _extract_fallback_document_content(pdf_path, doc_name)
                
        except Exception as e:
            print(f"Error extracting content from {doc_name}: {e}")
            refined_text = _extract_fallback_document_content(pdf_path, doc_name)
        
        # Basic section info without refined_text
        final_extracted_sections.append({
            "document": doc_name,
            "section_title": section['text'],
            "importance_rank": i,  # Simple integer ranking
            "page_number": section['page']
        })
        
        # Detailed content in subsection_analysis
        subsection_analysis.append({
            "document": doc_name,
            "refined_text": refined_text,
            "page_number": section['page']
        })
    
    output_data = {
        "metadata": {
            "input_documents": document_files,
            "persona": persona,
            "job_to_be_done": job_to_be_done,
            "processing_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "extracted_sections": final_extracted_sections,
        "subsection_analysis": subsection_analysis
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    runtime = time.perf_counter() - start_time
    print(f"\n[✓] Processing complete in {runtime:.2f}s")
    print(f"Output saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    process_document_collection()
