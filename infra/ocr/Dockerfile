# The OCR runtime. This is the production ingestion environment, not a workaround:
# workers run in Linux containers, and paddleocr dies in a oneDNN kernel on Windows.
FROM python:3.12-slim

# Paddle needs libgomp/libgl/libglib even when unused at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-hin \
        tesseract-ocr-mar \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
# CPU torch explicitly. The default index pulls the CUDA build - about 2.5GB of
# wheels for a GPU this project does not have and will not have on a phone either.
# torch AND torchvision from the same index, together. Installing torch alone lets
# open_clip_torch pull a torchvision from PyPI built against a different torch, and the
# mismatch only surfaces at import as "operator torchvision::nms does not exist".
RUN pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Paddle is ~1GB of wheels and is only needed to run the engine benchmark. Tesseract
# alone satisfies the phase 1 definition of done, so it is opt-in:
#   docker compose build --build-arg WITH_PADDLE=1 ocr
ARG WITH_PADDLE=0
RUN if [ "$WITH_PADDLE" = "1" ]; then \
        pip install --no-cache-dir paddlepaddle paddleocr; \
    fi

# Bake the weights in. Downloading at first request would make the first search of
# every fresh container take minutes, and would need network at runtime from a
# service whose whole point is that it reaches nothing.
ENV CLIP_MODEL=ViT-B-32 CLIP_WEIGHTS=laion2b_s34b_b79k
RUN python -c "import open_clip, os; open_clip.create_model_and_transforms(os.environ['CLIP_MODEL'], pretrained=os.environ['CLIP_WEIGHTS'])"

COPY app.py .
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
