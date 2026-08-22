# The OCR runtime. This is the production ingestion environment, not a workaround:
# workers run in Linux containers, and paddleocr dies in a oneDNN kernel on Windows.
FROM python:3.12-slim

# Paddle needs libgomp/libgl/libglib even when unused at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Paddle is ~1GB of wheels and is only needed to run the engine benchmark. Tesseract
# alone satisfies the phase 1 definition of done, so it is opt-in:
#   docker compose build --build-arg WITH_PADDLE=1 ocr
ARG WITH_PADDLE=0
RUN if [ "$WITH_PADDLE" = "1" ]; then \
        pip install --no-cache-dir paddlepaddle paddleocr; \
    fi

COPY app.py .
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
