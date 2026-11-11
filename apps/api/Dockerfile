FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends antiword && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY apps/api /srv/apps/api
COPY CLAUDE.md /srv/CLAUDE.md
RUN pip install --no-cache-dir --default-timeout=180 --retries 8 /srv/apps/api
# Meaning-based search on the server: CPU-only torch plus sentence-transformers (~1 GB image
# growth). The model weights are NOT baked in; they live in the `models` volume, downloaded
# once with `docker compose run --rm api python -m memora.services.embedding --warmup`.
ARG WITH_SEMANTIC=0
# Separate layers, long timeouts and retries: these wheels are large, and one slow download
# must not throw away the others.
RUN if [ "$WITH_SEMANTIC" = "1" ]; then \
      pip install --no-cache-dir --default-timeout=180 --retries 8 torch \
        --index-url https://download.pytorch.org/whl/cpu; \
    fi
RUN if [ "$WITH_SEMANTIC" = "1" ]; then \
      pip install --no-cache-dir --default-timeout=180 --retries 8 "sentence-transformers>=3.4,<6"; \
    fi
WORKDIR /srv/apps/api
CMD ["uvicorn", "memora.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
