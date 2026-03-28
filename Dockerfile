# ── Rôle d'Évaluation — Docker image ─────────────────────────────────────────
FROM python:3.11-slim

# Keeps Python from generating .pyc files and enables real-time log output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY role_eval.py .
COPY app.py .

EXPOSE 7860

CMD ["python", "app.py"]
