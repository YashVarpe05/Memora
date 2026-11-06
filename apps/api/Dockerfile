FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends antiword && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY apps/api /srv/apps/api
COPY CLAUDE.md /srv/CLAUDE.md
RUN pip install --no-cache-dir /srv/apps/api
WORKDIR /srv/apps/api
CMD ["uvicorn", "memora.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
