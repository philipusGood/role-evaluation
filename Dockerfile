# ── Rôle d'Évaluation — Docker image ─────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingest.py .
COPY role_eval.py .
COPY app.py .

# /data is a persistent volume — the SQLite DB lives here.
# Mount a host path to /data so the DB survives container restarts.
VOLUME ["/data"]

EXPOSE 7860

# On startup: run ingest (exits immediately if DB is current), then start Flask.
# First-run ingest takes ~15 minutes; progress is visible in Unraid Docker logs.
CMD ["sh", "-c", "python ingest.py && python app.py"]
