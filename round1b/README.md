# Challenge 1b: Persona-Driven Document Intelligence

## Overview
This solution addresses Challenge 1b of the Adobe India Hackathon 2025. The goal is to build an intelligent document analyst that extracts and prioritizes the most relevant sections from a collection of PDFs, based on a specific persona and their job-to-be-done. The system uses semantic ranking and document structure heuristics to deliver high-quality, persona-driven insights.

---

## Solution Highlights
- **Persona & Job Awareness:** Ranks and extracts sections most relevant to the provided persona and job-to-be-done.
- **Semantic Ranking:** Uses a local SentenceTransformer model (all-MiniLM-L6-v2) for semantic similarity scoring.
- **Heuristic Section Extraction:** Robust heading detection and section segmentation using font, layout, and OCR (for scanned PDFs).
- **Fast & Lightweight:** Model size < 1GB, CPU-only, and processes 3–5 documents in under 60 seconds.
- **No Internet Required:** All models and dependencies are local.

---

## Directory Structure
```
round1b/
├── input/                # Place input PDFs and challenge1b_input.json here
├── output/               # Output JSON will be written here
├── models/               # Pre-downloaded all-MiniLM-L6-v2 model
├── src/
│   ├── extractor.py      # Section/outline extraction logic
│   └── relevance.py      # Semantic ranking engine
├── main.py               # Pipeline orchestrator
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

---

## Input & Output
### Input
- Place all input PDFs and a `challenge1b_input.json` file in the `input/` directory.
- The input JSON must have the following structure:
```json
{
  "persona": "PhD Researcher in Computational Biology",
  "job_to_be_done": "Prepare a comprehensive literature review focusing on methodologies, datasets, and performance benchmarks",
  "documents": ["paper1.pdf", "paper2.pdf", "paper3.pdf"]
}
```

### Output
- The output will be written to `output/challenge1b_output.json` in the following format:
```json
{
  "metadata": {
    "input_documents": ["paper1.pdf", "paper2.pdf", "paper3.pdf"],
    "persona": "PhD Researcher in Computational Biology",
    "job_to_be_done": "Prepare a comprehensive literature review focusing on methodologies, datasets, and performance benchmarks",
    "processing_timestamp": "2025-07-20T12:34:56Z"
  },
  "extracted_sections": [
    {
      "document": "paper1.pdf",
      "page_number": 3,
      "section_title": "Methodology",
      "importance_rank": 0.92,
      "refined_text": "...section content..."
    }
    // ...more sections...
  ]
}
```

---

## How to Run
1. **Download the Model:**
   - Download the `all-MiniLM-L6-v2` SentenceTransformer model and place it in the `models/` directory.
2. **Build the Docker Image:**
   ```bash
   docker build --platform linux/amd64 -t persona-doc-intel .
   ```
3. **Run the Container:**
   ```bash
   docker run --rm -v $(pwd)/round1b/input:/app/input:ro -v $(pwd)/round1b/output:/app/output --network none persona-doc-intel
   ```

---

## Key Files
- `main.py` – Orchestrates the pipeline: loads input, extracts outlines, ranks sections, and writes output.
- `src/extractor.py` – Extracts document outlines and section content using heuristics and OCR.
- `src/relevance.py` – Ranks sections using semantic similarity to persona and job.
- `requirements.txt` – All required Python packages.
- `Dockerfile` – Containerizes the solution for reproducible, isolated execution.

---

## Constraints & Notes
- **CPU-only**; no GPU required.
- **Model size**: < 1GB (all-MiniLM-L6-v2 fits easily).
- **No internet access** during execution.
- **Processing time**: ≤ 60 seconds for 3–5 PDFs.
- **All dependencies** are open source and specified in `requirements.txt`.

---

## Acknowledgments
- Built for Adobe India Hackathon 2025, Round 1b.
- Uses open-source libraries: pdfplumber, pytesseract, Pillow, langdetect, pydantic, sentence-transformers, torch.

---

## Contact
For questions or issues, please contact the project team.
