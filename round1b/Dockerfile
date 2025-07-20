FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Install system tools and OCR dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils tesseract-ocr \
        tesseract-ocr-jpn tesseract-ocr-chi-sim tesseract-ocr-fra tesseract-ocr-deu && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy model directory (should be pre-populated locally)
COPY models ./models

# Copy source code and main script
COPY src ./src
COPY main.py .

# Create input/output mount points (for clarity, not strictly required)
RUN mkdir -p /app/input /app/output

ENTRYPOINT ["python", "main.py"]
