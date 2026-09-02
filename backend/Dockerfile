# Alternative container build for the API, for platforms that prefer Docker
# over Render's native Python runtime (render.yaml uses the native runtime by
# default - this is provided for portability to other hosts).
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY core core
COPY backend backend

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
