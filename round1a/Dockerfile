FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# system tools & tesseract for multilingual bonus
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils tesseract-ocr \
        tesseract-ocr-jpn tesseract-ocr-chi-sim tesseract-ocr-fra tesseract-ocr-deu && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY main.py .

ENTRYPOINT ["python", "main.py"]
